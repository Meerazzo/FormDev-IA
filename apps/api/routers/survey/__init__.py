"""Router principal du projet Surveys.

Facade de compatibilité : les routes historiques restent dans `surveys.py`.
Le package donne une entrée d'architecture par projet et isole les futurs
fichiers `routes.py`, `examples.py` et `helpers.py`.
"""

from routers.surveys import router

__all__ = ["router"]
