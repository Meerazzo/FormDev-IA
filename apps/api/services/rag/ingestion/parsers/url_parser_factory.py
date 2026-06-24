from __future__ import annotations

from core.config import settings
from services.rag.ingestion.parsers.base import ParsedDocument
from services.rag.ingestion.parsers.url_parser import UrlParser
from services.rag.ingestion.parsers.crawl4ai_url_parser import Crawl4AIUrlParser


def parse_url_document(url: str) -> ParsedDocument:
    """
    Résout le backend d'extraction URL.

    Modes :
    - basic : parser historique httpx/trafilatura/BeautifulSoup ;
    - crawl4ai : extraction navigateur Crawl4AI raw_markdown + nettoyage léger ;
    - auto : Crawl4AI puis fallback basic en cas d'erreur.
    """
    backend = (settings.RAG_URL_PARSER_BACKEND or "basic").strip().lower()

    if backend == "basic":
        return UrlParser().parse_url(url)

    if backend == "crawl4ai":
        return Crawl4AIUrlParser().parse_url(url)

    if backend == "auto":
        try:
            return Crawl4AIUrlParser().parse_url(url)
        except Exception as exc:
            document = UrlParser().parse_url(url)
            document.metadata = {
                **(document.metadata or {}),
                "url_parser_backend": "auto",
                "crawl4ai_fallback_error": str(exc),
            }
            return document

    raise ValueError(
        "RAG_URL_PARSER_BACKEND invalide. "
        "Valeurs acceptées: basic, crawl4ai, auto."
    )
