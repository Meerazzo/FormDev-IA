from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Header, HTTPException, Request

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from services.vllm_client import VLLMClient

RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM

router = APIRouter(tags=["gateway"])
vllm = VLLMClient()

@router.post("/v1/chat")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def chat(payload: Dict[str, Any], request: Request, x_api_key: str | None = Header(default=None)):
    _, client_id = authenticate(x_api_key)
    _ = client_id  # future multi-tenant

    try:
        return await vllm.chat_completions(payload)
    except RuntimeError as e:
        msg = str(e)
        if "Cannot reach inference server" in msg:
            raise HTTPException(status_code=502, detail=msg)
        raise HTTPException(status_code=502, detail=msg)