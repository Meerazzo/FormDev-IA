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
from schemas.chat import ChatRequest, ChatResponse, ChatResponseMessage, ChatUsage
from services.vllm_client import VLLMClient, VLLMConnectionError, VLLMUpstreamError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM  # Limite de requêtes par minute appliquée à cet endpoint

router = APIRouter(tags=["gateway"])
vllm = VLLMClient()  # Instance du client vLLM utilisée pour appeler le serveur d'inférence

# Petit budget de continuation quand la première réponse a été coupée
CONTINUATION_MAX_TOKENS = 80

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

@router.post(
    "/v1/chat",
    response_model=ChatResponse,
    summary="Interroger le modèle de chat",
    description="""
Interroge le modèle de langage via la gateway FormDev.

La requête contient une liste de **messages structurés** représentant une conversation.

Chaque message possède :
- **role** : type de message
- **content** : texte du message

### Rôles disponibles

- **system** : instructions générales pour cadrer le comportement du modèle  
- **user** : demande ou question envoyée par l'application  
- **assistant** : réponse précédente du modèle (optionnel, pour maintenir un contexte)

Exemple minimal :

```json
{
  "messages": [
    {
      "role": "system",
      "content": "Tu es un assistant pédagogique."
    },
    {
      "role": "user",
      "content": "Explique ce qu'est un style dans Word."
    }
  ]
}
```
### Paramètres de génération

- **temperature**  
  Contrôle la créativité de la réponse.  
  - `0.2` → réponses très stables  
  - `0.4` à `0.7` → bon compromis pour un usage métier  
  - `> 0.8` → réponses plus variées mais moins prévisibles

- **top_p**  
  Contrôle la diversité du texte généré.  
  Valeur recommandée : **0.8 à 0.95**.

- **max_tokens**  
  Limite technique sur la taille maximale de la réponse.  
  Si la valeur est trop basse, la réponse peut être coupée.

### Bonne pratique

Pour contrôler la longueur de la réponse, il est préférable de le préciser directement dans le prompt, par exemple :

- `"Réponds en une phrase"`
- `"Fais une réponse courte de 3 à 4 phrases"`
- `"Rédige un paragraphe détaillé"`

### Contexte du modèle

Le modèle **Qwen 7B Instruct** est servi avec une fenêtre de contexte configurée à **4096 tokens** côté serveur.  
Cette limite correspond à la taille totale de la requête (**messages + génération**).
une limite de 1024 tokens a ete definis cote serveur pour le prompt.
""",
    responses={
        200: {"description": "Réponse générée par le modèle"},
        401: {"description": "Clé API absente ou invalide"},
        429: {"description": "Limite de requêtes atteinte"},
        502: {"description": "Serveur d'inférence inaccessible ou erreur amont"},
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def chat(
    request: Request,
    payload: ChatRequest = Body(
        ...,
        openapi_examples={
            "roles_explanation": {
                "summary": "Comprendre les rôles",
                "description": "Exemple montrant le rôle system et user.",
                "value": {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Tu es un assistant pédagogique spécialisé dans les outils bureautiques."
                        },
                        {
                            "role": "user",
                            "content": "Explique ce qu'est un style dans Word."
                        }
                    ],
                    "max_tokens": 150
                }
            },
            "simple": {
                "summary": "Question simple",
                "description": "Exemple minimal pour interroger directement le modèle.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Dis bonjour en une phrase."
                        }
                    ],
                    "max_tokens": 60
                },
            },
            "pedagogical_enrichment": {
                "summary": "Enrichissement pédagogique",
                "description": "Exemple d’usage FormDev avec prompt système métier.",
                "value": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Tu es un assistant spécialisé en ingénierie pédagogique. Rédige un paragraphe clair, fluide et réutilisable dans un logiciel de formation. Le texte doit présenter l’objectif pédagogique, les notions travaillées et les bénéfices pour l’apprenant."
                        },
                        {
                            "role": "user",
                            "content": "Travailler les titres dans Word"
                        }
                    ],
                    "max_tokens": 220,
                    "temperature": 0.4,
                    "top_p": 0.9
                },
            },
            "reformulation": {
                "summary": "Reformulation",
                "description": "Exemple de reformulation d’un texte fourni par l’ERP.",
                "value": {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Tu reformules les textes de manière claire, concise et professionnelle."
                        },
                        {
                            "role": "user",
                            "content": "Reformule : Cette formation permet d'aborder différents points liés à Word."
                        }
                    ],
                    "max_tokens": 120
                },
            },
        },
    ),
    x_api_key: str | None = Security(api_key_header),
):
    _, client_id = authenticate(x_api_key)  # Authentification via API key et récupération de l'identifiant client
    _ = client_id  # future logique multi-tenant / quotas différenciés

    try:
        t0 = time.perf_counter()

        base_payload = payload.model_dump(exclude_none=True)
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

            continuation_payload["messages"] = continuation_payload["messages"] + [
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

        latency_ms = (time.perf_counter() - t0) * 1000.0

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
        raise HTTPException(status_code=502, detail="Cannot reach inference server (vLLM)")

    except VLLMUpstreamError as e:
        raise HTTPException(status_code=502, detail=f"vLLM upstream error ({e.status_code})")

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Model error: {type(e).__name__}")