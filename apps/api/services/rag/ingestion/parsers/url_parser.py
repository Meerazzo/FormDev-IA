import httpx
import trafilatura
from bs4 import BeautifulSoup

from services.rag.ingestion.parsers.base import ParsedDocument


class UrlParser:
    """
    Parser URL pour le RAG.

    Stratégie :
    1. Télécharger la page avec httpx.
    2. Extraire le contenu principal avec trafilatura.
    3. Si trafilatura échoue, fallback avec BeautifulSoup.
    """

    def parse_url(self, url: str) -> ParsedDocument:
        response = httpx.get(
            url,
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "FormDev-RAG/1.0",
            },
        )
        response.raise_for_status()

        html = response.text

        text = trafilatura.extract(
            html,
            url=str(response.url),
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )

        parser_used = "trafilatura"

        if not text or not text.strip():
            text = self._fallback_extract(html)
            parser_used = "beautifulsoup_fallback"

        text = (text or "").strip()

        if not text:
            raise ValueError("Aucun texte exploitable n'a pu être extrait de cette URL")

        title = self._extract_title(html)

        return ParsedDocument(
            text=text,
            pages=[
                {
                    "page": None,
                    "text": text,
                }
            ],
            metadata={
                "parser": "url",
                "extractor": parser_used,
                "url": url,
                "final_url": str(response.url),
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "title": title,
            },
        )

    def _fallback_extract(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        return soup.get_text(separator="\n", strip=True)

    def _extract_title(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return None
