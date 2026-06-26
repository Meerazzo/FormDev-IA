"""
Gestion du logging et du traçage des requêtes.

Ce module configure :
- le niveau de logs
- l'envoi optionnel vers Greylog
- la gestion centralisée des exceptions
- un middleware ajoutant un identifiant unique à chaque requête

Les logs HTTP restent volontairement légers :
- pas de body
- pas de payload questionnaire
- pas de prompt LLM
- pas de clé API
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from core.config import settings
from core.security import KEY_TO_CLIENT

LOG_LEVEL = settings.LOG_LEVEL.upper()

logger = logging.getLogger("formdev_ia_api")


def _module_from_path(path: str) -> str:
    if path.startswith("/v1/chat"):
        return "chat"
    if path.startswith("/surveys"):
        return "surveys"
    if path.startswith("/rag"):
        return "rag"
    return "system"


def _route_family(path: str) -> str:
    if path.startswith("/v1/chat"):
        return "chat_gateway"
    if path.startswith("/surveys/feedback"):
        return "surveys_feedback"
    if path.startswith("/surveys/processings"):
        return "surveys_processing"
    if path.startswith("/surveys/analyze"):
        return "surveys_analyze"
    if path.startswith("/rag/sources"):
        return "rag_sources"
    if path.startswith("/rag/corpora"):
        return "rag_corpora"
    if path.startswith("/rag/search"):
        return "rag_search"
    if path.startswith("/rag/chat"):
        return "rag_chat"
    if path.startswith("/rag/jobs"):
        return "rag_jobs"
    if path.startswith("/rag/health"):
        return "rag_health"
    return "system"


def _status_family(status_code) -> str:
    try:
        status = int(status_code)
    except Exception:
        return "unknown"
    return f"{status // 100}xx"


def _latency_bucket(duration_ms: float) -> str:
    if duration_ms < 100:
        return "lt_100ms"
    if duration_ms < 500:
        return "100_500ms"
    if duration_ms < 1000:
        return "500ms_1s"
    if duration_ms < 3000:
        return "1_3s"
    if duration_ms < 10000:
        return "3_10s"
    return "gt_10s"


def _level_for_status(status_code) -> int:
    try:
        status = int(status_code)
    except Exception:
        return logging.INFO
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO


def setup_logging() -> None:
    """
    Initialise la configuration globale des logs.

    Les logs sont envoyés :
    - sur stdout pour Docker
    - vers Greylog en GELF UDP si activé
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if settings.GRAYLOG_ENABLED:
        try:
            import graypy

            graylog_handler = graypy.GELFUDPHandler(
                settings.GRAYLOG_HOST,
                settings.GRAYLOG_PORT,
                facility=settings.GRAYLOG_FACILITY,
            )
            graylog_handler.setLevel(LOG_LEVEL)
            root_logger.addHandler(graylog_handler)

            root_logger.info(
                "Greylog logging enabled",
                extra={
                    "event_type": "observability_startup",
                    "service_name": "formdev-api",
                    "app_env": settings.APP_ENV,
                    "graylog_host": settings.GRAYLOG_HOST,
                    "graylog_port": settings.GRAYLOG_PORT,
                    "graylog_facility": settings.GRAYLOG_FACILITY,
                },
            )
        except Exception as e:
            root_logger.warning("Unable to enable Greylog logging: %s", str(e))

    # Évite de polluer Greylog avec chaque appel HTTP interne vers vLLM.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _get_remote_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return "-"


def _get_user_agent(request: Request) -> str:
    user_agent = request.headers.get("user-agent") or "-"
    return user_agent[:300]


async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "-")

    path = request.url.path
    logger.exception(
        "unhandled exception",
        extra={
            "event_type": "http_exception",
            "service_name": "formdev-api",
            "app_env": settings.APP_ENV,
            "request_id": req_id,
            "module": _module_from_path(path),
            "route_family": _route_family(path),
            "method": request.method,
            "path": path,
            "status_code": 500,
            "status_family": "5xx",
            "is_error": True,
            "error_type": exc.__class__.__name__,
            "remote_ip": _get_remote_ip(request),
            "user_agent": _get_user_agent(request),
        },
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    req_id = getattr(request.state, "request_id", "-")

    path = request.url.path
    logger.warning(
        "rate limit exceeded",
        extra={
            "event_type": "rate_limit",
            "service_name": "formdev-api",
            "app_env": settings.APP_ENV,
            "request_id": req_id,
            "module": _module_from_path(path),
            "route_family": _route_family(path),
            "method": request.method,
            "path": path,
            "status_code": 429,
            "status_family": "4xx",
            "is_error": True,
            "remote_ip": _get_remote_ip(request),
            "user_agent": _get_user_agent(request),
        },
    )

    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )


def add_request_id_middleware(app: FastAPI) -> None:
    """
    Middleware de traçage HTTP global.

    Une ligne de log structurée est envoyée pour chaque requête.
    """
    @app.middleware("http")
    async def request_trace_and_access_log(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        start = time.perf_counter()

        api_key = request.headers.get("x-api-key")
        client_id = KEY_TO_CLIENT.get(api_key) if api_key else None

        response = None

        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status_code = getattr(response, "status_code", "-") if response else "-"
            path = request.url.path
            family = _status_family(status_code)

            logger.log(
                _level_for_status(status_code),
                "request completed",
                extra={
                    "event_type": "http_request",
                    "service_name": "formdev-api",
                    "app_env": settings.APP_ENV,
                    "request_id": request.state.request_id,
                    "client_id": client_id or "-",
                    "module": _module_from_path(path),
                    "route_family": _route_family(path),
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                    "status_family": family,
                    "is_error": family in {"4xx", "5xx"},
                    "duration_ms": round(duration_ms, 1),
                    "latency_bucket": _latency_bucket(duration_ms),
                    "remote_ip": _get_remote_ip(request),
                    "user_agent": _get_user_agent(request),
                },
            )

            if response is not None:
                response.headers["X-Request-Id"] = request.state.request_id
