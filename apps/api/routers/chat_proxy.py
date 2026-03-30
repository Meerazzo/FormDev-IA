"""
Router proxy vers le serveur d'inférence vLLM.

Cet endpoint expose une API de chat compatible OpenAI permettant
aux applications clientes d'interagir directement avec
le modèle via la gateway FormDev.

Fonctionnalités :
- authentification par clé API
- rate limiting
- documentation Swagger enrichie
- gestion centralisée des erreurs réseau
"""

import time
import logging

from fastapi import APIRouter, HTTPException, Request, Security, Body
from fastapi.security import APIKeyHeader

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from schemas.chat import ChatRequest, ChatResponse, ChatUsage
from services.vllm_client import VLLMClient, VLLMConnectionError, VLLMUpstreamError

from services.interaction_logger import (
    log_ai_interaction_success,
    log_ai_interaction_error,
)


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM  # Limite de requêtes par minute appliquée à cet endpoint

router = APIRouter(tags=["gateway"])
vllm = VLLMClient()  # Instance du client vLLM utilisée pour appeler le serveur d'inférence

# Petit budget de continuation quand la première réponse a été coupée
CONTINUATION_MAX_TOKENS = 150

DEFAULT_SYSTEM_PROMPT = """
Tu es un assistant expert en rédaction en français, spécialisé dans les contenus de formation et les documents pédagogiques.

Ta mission est de produire des textes clairs, structurés, naturels et professionnels, adaptés à un contexte de formation.

Règles à respecter impérativement :
- utiliser un français irréprochable (orthographe, grammaire, syntaxe)
- produire un texte fluide, naturel et facile à comprendre
- adopter un ton pédagogique, professionnel et accessible
- éviter les formulations maladroites, les répétitions et les tournures artificielles
- respecter strictement la demande de l’utilisateur
- ne pas inventer d’informations si elles ne sont pas demandées
- adapter la longueur, le niveau de détail et le style à la consigne
- produire un texte directement réutilisable, sans commentaire inutile avant ou après

Si un texte est fourni :
- corriger les éventuelles fautes
- améliorer la clarté et la qualité du français
- conserver le sens initial sauf indication contraire

Le texte doit être équivalent à celui qu’un formateur ou concepteur pédagogique francophone produirait.

Réponds uniquement avec le texte final.
""".strip()

POST_CORRECTION_SYSTEM_PROMPT = """
Tu es un correcteur expert en langue française.

Ta mission est de corriger un texte déjà généré en appliquant le minimum de modifications nécessaires.

Règles impératives :
- corriger uniquement les fautes d'orthographe, de grammaire, de syntaxe et de ponctuation
- améliorer légèrement la fluidité seulement si une phrase est maladroite
- conserver strictement le sens, la structure et le niveau de détail du texte initial
- ne pas reformuler inutilement
- ne pas ajouter d'information
- ne pas développer le texte
- ne pas transformer le format du texte (pas de liste si le texte est un paragraphe)
- produire un texte final propre, naturel et directement exploitable

Réponds uniquement avec le texte corrigé.
""".strip()

def _extract_input_text(messages: list[dict]) -> str | None:
    user_contents = [
        (msg.get("content") or "").strip()
        for msg in messages
        if msg.get("role") == "user" and (msg.get("content") or "").strip()
    ]
    if not user_contents:
        return None
    return "\n\n".join(user_contents)

def _extract_main_fields(raw_response: dict) -> tuple[str, str | None, dict]:
    """Extrait le contenu, la raison d'arrêt et l'usage depuis la réponse brute vLLM."""
    choice = (raw_response.get("choices") or [{}])[0] or {}
    message = choice.get("message") or {}
    content = message.get("content", "") or ""
    finish_reason = choice.get("finish_reason")
    usage = raw_response.get("usage") or {}
    return content, finish_reason, usage


def _join_contents(first: str, continuation: str) -> str:
    """
    Concatène proprement la réponse initiale et la continuation.
    On évite juste les doubles espaces les plus évidents.
    """
    if not first:
        return continuation.strip()
    if not continuation:
        return first.strip()
    return f"{first.rstrip()} {continuation.lstrip()}".strip()

def _build_backend_messages(messages: list[dict]) -> list[dict]:
    """
    Construit la conversation envoyée au modèle en imposant
    le prompt système côté backend.

    Tous les messages 'system' fournis par le client sont ignorés.
    """
    non_system_messages = [msg for msg in messages if msg.get("role") != "system"]

    return [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        *non_system_messages,
    ]

