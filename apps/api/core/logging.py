from __future__ import annotations

import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from core.config import settings
LOG_LEVEL = settings.LOG_LEVEL.upper()
from core.security import KEY_TO_CLIENT


logger = logging.getLogger("formdev_ia_api")


def setup_logging() -> None:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(message)s",
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "-")
    logger.exception("Erreur non gérée request_id=%s path=%s", req_id, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


def add_request_id_middleware(app: FastAPI) -> None:
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

            if "response" in locals():
                response.headers["X-Request-Id"] = request.state.request_id