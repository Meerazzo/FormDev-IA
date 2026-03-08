from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from schemas.content import ContentEnrichRequest, ContentEnrichResponse
from services.vllm_client import (
    VLLMClient,
    VLLMConnectionError,
    VLLMUpstreamError,
    get_vllm_client,
)
from projects.contentSuggest.service import enrich_content

router = APIRouter(prefix="/v1/content", tags=["content"])


@router.post("/enrich", response_model=ContentEnrichResponse)
async def enrich(req: ContentEnrichRequest, client: VLLMClient = Depends(get_vllm_client)):
    try:
        enriched, model, latency_ms = await enrich_content(req, client)
        return ContentEnrichResponse(enriched_text=enriched, model=model, latency_ms=latency_ms)

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Model timeout")

    except VLLMConnectionError:
        raise HTTPException(status_code=502, detail="Cannot reach inference server (vLLM)")

    except VLLMUpstreamError as e:
        # upstream a répondu 4xx/5xx (mauvais payload, OOM, etc.)
        raise HTTPException(status_code=502, detail=f"vLLM upstream error ({e.status_code})")

    except Exception as e:
        # pas de leak d'infos internes
        raise HTTPException(status_code=502, detail=f"Model error: {type(e).__name__}")