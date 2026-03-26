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
#from projects.contentSuggest.router import router as content_router  # projet 2

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

    Cette API permet d'interroger un modèle de langage local via une interface
    compatible avec les formats de conversation modernes.

    Principe d'utilisation :

    - envoyer une liste de messages structurés (system / user / assistant)
    - le modèle génère une réponse en fonction de ces messages

    Structure des rôles :

    • **system** : instructions générales données au modèle  
    • **user** : question ou demande envoyée par l'utilisateur  
    • **assistant** : réponse précédente du modèle (optionnel, pour maintenir un contexte)

    Exemple simple :

    system → définit le comportement du modèle  
    user → pose la question  
    assistant → réponse générée par l'IA
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
    #app.include_router(content_router)

    return app

app = create_app()