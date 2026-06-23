import html
import re
from html.parser import HTMLParser

import mammoth

from services.rag.ingestion.parsers.base import BaseParser, ParsedDocument


class _MammothHtmlToMarkdownParser(HTMLParser):
    """
    Convertisseur HTML Mammoth -> texte Markdown léger.

    Objectifs :
    - garder les titres avec # / ## / ### ;
    - garder les listes avec "- " ;
    - convertir les tableaux en lignes "cellule | cellule" ;
    - supprimer le HTML sans perdre la structure utile au RAG.
    """

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

        self.current_heading_level: int | None = None
        self.in_list_item = False

        self.in_table_cell = False
        self.current_cell_parts: list[str] = []
        self.current_row: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._newline()
            self.current_heading_level = int(tag[1])
            self.parts.append("#" * min(self.current_heading_level, 6))
            self.parts.append(" ")
            return

        if tag == "p":
            self._newline()
            return

        if tag == "br":
            self._newline()
            return

        if tag == "li":
            self._newline()
            self.in_list_item = True
            self.parts.append("- ")
            return

        if tag == "tr":
            self.current_row = []
            return

        if tag in {"td", "th"}:
            self.in_table_cell = True
            self.current_cell_parts = []
            return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.current_heading_level = None
            self._newline()
            return

        if tag == "p":
            self._newline()
            return

        if tag == "li":
            self.in_list_item = False
            self._newline()
            return

        if tag in {"td", "th"}:
            cell_text = self._clean_inline_text("".join(self.current_cell_parts))
            if self.current_row is not None:
                self.current_row.append(cell_text)
            self.current_cell_parts = []
            self.in_table_cell = False
            return

        if tag == "tr":
            if self.current_row:
                row = [cell for cell in self.current_row if cell]
                if row:
                    self._newline()
                    self.parts.append(" | ".join(row))
                    self._newline()
            self.current_row = None
            return

        if tag in {"table", "ul", "ol"}:
            self._newline()
            return

    def handle_data(self, data: str) -> None:
        if not data:
            return

        data = html.unescape(data)

        if self.in_table_cell:
            self.current_cell_parts.append(data)
        else:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)

    def _newline(self) -> None:
        if not self.parts:
            return
        if not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def _clean_inline_text(self, text: str) -> str:
        text = html.unescape(text or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class DocxParser(BaseParser):
    """
    Parser DOCX basé sur Mammoth.

    Mammoth convertit le DOCX en HTML sémantique, puis on transforme ce HTML
    en texte Markdown léger pour améliorer le RAG :
    - titres conservés ;
    - listes conservées ;
    - tableaux convertis en lignes lisibles.
    """

    def parse(self, file_path: str) -> ParsedDocument:
        with open(file_path, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file)

        html_content = result.value or ""
        text = self._html_to_markdown_text(html_content)

        if not text:
            raise ValueError("Aucun texte exploitable extrait du DOCX avec Mammoth")

        messages = [str(message) for message in result.messages]

        metadata = {
            "parser": "mammoth",
            "html_chars": len(html_content),
            "messages": messages,
            "headings_count": sum(
                1 for line in text.splitlines() if line.strip().startswith("#")
            ),
            "table_like_lines_count": sum(
                1 for line in text.splitlines() if "|" in line
            ),
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

    def _html_to_markdown_text(self, html_content: str) -> str:
        parser = _MammothHtmlToMarkdownParser()
        parser.feed(html_content)
        parser.close()

        text = parser.get_text()

        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()
