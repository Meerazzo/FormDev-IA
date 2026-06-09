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
from routers.surveys import router as surveys_router
from routers.rag import router as rag_router


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
    description="""
    API d'inférence et d'analyse de questionnaires pour FormDev.

    Fonctionnalités principales :
    - génération / reformulation de texte via `/v1/chat`
    - analyse asynchrone de formulaires de satisfaction via `/surveys/forms/analyze`
    - suivi de traitement via `/surveys/processings/{processing_id}`
    - validation opérateur et apprentissage progressif via `/surveys/feedback`

    L'API s'appuie sur :
    - vLLM pour l'inférence LLM
    - PostgreSQL pour le stockage métier
    - Qdrant pour la mémoire vectorielle des exemples validés
    """,
    )


    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler) # Activation du rate limiter global (SlowAPI)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    add_request_id_middleware(app)
    # Enregistrement des routes exposées par l'API gateway
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(surveys_router)
    app.include_router(rag_router)
    #app.include_router(content_router)

    return app

app = create_app()