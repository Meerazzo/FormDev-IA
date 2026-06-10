import fitz

from services.rag.ingestion.parsers.base import BaseParser, ParsedDocument


class PdfParser(BaseParser):
    def parse(self, file_path: str) -> ParsedDocument:
        pages: list[dict] = []
        full_text_parts: list[str] = []

        with fitz.open(file_path) as document:
            for page_index, page in enumerate(document, start=1):
                text = page.get_text("text") or ""
                text = text.strip()

                if not text:
                    continue

                pages.append(
                    {
                        "page": page_index,
                        "text": text,
                    }
                )
                full_text_parts.append(text)

            metadata = {
                "parser": "pdf",
                "page_count": document.page_count,
                "title": document.metadata.get("title"),
                "author": document.metadata.get("author"),
            }

        return ParsedDocument(
            text="\n\n".join(full_text_parts),
            pages=pages,
            metadata=metadata,
        )