def _build_post_correction_messages(text: str) -> list[dict]:
    """
    Construit la conversation pour la seconde passe de correction linguistique.
    """
    return [
        {"role": "system", "content": POST_CORRECTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Corrige ce texte avec un minimum de modifications. "
                "Ne développe pas, ne restructure pas inutilement, "
                "et conserve le même format :\n\n"
                f"{text}"
            ),
        },
    ]

@router.post(
    "/v1/chat",
    response_model=ChatResponse,
    summary="Générer ou transformer un texte en français",
    description="""
Interroge le modèle de langage via la gateway FormDev.

Cette route permet de réaliser différentes tâches de rédaction en français, par exemple :
- reformuler un texte
- résumer un contenu
- enrichir ou développer une idée
- générer un texte professionnel ou pédagogique

La requête repose sur une structure de conversation de type chat.

### Structure des messages

Chaque message contient :
- **role** : rôle du message dans la conversation
- **content** : texte du message

Rôles possibles :
- **user** : demande principale envoyée par l'application
- **assistant** : réponse précédente du modèle, si l'on souhaite conserver un historique conversationnel
- **system** : message optionnel côté client, mais le cadrage principal du modèle est défini côté serveur pour garantir une qualité homogène des réponses

### Recommandation d'usage

Pour obtenir les meilleurs résultats, il est recommandé d'exprimer clairement la tâche directement dans le message `user`.

Exemples :
- `Reformule ce texte dans un style professionnel : ...`
- `Résume ce texte en 3 phrases claires : ...`
- `Développe cet intitulé sous la forme d'un paragraphe : ...`

### Qualité rédactionnelle

Le comportement général du modèle est encadré côté serveur afin de garantir :
- un français correct et fluide
- un ton professionnel
- une réponse directement exploitable
- une meilleure cohérence entre les différents usages

### Paramètres de génération

- **temperature**  
  Contrôle le niveau de variation dans la réponse.
  - `0.2` → réponses plus stables, adaptées à la reformulation, au résumé et aux usages métier
  - `0.3` à `0.5` → réponses un peu plus variées, utiles pour du développement de contenu
  - `> 0.7` → réponses plus libres, mais moins prévisibles

- **top_p**  
  Contrôle la diversité de génération.  
  Valeur recommandée : **0.8 à 0.95**.

- **max_tokens**  
  Limite maximale de la réponse générée.  
  Si cette valeur est trop basse, la sortie peut être coupée.

### Post-correction optionnelle

- **post_correction**
  Si ce paramètre est activé, l'API effectue une seconde inférence après la génération initiale.
  Cette seconde passe sert à :
  - corriger les fautes d’orthographe et de grammaire
  - améliorer la fluidité
  - améliorer la tournure des phrases
  - conserver le sens initial

  Valeur par défaut : **false**.

### Bonne pratique

Pour contrôler la forme de la réponse, il est préférable de le préciser directement dans le message utilisateur.

Exemples :
- `Réponds en une phrase`
- `Fais une synthèse en 3 phrases`
- `Rédige un paragraphe détaillé`
- `Utilise un style professionnel et fluide`

### Contexte du modèle

Le modèle est servi avec une fenêtre de contexte configurée côté serveur.  
Cette limite correspond à la taille totale de la requête, c’est-à-dire :
- les messages envoyés
- plus la réponse générée
""",
    responses={
        200: {"description": "Réponse générée par le modèle"},
        401: {"description": "Clé API absente ou invalide"},
        429: {"description": "Limite de requêtes atteinte"},
        502: {"description": "Erreur du serveur d'inférence ou du proxy IA"},
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def chat(
    request: Request,
    payload: ChatRequest = Body(
        ...,
        openapi_examples={
            "simple_question": {
                "summary": "Question simple",
                "description": "Exemple minimal d'utilisation de la route.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Explique ce qu'est un style dans Word en 3 phrases simples."
                        }
                    ],
                    "max_tokens": 120,
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "post_correction": True
                },
            },
            "reformulation": {
                "summary": "Reformulation professionnelle",
                "description": "Améliorer un texte en corrigeant le français et en le rendant plus fluide.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reformule ce texte dans un style professionnel et fluide, sans changer le sens : Cette formation permet d aborder differents points liés à Word."
                        }
                    ],
                    "max_tokens": 120,
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "post_correction": True
                },
            },
            "summary_text": {
                "summary": "Résumé",
                "description": "Synthétiser un contenu en quelques phrases claires.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Résume ce texte en 3 phrases claires et professionnelles : Les styles dans Word permettent d appliquer rapidement une mise en forme cohérente à différents éléments d un document. Ils facilitent l organisation, la lisibilité et la structuration des contenus. Leur bonne utilisation permet aussi de gagner du temps lors de la mise en page."
                        }
                    ],
                    "max_tokens": 120,
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "post_correction": True
                },
            },
            "content_enrichment": {
                "summary": "Enrichissement de contenu",
                "description": "Développer un intitulé ou une idée sous forme de paragraphe réutilisable.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Développe cet intitulé sous la forme d'un paragraphe clair, fluide et professionnel, réutilisable dans un catalogue de formation : Travailler les titres dans Word"
                        }
                    ],
                    "max_tokens": 180,
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "post_correction": True
                },
            },
            "conversation_with_history": {
                "summary": "Conversation avec historique",
                "description": "Exemple avec conservation d'un échange précédent.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Résume ce texte en 3 phrases : Les styles dans Word permettent d harmoniser la mise en forme d un document."
                        },
                        {
                            "role": "assistant",
                            "content": "Les styles dans Word permettent d'appliquer une mise en forme cohérente à un document. Ils facilitent l'organisation du contenu et améliorent sa lisibilité. Leur utilisation permet également de gagner du temps dans la mise en page."
                        },
                        {
                            "role": "user",
                            "content": "Fais une version encore plus courte."
                        }
                    ],
                    "max_tokens": 80,
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "post_correction": True
                },
            },
            "reformulation_with_post_correction": {
                "summary": "Reformulation avec post-correction",
                "description": "Exemple avec seconde passe de correction linguistique activée.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reformule ce texte dans un style professionnel : cette formation permet daborder differents point sur word"
                        }
                    ],
                    "max_tokens": 120,
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "post_correction": True
                },
            },
        },
    ),
    x_api_key: str | None = Security(api_key_header),
):
    _, client_id = authenticate(x_api_key)  # Authentification via API key et récupération de l'identifiant client

    req_id = getattr(request.state, "request_id", None)

    client_messages = payload.model_dump(exclude_none=True).get("messages", [])
    backend_messages = _build_backend_messages(client_messages)

    request_params_json = {
        k: v
        for k, v in {
            "max_tokens": payload.max_tokens,
            "temperature": payload.temperature,
            "top_p": payload.top_p,
            "post_correction": payload.post_correction,
        }.items()
        if v is not None
    }

    input_text = _extract_input_text(client_messages)

    try:
        t0 = time.perf_counter()

        base_payload = payload.model_dump(exclude_none=True)
        base_payload.pop("post_correction", None)
        base_payload["messages"] = backend_messages

        raw_response = await vllm.chat_completions(base_payload)

        content, finish_reason, usage = _extract_main_fields(raw_response)
        final_content = content
        final_finish_reason = finish_reason
        final_usage = usage
        final_model = raw_response.get("model")

        # Si la réponse a été coupée par la limite de longueur,
        # on fait une seule relance pour terminer proprement.
        if finish_reason == "length" and content.strip():
            continuation_payload = payload.model_dump(exclude_none=True)
            continuation_payload.pop("post_correction", None)
            continuation_payload["messages"] = backend_messages + [
                {
                    "role": "assistant",
                    "content": content
                },
                {
                    "role": "user",
                    "content": (
                        "Continue uniquement la fin de la réponse sans répéter le début. "
                        "Termine proprement la phrase ou le paragraphe en cours."
                    )
                }
            ]

            # On garde temperature/top_p éventuels,
            # mais on utilise un petit budget juste pour finir.
            continuation_payload["max_tokens"] = CONTINUATION_MAX_TOKENS

            continuation_raw_response = await vllm.chat_completions(continuation_payload)
            continuation_content, continuation_finish_reason, continuation_usage = _extract_main_fields(
                continuation_raw_response
            )

            final_content = _join_contents(content, continuation_content)
            final_finish_reason = continuation_finish_reason or finish_reason

            # Reporting simple :
            # - on garde les prompt_tokens du premier appel
            # - on additionne les completion_tokens
            # - total_tokens recalculé
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = (usage.get("completion_tokens") or 0) + (
                continuation_usage.get("completion_tokens") or 0
            )

            if prompt_tokens is not None:
                total_tokens = prompt_tokens + completion_tokens
            else:
                total_tokens = None

            final_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        # Post-correction optionnelle : seconde inférence pour améliorer le français
        if payload.post_correction and final_content.strip():
            correction_payload = payload.model_dump(exclude_none=True)
            correction_payload.pop("post_correction", None)
            correction_payload["messages"] = _build_post_correction_messages(final_content)
            correction_payload["max_tokens"] = max(payload.max_tokens, 256)
            correction_payload["temperature"] = 0.1
            correction_payload["top_p"] = 0.9

            correction_raw_response = await vllm.chat_completions(correction_payload)
            corrected_content, correction_finish_reason, correction_usage = _extract_main_fields(
                correction_raw_response
            )

            if corrected_content.strip():
                final_content = corrected_content
                final_finish_reason = correction_finish_reason or final_finish_reason

                prompt_tokens = (final_usage or {}).get("prompt_tokens")
                completion_tokens = ((final_usage or {}).get("completion_tokens") or 0) + (
                    (correction_usage or {}).get("completion_tokens") or 0
                )

                if prompt_tokens is not None:
                    total_tokens = prompt_tokens + completion_tokens
                else:
                    total_tokens = None

                final_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }
        latency_ms = (time.perf_counter() - t0) * 1000.0
        log_ai_interaction_success(
            request_id=req_id,
            project="project_2",
            client_id=client_id,
            endpoint="/v1/chat",
            feature="chat",
            model_requested=payload.model,
            model_used=final_model,
            input_text=input_text,
            messages_json=backend_messages,
            request_params_json=request_params_json,
            output_text=final_content,
            response_json={
                "model": final_model,
                "content": final_content,
                "finish_reason": final_finish_reason,
                "usage": final_usage,
                "latency_ms": round(latency_ms, 1),
            },
            finish_reason=final_finish_reason,
            prompt_tokens=final_usage.get("prompt_tokens"),
            completion_tokens=final_usage.get("completion_tokens"),
            total_tokens=final_usage.get("total_tokens"),
            latency_ms=round(latency_ms, 1),
            status_code=200,
            pipeline_name="chat_gateway",
            pipeline_version="v1",
        )
        return ChatResponse(
            model=final_model,
            content=final_content,
            finish_reason=final_finish_reason,
            usage=ChatUsage(
                prompt_tokens=final_usage.get("prompt_tokens"),
                completion_tokens=final_usage.get("completion_tokens"),
                total_tokens=final_usage.get("total_tokens"),
            ),
            latency_ms=round(latency_ms, 1),
        )

    except VLLMConnectionError:
        log_ai_interaction_error(
            request_id=req_id,
            project="project_2",
            client_id=client_id,
            endpoint="/v1/chat",
            feature="chat",
            model_requested=payload.model,
            input_text=input_text,
            messages_json=backend_messages,
            request_params_json=request_params_json,
            status_code=502,
            error_type="VLLMConnectionError",
            error_message="Cannot reach inference server (vLLM)",
            pipeline_name="chat_gateway",
            pipeline_version="v1",
        )
        raise HTTPException(status_code=502, detail="Cannot reach inference server (vLLM)")

    except VLLMUpstreamError as e:
        log_ai_interaction_error(
            request_id=req_id,
            project="project_2",
            client_id=client_id,
            endpoint="/v1/chat",
            feature="chat",
            model_requested=payload.model,
            input_text=input_text,
            messages_json=backend_messages,
            request_params_json=request_params_json,
            status_code=502,
            error_type="VLLMUpstreamError",
            error_message=f"vLLM upstream error ({e.status_code})",
            pipeline_name="chat_gateway",
            pipeline_version="v1",
            metadata_json={"upstream_status_code": e.status_code},
        )
        raise HTTPException(status_code=502, detail=f"vLLM upstream error ({e.status_code})")

    except Exception as e:
        log_ai_interaction_error(
            request_id=req_id,
            project="project_2",
            client_id=client_id,
            endpoint="/v1/chat",
            feature="chat",
            model_requested=payload.model,
            input_text=input_text,
            messages_json=backend_messages,
            request_params_json=request_params_json,
            status_code=502,
            error_type=type(e).__name__,
            error_message=str(e),
            pipeline_name="chat_gateway",
            pipeline_version="v1",
        )
        raise HTTPException(status_code=502, detail=f"Model error: {type(e).__name__}")