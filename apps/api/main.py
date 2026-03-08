from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from core.logging import (
    setup_logging,
    add_request_id_middleware,
    unhandled_exception_handler,
    rate_limit_handler,
)
from core.rate_limit import limiter
from routers.health import router as health_router
from routers.chat_proxy import router as chat_router
from projects.contentSuggest.router import router as content_router  # projet 2

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="FormDev IA - Gateway")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    add_request_id_middleware(app)

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(content_router)

    return app

app = create_app()