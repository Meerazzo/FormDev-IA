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

from fastapi import APIRouter, HTTPException, Request, Security, Body
from fastapi.security import APIKeyHeader

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from schemas.chat import ChatRequest, ChatResponse, ChatUsage
from services.vllm_client import VLLMClient, VLLMConnectionError, VLLMUpstreamError
from core.feature_config import (
    CHAT_DEFAULT_SYSTEM_PROMPT,
    CHAT_POST_CORRECTION_SYSTEM_PROMPT,
)
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

def _build_backend_messages(messages: list[dict], system_prompt: str | None = None) -> list[dict]:
    """
    Construit la conversation envoyée au modèle.

    Tous les messages 'system' fournis dans l'historique sont ignorés
    afin d'éviter les doublons. Un seul prompt système est injecté :
    - celui fourni explicitement par le client si présent
    - sinon le prompt système par défaut du backend
    """
    non_system_messages = [msg for msg in messages if msg.get("role") != "system"]
    final_system_prompt = (system_prompt or CHAT_DEFAULT_SYSTEM_PROMPT).strip()

    return [
        {"role": "system", "content": final_system_prompt},
        *non_system_messages,
    ]

def _build_post_correction_messages(
    text: str,
    post_correction_prompt: str | None = None,
) -> list[dict]:
    """
    Construit la conversation pour la seconde passe de correction linguistique.

    Le prompt de correction peut être fourni par le client.
    À défaut, on utilise le prompt de correction par défaut du backend.
    """
    final_post_prompt = (post_correction_prompt or CHAT_POST_CORRECTION_SYSTEM_PROMPT).strip()

    return [
        {"role": "system", "content": final_post_prompt},
        {
            "role": "user",
            "content": (
                "Corrige ce texte avec un minimum de modifications. "
                "Améliore la langue si nécessaire, mais conserve le sens général et un format comparable :\n\n"
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
- **system** : message système possible côté client via le champ system_prompt. Si aucun prompt système n’est fourni, l’API utilise un prompt par défaut côté serveur.

### Recommandation d'usage

Pour obtenir les meilleurs résultats, il est recommandé d'exprimer clairement la tâche directement dans le message `user`.

Exemples :
- `Reformule ce texte dans un style professionnel : ...`
- `Résume ce texte en 3 phrases claires : ...`
- `Développe cet intitulé sous la forme d'un paragraphe : ...`

### Personnalisation des prompts

L'API peut fonctionner :
- avec les prompts par défaut du backend
- ou avec des prompts fournis dans la requête

Champs disponibles :
- `system_prompt` : remplace le prompt système par défaut
- `post_correction_prompt` : remplace le prompt de correction si `post_correction=true`

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
        "reformulation_catalogue_sport": {
            "summary": "Reformulation d'une description de formation sport",
            "description": "Exemple de reformulation d'un texte de présentation destiné à un catalogue de formation.",
            "value": {
                "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                "system_prompt": (
                    "Tu es un assistant de reformulation en français. "
                    "Tu reformules les textes dans un style professionnel, fluide, clair et naturel. "
                    "Tu conserves le sens initial, sans ajouter d'information non présente."
                ),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Reformule ce texte pour une brochure de formation : "
                            "Cette formation permet de voir plusieurs points pour apprendre à encadrer des séances de renforcement musculaire, "
                            "avec une partie pratique, des conseils de posture et des idées d'exercices adaptables à différents publics."
                        )
                    }
                ],
                "max_tokens": 180,
                "temperature": 0.2,
                "top_p": 0.9,
                "post_correction": False
            },
        },
        "reformulation_technique_industrielle": {
            "summary": "Reformulation d'un texte technique industriel",
            "description": "Exemple de reformulation d'un contenu technique dans un style plus structuré et professionnel.",
            "value": {
                "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                "system_prompt": (
                    "Tu es un assistant de reformulation professionnelle. "
                    "Tu clarifies les formulations, améliores la fluidité et corriges les maladresses, "
                    "sans modifier le fond technique."
                ),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Reformule ce texte : "
                            "La formation sert à revoir les bases de maintenance de premier niveau sur des équipements industriels, "
                            "avec de la prévention sécurité, des contrôles visuels et quelques manipulations simples pour éviter les pannes courantes."
                        )
                    }
                ],
                "max_tokens": 180,
                "temperature": 0.2,
                "top_p": 0.9,
                "post_correction": False
            },
        },
        "summary_safety_training": {
            "summary": "Synthèse d'un texte de formation sécurité",
            "description": "Résumer un texte de présentation en quelques phrases claires et exploitables.",
            "value": {
                "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                "system_prompt": (
                    "Tu es un assistant de synthèse. "
                    "Tu produis des résumés clairs, structurés et professionnels en français. "
                    "Tu conserves uniquement les informations essentielles."
                ),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Résume ce texte en 3 phrases : "
                            "Cette formation sensibilise les participants aux risques liés au travail en hauteur. "
                            "Elle présente les règles de sécurité, les équipements de protection individuelle, "
                            "les bonnes pratiques de vérification du matériel et les réflexes à adopter avant toute intervention. "
                            "Des cas concrets et des mises en situation permettent de relier les apports théoriques à la réalité du terrain."
                        )
                    }
                ],
                "max_tokens": 140,
                "temperature": 0.2,
                "top_p": 0.9,
                "post_correction": False
            },
        },
        "content_enrichment_medico_social": {
            "summary": "Enrichissement d'un intitulé de formation médico-sociale",
            "description": "Développer un intitulé court en paragraphe réutilisable dans un catalogue.",
            "value": {
                "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                "system_prompt": (
                    "Tu es un assistant de rédaction pour des catalogues de formation. "
                    "Tu développes les intitulés en paragraphes professionnels, fluides, précis et directement réutilisables."
                ),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Développe cet intitulé sous la forme d'un paragraphe de présentation de formation : "
                            "Prévenir l'épuisement professionnel dans les métiers de l'accompagnement"
                        )
                    }
                ],
                "max_tokens": 220,
                "temperature": 0.3,
                "top_p": 0.9,
                "post_correction": False
            },
        },
        "conversation_with_history_project_management": {
            "summary": "Conversation avec historique",
            "description": "Exemple de suivi de consigne dans un échange déjà commencé.",
            "value": {
                "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                "system_prompt": (
                    "Tu es un assistant de rédaction professionnelle. "
                    "Tu réponds en français clair, synthétique et réutilisable en contexte formation."
                ),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Résume ce texte en 4 phrases : "
                            "Cette formation en gestion de projet permet aux participants de comprendre les grandes étapes de cadrage, "
                            "de planification, de suivi et de clôture d'un projet. "
                            "Elle aborde également la coordination des acteurs, le suivi des délais, "
                            "la gestion des priorités et l'anticipation des risques."
                        )
                    },
                    {
                        "role": "assistant",
                        "content": (
                            "Cette formation présente les principales étapes de la gestion de projet, du cadrage à la clôture. "
                            "Elle aide à structurer le suivi des délais, des priorités et des risques. "
                            "Elle met également l'accent sur la coordination des acteurs impliqués. "
                            "L'ensemble vise à renforcer la conduite opérationnelle des projets."
                        )
                    },
                    {
                        "role": "user",
                        "content": "Fais maintenant une version plus concise en 2 phrases."
                    }
                ],
                "max_tokens": 100,
                "temperature": 0.2,
                "top_p": 0.9,
                "post_correction": False
            },
        },
        "post_correction_custom_prompt": {
            "summary": "Post-correction avec prompt personnalisé",
            "description": "Exemple où la génération est suivie d'une correction linguistique pilotée par le client.",
            "value": {
                "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                "system_prompt": (
                    "Tu es un assistant de reformulation professionnelle. "
                    "Réécris le texte dans un style clair et professionnel."
                ),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Reformule ce texte : "
                            "Cette formation permet aux équipes techniques de mieux comprendre les bases du câblage réseau, "
                            "les points de vigilance lors des installations et les erreurs fréquentes à éviter sur le terrain."
                        )
                    }
                ],
                "max_tokens": 180,
                "temperature": 0.2,
                "top_p": 0.9,
                "post_correction": True,
                "post_correction_prompt": (
                    "Tu es un correcteur linguistique. "
                    "Corrige l'orthographe, la grammaire et la syntaxe. "
                    "Améliore légèrement la fluidité sans changer le sens, sans raccourcir fortement et sans ajouter d'information."
                )
            },
        },
    }
    ),
    x_api_key: str | None = Security(api_key_header),
):
    _, client_id = authenticate(x_api_key)  # Authentification via API key et récupération de l'identifiant client

    req_id = getattr(request.state, "request_id", None)

    client_messages = payload.model_dump(exclude_none=True).get("messages", [])
    backend_messages = _build_backend_messages(
        client_messages,
        system_prompt=payload.system_prompt,
    )

    request_params_json = {
        k: v
        for k, v in {
            "max_tokens": payload.max_tokens,
            "temperature": payload.temperature,
            "top_p": payload.top_p,
            "post_correction": payload.post_correction,
            "system_prompt": payload.system_prompt,
            "post_correction_prompt": payload.post_correction_prompt,
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
            correction_payload["messages"] = _build_post_correction_messages(
                final_content,
                post_correction_prompt=payload.post_correction_prompt,
            )
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