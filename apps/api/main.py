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
    title="FormDev IA - Gateway",
    description="""
    API gateway pour les services d'intelligence artificielle de FormDev.

    Cette API permet aujourd'hui deux grands usages :

    ### 1. Génération / transformation de texte via `/v1/chat`
    - reformulation
    - synthèse
    - enrichissement de contenu
    - génération encadrée en français professionnel et pédagogique

    ### 2. Analyse de questionnaires via `/surveys/analyze`
    - segmentation d'une réponse ouverte en plusieurs points
    - classification par sentiment
    - catégorisation métier
    - stockage des résultats en base de données

    ### Sécurité
    Les routes exposées sont protégées par clé API et soumises au rate limiting.

    ### Principe général
    L'application agit comme une gateway entre les clients FormDev,
    le serveur d'inférence vLLM et la base PostgreSQL de journalisation / stockage métier.
    """,
        version="1.0",
    )


    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler) # Activation du rate limiter global (SlowAPI)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    add_request_id_middleware(app)
    # Enregistrement des routes exposées par l'API gateway
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(surveys_router)
    #app.include_router(content_router)

    return app

app = create_app()