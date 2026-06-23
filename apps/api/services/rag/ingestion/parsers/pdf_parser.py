import inspect
import re
from collections.abc import Mapping

import fitz
import pymupdf4llm

from core.config import settings
from services.rag.ingestion.parsers.base import BaseParser, ParsedDocument


class PdfParser(BaseParser):
    """
    Parser PDF basé sur PyMuPDF4LLM.

    Objectifs :
    - extraire un Markdown plus structuré que page.get_text("text") ;
    - conserver la notion de page avec page_chunks=True ;
    - désactiver les images ;
    - préparer l'activation OCR via RAG_PDF_USE_OCR.
    """

    def parse(self, file_path: str) -> ParsedDocument:
        metadata = self._read_pdf_metadata(file_path)
        pages = self._parse_pages_with_pymupdf4llm(file_path)

        if not pages:
            raise ValueError("Aucun texte exploitable extrait du PDF avec PyMuPDF4LLM")

        full_text = "\n\n".join(page["text"] for page in pages if page.get("text"))

        metadata.update(
            {
                "parser": "pymupdf4llm",
                "ocr_enabled": settings.RAG_PDF_USE_OCR,
                "pages_with_text": len(pages),
            }
        )

        return ParsedDocument(
            text=full_text,
            pages=pages,
            metadata=metadata,
        )

    def _parse_pages_with_pymupdf4llm(self, file_path: str) -> list[dict]:
        kwargs = self._build_to_markdown_kwargs()

        markdown_pages = pymupdf4llm.to_markdown(
            file_path,
            **kwargs,
        )

        if isinstance(markdown_pages, str):
            text = self._clean_markdown(markdown_pages)
            return [{"page": None, "text": text}] if text else []

        pages: list[dict] = []

        for index, item in enumerate(markdown_pages, start=1):
            page_number = index
            text = ""

            # PyMuPDF4LLM retourne des defaultdict, donc on teste Mapping
            # plutôt que dict strict.
            if isinstance(item, Mapping):
                item_metadata = item.get("metadata") or {}

                page_number = (
                    item.get("page")
                    or item.get("page_number")
                    or item_metadata.get("page")
                    or item_metadata.get("page_number")
                    or index
                )

                text = (
                    item.get("text")
                    or item.get("markdown")
                    or item.get("content")
                    or ""
                )
            else:
                text = str(item)

            text = self._clean_markdown(text)

            if text:
                pages.append(
                    {
                        "page": page_number,
                        "text": text,
                    }
                )

        return pages

    def _build_to_markdown_kwargs(self) -> dict:
        signature = inspect.signature(pymupdf4llm.to_markdown)
        supported_params = set(signature.parameters)

        kwargs = {
            "page_chunks": True,
            "write_images": False,
            "embed_images": False,
        }

        if "ignore_images" in supported_params:
            kwargs["ignore_images"] = True

        if settings.RAG_PDF_USE_OCR:
            if "use_ocr" in supported_params:
                kwargs["use_ocr"] = True
            else:
                raise RuntimeError(
                    "RAG_PDF_USE_OCR=true mais la version installée de pymupdf4llm "
                    "ne supporte pas le paramètre use_ocr."
                )

        return kwargs

    def _clean_markdown(self, text: str) -> str:
        text = text or ""

        # Supprime les messages d'images omises générés par PyMuPDF4LLM.
        text = re.sub(
            r"\*\*==>\s*picture\s*\[[^\n]+\]\s*intentionally omitted\s*<==\*\*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = text.replace("\x00", " ")

        # Nettoyage léger, en gardant la structure Markdown.
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _read_pdf_metadata(self, file_path: str) -> dict:
        with fitz.open(file_path) as document:
            return {
                "page_count": document.page_count,
                "title": document.metadata.get("title"),
                "author": document.metadata.get("author"),
            }
