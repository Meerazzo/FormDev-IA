"""Router principal du projet Chat IA.

Facade de compatibilité : la logique HTTP historique reste dans `chat_proxy.py`.
Ce package donne déjà une entrée d'architecture par projet et pourra ensuite
être découpé en `routes.py`, `examples.py` et `helpers.py` sans changer `main.py`.
"""

from routers.chat_proxy import router

__all__ = ["router"]
