import logging
import os
import time
import uuid
from typing import Any, Dict, Tuple

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# -----------------------------------------------------------------------------
# API Gateway FormDev IA (Lot 0)
# -----------------------------------------------------------------------------
# Rôle :
# - Fournir un point d’entrée stable pour l’ERP / extranets (nos routes à nous)
# - Ajouter la sécurité et la protection du GPU : clé API + rate limiting
# - Faire l’intermédiaire (proxy) vers le serveur d’inférence vLLM
#
# Pourquoi ne pas appeler vLLM directement ?
# - vLLM = moteur d’inférence, pas un backend “métier”
# - Ici on centralise : auth, multi-tenant (client_id), logs, futures routes RAG/surveys
#
# Projets à venir :
# - /rag/*      : ingestion docs/urls + index + chat RAG multi-clients
# - /content/*  : enrichissement de contenu
# - /surveys/*  : segmentation + sentiment/catégorie + feedback
# -----------------------------------------------------------------------------

# URL interne du serveur vLLM (dans Docker, ça doit être "http://inference:8000")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000").rstrip("/")

# Limite simple de requêtes/minute (Lot 0). On pourra passer à un quota par client.
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "30"))

# Clés API autorisées.
# Format conseillé : "clientA:key1,clientB:key2"
# (ça permet de récupérer un client_id à partir de la clé)
API_KEYS_RAW = os.getenv("API_KEYS", "")

VALID_KEYS: set[str] = set()
KEY_TO_CLIENT: dict[str, str] = {}

for chunk in [c.strip() for c in API_KEYS_RAW.split(",") if c.strip()]:
    if ":" in chunk:
        client_id, key = chunk.split(":", 1)
        client_id = client_id.strip()
        key = key.strip()
        if key:
            VALID_KEYS.add(key)
            KEY_TO_CLIENT[key] = client_id
    else:
        key = chunk.strip()
        if key:
            VALID_KEYS.add(key)

# Rate limiting (actuellement par IP). Plus tard : par client_id ou par API key.
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT_RPM}/minute"])

app = FastAPI(title="FormDev IA - Gateway (Lot 0)")

# -----------------------------------------------------------------------------
# Journalisation (logs)
# -----------------------------------------------------------------------------
# Pour Lot 0 on reste simple : logs texte lisibles dans `docker compose logs -f api`.
# On log les requêtes et les erreurs non gérées.
logger = logging.getLogger("formdev_ia_api")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log stacktrace côté serveur, réponse générique côté client
    req_id = getattr(request.state, "request_id", "-")
    logger.exception("Erreur non gérée request_id=%s path=%s", req_id, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# -----------------------------------------------------------------------------
# Gestion du rate limit
# -----------------------------------------------------------------------------
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


# -----------------------------------------------------------------------------
# Middleware : X-Request-Id + logs d'accès
# -----------------------------------------------------------------------------
@app.middleware("http")
async def request_trace_and_access_log(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    start = time.perf_counter()

    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        status_code = getattr(response, "status_code", "-") if "response" in locals() else "-"

        # Tentative de récupérer le client_id via la clé API (si format client:key)
        api_key = request.headers.get("x-api-key")
        client_id = KEY_TO_CLIENT.get(api_key) if api_key else None

        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f request_id=%s client_id=%s",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
            request.state.request_id,
            client_id or "-",
        )

        # Ajoute toujours le request_id dans la réponse (quand on en a une)
        if "response" in locals():
            response.headers["X-Request-Id"] = request.state.request_id


# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
def authenticate(x_api_key: str | None) -> Tuple[str, str | None]:
    """
    Vérifie la clé API et renvoie (api_key, client_id).

    - Si API_KEYS est au format "client:key", client_id est rempli.
    - Sinon client_id peut être None.
    """
    if not VALID_KEYS:
        # Fail closed : si on a oublié de configurer API_KEYS, on refuse.
        raise HTTPException(status_code=500, detail="API_KEYS not configured")

    if not x_api_key or x_api_key not in VALID_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_api_key, KEY_TO_CLIENT.get(x_api_key)


# -----------------------------------------------------------------------------
# Routes Lot 0
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    """Endpoint de vie (monitoring, tests d’intégration)."""
    return {"status": "ok"}


@app.post("/v1/chat")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def chat(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(default=None),
):
    """
    Proxy sécurisé vers vLLM : /v1/chat/completions (OpenAI-compatible)

    L’ERP nous envoie un payload type OpenAI Chat Completions :
    {
      "model": "...",
      "messages": [{"role":"user","content":"..."}],
      "max_tokens": 128
    }
    """
    _, client_id = authenticate(x_api_key)

    # NOTE : bientôt on utilisera client_id pour :
    # - choisir le corpus RAG (Projet 1)
    # - appliquer des quotas par client
    _ = client_id

    url = f"{VLLM_BASE_URL}/v1/chat/completions"
    timeout = httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
    except httpx.ConnectError:
        # Erreur typique quand VLLM_BASE_URL est mal configuré ou vLLM down
        raise HTTPException(status_code=502, detail="Cannot reach inference server (vLLM)")

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


# -----------------------------------------------------------------------------
# À venir (Projets 1/2/3)
# -----------------------------------------------------------------------------
# /rag/*     : ingestion docs/urls, resync, chat RAG + citations
# /content/* : enrichissement texte
# /surveys/* : analyse + feedback + batch