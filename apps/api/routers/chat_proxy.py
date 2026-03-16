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


@router.post(
    "/v1/chat",
    response_model=ChatResponse,
    summary="Interroger le modèle de chat",
    description="""
Interroge le modèle de langage via la gateway FormDev.

La requête doit contenir une liste de messages structurés.

Chaque message possède un **role** et un **content**.

### Rôles possibles

- **system** : définit le comportement ou les instructions générales du modèle
- **user** : message envoyé par l'utilisateur ou l'application
- **assistant** : réponse précédente du modèle (optionnel)

### Exemple simple

system → définit le rôle de l'IA  
user → question ou demande  

### Exemple

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
Paramètres principaux

- max_tokens : longueur maximale de la réponse

- temperature : créativité de la réponse

- top_p : diversité du texte généré
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
        raw_response = await vllm.chat_completions(payload.model_dump(exclude_none=True))
        latency_ms = (time.perf_counter() - t0) * 1000.0

        choice = raw_response.get("choices", [{}])[0]
        message = choice.get("message", {}) or {}
        usage = raw_response.get("usage", {}) or {}

        return ChatResponse(
            model=raw_response.get("model"),
            content=message.get("content", ""),
            finish_reason=choice.get("finish_reason"),
            usage=ChatUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
            latency_ms=round(latency_ms, 1),
        )

    except VLLMConnectionError:
        raise HTTPException(status_code=502, detail="Cannot reach inference server (vLLM)")

    except VLLMUpstreamError as e:
        raise HTTPException(status_code=502, detail=f"vLLM upstream error ({e.status_code})")

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Model error: {type(e).__name__}")