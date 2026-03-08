"""
Router FastAPI pour l'enrichissement de contenu pédagogique.

Expose l'endpoint :

POST /v1/content/enrich

Cet endpoint transforme un intitulé de formation
en description pédagogique complète.
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Body

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

router = APIRouter(prefix="/v1/content", tags=["content"]) # Route principale du service d'enrichissement


@router.post("/enrich", response_model=ContentEnrichResponse)
@limiter.limit(f"{settings.RATE_LIMIT_RPM}/minute")
async def enrich(
    request: Request,
    req: ContentEnrichRequest = Body(...),
    client: VLLMClient = Depends(get_vllm_client),
    x_api_key: str | None = Header(default=None),
):
    authenticate(x_api_key) # Vérification de la clé API avant traitement

    try:
        enriched, model, latency_ms = await enrich_content(req, client) # Appel du service métier responsable de la génération
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