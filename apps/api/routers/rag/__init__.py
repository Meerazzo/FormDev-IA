"""Router principal du projet RAG documentaire.

Le module agrège des sous-routers courts pour éviter un fichier HTTP unique
contenant toutes les responsabilités RAG.
"""

from fastapi import APIRouter

from .chat import router as chat_router
from .conversations import router as conversations_router
from .corpora import router as corpora_router
from .health import router as health_router
from .jobs import router as jobs_router
from .search import router as search_router
from .sources import router as sources_router

router = APIRouter()

# Ordre volontaire : les routes fixes /sources/url doivent être enregistrées
# avant les routes paramétrées /sources/{source_id}.
router.include_router(health_router)
router.include_router(sources_router)
router.include_router(corpora_router)
router.include_router(search_router)
router.include_router(conversations_router)
router.include_router(chat_router)
router.include_router(jobs_router)
