"""
Router proxy vers le serveur d'inférence vLLM.

Cet endpoint expose une API compatible OpenAI permettant
aux applications clientes d'interagir directement avec
le modèle via la gateway FormDev.

Fonctionnalités :
- authentification API key
- rate limiting
- gestion des erreurs réseau
"""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Header, HTTPException, Request

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from services.vllm_client import VLLMClient

RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM # Limite de requêtes par minute appliquée à cet endpoint

router = APIRouter(tags=["gateway"])
vllm = VLLMClient() # Instance du client vLLM utilisée pour appeler le serveur d'inférence

@router.post(
    "/v1/chat",
    summary="Proxy vers le modèle de chat",
    description="Transmet une requête de type OpenAI Chat Completions au serveur vLLM local.",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute") 
async def chat(payload: Dict[str, Any], request: Request, x_api_key: str | None = Header(default=None)):
    _, client_id = authenticate(x_api_key) # Authentification via API key et récupération de l'identifiant client
    _ = client_id  # future multi-tenant

    try:
        return await vllm.chat_completions(payload)
    except RuntimeError as e:
        msg = str(e)
        if "Cannot reach inference server" in msg:
            raise HTTPException(status_code=502, detail=msg)
        raise HTTPException(status_code=502, detail=msg)