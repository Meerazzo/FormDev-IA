"""
Point d'entrée de l'API FormDev IA.

Ce module construit l'application FastAPI et assemble les différents
composants transverses :

- configuration du logging
- middleware de traçabilité des requêtes
- gestion centralisée des erreurs
- rate limiting
- enregistrement des routers métier

L'application agit comme une gateway entre les clients FormDev et
les services d'inférence IA.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
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
from routers.surveys import router as surveys_router
from routers.rag import router as rag_router

OPENAPI_DESCRIPTION = """
API FormDev IA exposant trois modules principaux :

- **Chat IA** : génération, reformulation et transformation de texte via `POST /v1/chat`.
- **Surveys** : analyse asynchrone de questionnaires et feedback opérateur via `/surveys/*`.
- **RAG documentaire** : ingestion de sources, indexation Qdrant, recherche sémantique et chat sourcé via `/rag/*`.

L'authentification des routes métier se fait via le header `X-API-Key`.
La route `GET /health` reste disponible pour les vérifications techniques simples.
"""

OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "System", "description": "Routes transverses de santé et de supervision de l'API."},
    {"name": "Chat", "description": "Génération, reformulation et transformation de texte via le modèle LLM."},
    {"name": "Surveys", "description": "Analyse de questionnaires, suivi de traitement et feedback opérateur."},
    {"name": "RAG - Health", "description": "Diagnostic du module RAG, de Qdrant et des paramètres d'embedding."},
    {"name": "RAG - Sources", "description": "Création, ingestion, indexation, réindexation et suppression de sources documentaires."},
    {"name": "RAG - Corpora", "description": "Gestion des corpus documentaires par client."},
    {"name": "RAG - Search", "description": "Recherche sémantique dans les chunks indexés."},
    {"name": "RAG - Chat", "description": "Chat RAG synchrone ou streaming à partir des documents indexés."},
    {"name": "RAG - Conversations", "description": "Création, consultation, modification et suppression des conversations RAG."},
    {"name": "RAG - Jobs", "description": "Suivi des jobs asynchrones d'ingestion, d'indexation, de réindexation et de resynchronisation."},
]

DEFAULT_ERROR_RESPONSES: dict[str, dict[str, str]] = {
    "400": {"description": "Requête invalide ou paramètre métier incorrect"},
    "401": {"description": "Clé API absente ou invalide"},
    "404": {"description": "Ressource introuvable"},
    "409": {"description": "Conflit métier, par exemple source déjà existante"},
    "422": {"description": "Erreur de validation du payload ou des paramètres"},
    "429": {"description": "Limite de requêtes atteinte"},
    "500": {"description": "Erreur interne inattendue"},
    "502": {"description": "Erreur d'un service aval : vLLM, Qdrant, Redis/RQ ou stockage"},
}

OPERATION_ID_OVERRIDES: dict[tuple[str, str], str] = {
    ("GET", "/health"): "system_health",
    ("POST", "/v1/chat"): "chat_create_completion",
    ("POST", "/surveys/analyze"): "surveys_analyze",
    ("GET", "/surveys/processings/{processing_id}"): "surveys_get_processing_status",
    ("POST", "/surveys/feedback"): "surveys_save_feedback",
    ("GET", "/surveys/feedback"): "surveys_list_feedback",
    ("GET", "/rag/health"): "rag_health",
    ("POST", "/rag/search"): "rag_search",
    ("POST", "/rag/chat"): "rag_chat",
    ("POST", "/rag/chat/stream"): "rag_chat_stream",
}


def _tag_for_path(path: str, current_tags: list[str] | None) -> list[str]:
    if path == "/health":
        return ["System"]
    if path == "/v1/chat":
        return ["Chat"]
    if path.startswith("/surveys"):
        return ["Surveys"]
    if path == "/rag/health":
        return ["RAG - Health"]
    if path.startswith("/rag/jobs"):
        return ["RAG - Jobs"]
    if path.startswith("/rag/corpora"):
        return ["RAG - Corpora"]
    if path.startswith("/rag/conversations"):
        return ["RAG - Conversations"]
    if path.startswith("/rag/chat"):
        return ["RAG - Chat"]
    if path.startswith("/rag/search"):
        return ["RAG - Search"]
    if path.startswith("/rag/sources"):
        return ["RAG - Sources"]
    return current_tags or ["System"]


def _operation_id(method: str, path: str) -> str:
    override = OPERATION_ID_OVERRIDES.get((method.upper(), path))
    if override:
        return override

    normalized_path = (
        path.strip("/")
        .replace("{", "")
        .replace("}", "")
        .replace("-", "_")
        .replace("/", "_")
    )
    return f"{method.lower()}_{normalized_path}" if normalized_path else method.lower()


def _find_api_key_scheme_name(security_schemes: dict[str, Any]) -> str | None:
    for scheme_name, scheme in security_schemes.items():
        if not isinstance(scheme, dict):
            continue
        if (
            scheme.get("type") == "apiKey"
            and scheme.get("in") == "header"
            and scheme.get("name") == "X-API-Key"
        ):
            return scheme_name
    return None


def install_custom_openapi(app: FastAPI) -> None:
    """Installe une couche de finition OpenAPI sans modifier la logique des routers."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=OPENAPI_TAGS,
        )

        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        api_key_scheme_name = _find_api_key_scheme_name(security_schemes)
        if api_key_scheme_name:
            security_schemes[api_key_scheme_name]["description"] = (
                "Clé API client FormDev. À fournir sur les routes métier via le header X-API-Key."
            )

        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.lower() not in {"get", "post", "patch", "delete", "put"}:
                    continue

                http_method = method.upper()
                operation["tags"] = _tag_for_path(path, operation.get("tags"))
                operation["operationId"] = _operation_id(http_method, path)

                responses = operation.setdefault("responses", {})
                for code, response in DEFAULT_ERROR_RESPONSES.items():
                    responses.setdefault(code, response)

                if path != "/health" and api_key_scheme_name:
                    operation["security"] = [{api_key_scheme_name: []}]

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi


def create_app() -> FastAPI:
    """
    Factory de création de l'application FastAPI.

    L'utilisation d'une factory permet :
    - de centraliser l'initialisation
    - de faciliter les tests
    - d'éviter les effets de bord à l'import
    """
    setup_logging()
    app = FastAPI(
        title="FormDev IA API",
        version="1.0.0",
        description=OPENAPI_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        redoc_url=None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)  # Activation du rate limiter global (SlowAPI)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    add_request_id_middleware(app)
    # Enregistrement des routes exposées par l'API gateway
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(surveys_router)
    app.include_router(rag_router)
    # app.include_router(content_router)

    install_custom_openapi(app)
    return app


app = create_app()
