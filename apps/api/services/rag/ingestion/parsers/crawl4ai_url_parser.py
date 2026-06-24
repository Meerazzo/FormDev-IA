from __future__ import annotations

import asyncio
import threading
from typing import Any

from services.rag.ingestion.parsers.base import ParsedDocument
from services.rag.ingestion.web_cleaning.light_markdown_cleaner import LightMarkdownCleaner


class Crawl4AIUrlParser:
    """
    Parser URL basé sur Crawl4AI.

    Choix volontaire :
    - utiliser raw_markdown, pas fit_markdown ;
    - demander à Crawl4AI de limiter les liens/images au moment de la génération ;
    - appliquer seulement un nettoyage conservateur ;
    - préserver les URLs restantes.
    """

    def __init__(self) -> None:
        self.cleaner = LightMarkdownCleaner()

    def parse_url(self, url: str) -> ParsedDocument:
        crawl_payload = self._run_async(self._crawl(url))

        if not crawl_payload["success"]:
            raise ValueError(
                f"Erreur Crawl4AI sur l'URL {url}: "
                f"{crawl_payload.get('error') or 'erreur inconnue'}"
            )

        raw_markdown = crawl_payload["raw_markdown"]

        if not raw_markdown.strip():
            raise ValueError(f"Crawl4AI n'a extrait aucun Markdown exploitable pour l'URL {url}")

        cleaned = self.cleaner.clean(raw_markdown)
        text = cleaned.text

        if not text:
            raise ValueError(f"Aucun texte exploitable après nettoyage Crawl4AI pour l'URL {url}")

        metadata = {
            "parser": "url",
            "extractor": "crawl4ai_raw_markdown",
            "url": url,
            "final_url": crawl_payload.get("final_url") or url,
            "status_code": crawl_payload.get("status_code"),
            "crawl4ai_success": crawl_payload["success"],
            "crawl4ai_raw_char_length": len(raw_markdown),
            "crawl4ai_fit_char_length": len(crawl_payload.get("fit_markdown") or ""),
            "crawl4ai_fit_markdown_used": False,
            "light_cleaning_enabled": True,
            **cleaned.metadata,
        }

        return ParsedDocument(
            text=text,
            pages=[
                {
                    "page": None,
                    "text": text,
                }
            ],
            metadata=metadata,
        )

    async def _crawl(self, url: str) -> dict[str, Any]:
        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
            from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
        except ImportError as exc:
            raise RuntimeError(
                "Crawl4AI n'est pas installé. Installez crawl4ai ou repassez "
                "RAG_URL_PARSER_BACKEND=basic."
            ) from exc

        config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                options={
                    "ignore_links": True,
                    "ignore_images": True,
                    "skip_internal_links": True,
                    "body_width": 0,
                },
            )
        )

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=config)

        raw_markdown, fit_markdown = self._get_markdown_variants(result.markdown)

        return {
            "success": bool(getattr(result, "success", False)),
            "status_code": getattr(result, "status_code", None),
            "final_url": getattr(result, "url", None) or url,
            "error": getattr(result, "error_message", None),
            "raw_markdown": raw_markdown,
            "fit_markdown": fit_markdown,
        }

    def _get_markdown_variants(self, markdown_obj: Any) -> tuple[str, str]:
        raw = getattr(markdown_obj, "raw_markdown", None)
        fit = getattr(markdown_obj, "fit_markdown", None)

        internal = getattr(markdown_obj, "_markdown_result", None)

        if raw is None and internal is not None:
            raw = getattr(internal, "raw_markdown", None)

        if fit is None and internal is not None:
            fit = getattr(internal, "fit_markdown", None)

        raw = raw or str(markdown_obj or "")
        fit = fit or ""

        return raw, fit

    def _run_async(self, coro):
        """
        Exécute une coroutine depuis un contexte synchrone.

        Cas RQ worker : pas d'event loop active → asyncio.run.
        Cas route FastAPI async : event loop active → exécution dans un thread dédié.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result_box = {}
        error_box = {}

        def runner() -> None:
            try:
                result_box["value"] = asyncio.run(coro)
            except Exception as exc:
                error_box["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()

        if "error" in error_box:
            raise error_box["error"]

        return result_box["value"]
