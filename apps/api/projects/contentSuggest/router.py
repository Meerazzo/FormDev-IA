"""
Router FastAPI pour l'enrichissement de contenu pédagogique.

Expose l'endpoint :

POST /v1/content/enrich

Cet endpoint transforme un intitulé de formation
en description pédagogique complète.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Body, Security
from fastapi.security import APIKeyHeader

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from schemas.content import ContentEnrichRequest, ContentEnrichResponse
from services.vllm_client import (
    VLLMClient,
    VLLMConnectionError,
    VLLMUpstreamError,
    get_vllm_client,
)
from projects.contentSuggest.service import enrich_content

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

router = APIRouter(prefix="/v1/content", tags=["content"])  # Route principale du service d'enrichissement


@router.post(
    "/enrich",
    response_model=ContentEnrichResponse,
    summary="Enrichir un intitulé de formation",
    description="""
Génère un paragraphe pédagogique complet à partir d’un intitulé de formation.

Le texte retourné est destiné à être réutilisé directement dans FormDev.
Selon les paramètres fournis, la génération peut prendre en compte :
- le contexte de la formation
- le niveau visé
- la durée
- le public cible
- la longueur souhaitée
- le style rédactionnel
- la langue de sortie
""",
    response_description="Texte enrichi généré par le modèle",
    responses={
        401: {"description": "Clé API absente ou invalide"},
        429: {"description": "Limite de requêtes atteinte"},
        502: {"description": "Erreur du serveur d'inférence ou service indisponible"},
        504: {"description": "Timeout lors de la génération côté modèle"},
    },
)
@limiter.limit(f"{settings.RATE_LIMIT_RPM}/minute")
async def enrich(
    request: Request,
    req: ContentEnrichRequest = Body(
        ...,
        openapi_examples={
            "minimal": {
                "summary": "Exemple minimal",
                "description": "Cas le plus simple, avec seulement l’intitulé à enrichir.",
                "value": {
                    "text": "Travailler les titres dans Word"
                },
            },
            "standard": {
                "summary": "Exemple standard",
                "description": "Cas typique avec contexte pédagogique et options de génération.",
                "value": {
                    "text": "Travailler les titres dans Word",
                    "context": {
                        "training_name": "Word - Initiation",
                        "level": "débutant"
                    },
                    "options": {
                        "length": "medium",
                        "style": "pedagogic",
                        "language": "fr"
                    }
                },
            },
            "advanced": {
                "summary": "Exemple avancé",
                "description": "Cas plus complet avec contexte métier plus détaillé.",
                "value": {
                    "text": "Automatiser des tâches avec les macros",
                    "context": {
                        "training_name": "Excel - Perfectionnement",
                        "level": "avancé",
                        "duration": "1 jour",
                        "audience": "utilisateurs expérimentés"
                    },
                    "options": {
                        "length": "long",
                        "style": "descriptive",
                        "language": "fr"
                    }
                },
            },
        },
    ),
    client: VLLMClient = Depends(get_vllm_client),
    x_api_key: str | None = Security(api_key_header),
):
    authenticate(x_api_key)  # Vérification de la clé API avant traitement

    try:
        enriched, model, latency_ms = await enrich_content(req, client)  # Appel du service métier responsable de la génération
        return ContentEnrichResponse(
            enriched_text=enriched,
            model=model,
            latency_ms=latency_ms,
        )

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Model timeout")

    except VLLMConnectionError:
        raise HTTPException(status_code=502, detail="Cannot reach inference server (vLLM)")

    except VLLMUpstreamError as e:
        raise HTTPException(status_code=502, detail=f"vLLM upstream error ({e.status_code})")

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Model error: {type(e).__name__}")