import re

import httpx
import trafilatura
from bs4 import BeautifulSoup

from services.rag.ingestion.parsers.base import ParsedDocument


class UrlParser:
    """
    Parser URL générique pour le RAG.

    Objectif :
    - extraire le texte principal d'une page web ;
    - préserver les titres utiles ;
    - transformer les tableaux HTML en texte structuré exploitable par le RAG ;
    - ajouter des indices génériques sur les valeurs détectées, sans règle métier spécifique.
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
        title = self._extract_title(html)

        main_text = trafilatura.extract(
            html,
            url=str(response.url),
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )

        parser_used = "trafilatura"

        if not main_text or not main_text.strip():
            main_text = self._fallback_extract(html)
            parser_used = "beautifulsoup_fallback"

        main_text = (main_text or "").strip()

        structured_tables = self._extract_structured_tables(html)
        structured_tables_text = "\n\n".join(structured_tables).strip()

        text_parts: list[str] = []

        if title:
            text_parts.append(f"Titre de la page : {title}")

        if main_text:
            text_parts.append(main_text)

        if structured_tables_text:
            text_parts.append(
                "Tableaux HTML structurés pour la recherche documentaire :\n"
                f"{structured_tables_text}"
            )

        text = self._clean_text("\n\n".join(text_parts))

        if not text:
            raise ValueError("Aucun texte exploitable n'a pu être extrait de cette URL")

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
                "structured_tables_enabled": True,
                "structured_tables_count": len(structured_tables),
                "text_char_length": len(text),
            },
        )

    def _extract_structured_tables(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        structured_tables: list[str] = []

        for table_index, table in enumerate(soup.find_all("table"), start=1):
            rows = self._extract_table_rows(table)

            if not rows:
                continue

            table_title = self._find_table_title(table) or f"Tableau {table_index}"

            headers, data_rows = self._split_headers_and_rows(rows)

            if not data_rows:
                continue

            max_columns = max(len(row["cells"]) for row in data_rows)

            if not headers:
                headers = [f"Colonne {index}" for index in range(1, max_columns + 1)]

            if len(headers) < max_columns:
                headers = headers + [
                    f"Colonne {index}"
                    for index in range(len(headers) + 1, max_columns + 1)
                ]

            table_lines = [
                f"Tableau HTML détecté : {table_title}",
                "Colonnes détectées : " + " | ".join(headers),
            ]

            for row_index, row in enumerate(data_rows, start=1):
                cells = row["cells"]

                if not cells:
                    continue

                joined_row = " | ".join(cells)
                table_lines.append(f"Ligne {row_index} du tableau :")

                for cell_index, cell in enumerate(cells):
                    column_name = headers[cell_index] if cell_index < len(headers) else f"Colonne {cell_index + 1}"
                    table_lines.append(f"- {column_name} : {cell}")

                value_hints = self._extract_generic_value_hints(joined_row)

                for hint in value_hints:
                    table_lines.append(f"- Indice générique : {hint}")

            structured_tables.append("\n".join(table_lines))

        return structured_tables

    def _extract_table_rows(self, table) -> list[dict]:
        rows: list[dict] = []

        for tr in table.find_all("tr"):
            cells = []
            has_header_cell = False

            for cell in tr.find_all(["th", "td"]):
                if cell.name == "th":
                    has_header_cell = True

                cell_text = cell.get_text(separator=" ", strip=True)
                cell_text = self._clean_inline_text(cell_text)

                if cell_text:
                    cells.append(cell_text)

            if cells:
                rows.append(
                    {
                        "cells": cells,
                        "is_header": has_header_cell,
                    }
                )

        return rows

    def _split_headers_and_rows(self, rows: list[dict]) -> tuple[list[str], list[dict]]:
        if not rows:
            return [], []

        first_row = rows[0]

        if first_row.get("is_header"):
            return first_row["cells"], rows[1:]

        return [], rows

    def _find_table_title(self, table) -> str | None:
        caption = table.find("caption")

        if caption:
            caption_text = self._clean_inline_text(caption.get_text(" ", strip=True))

            if caption_text:
                return caption_text

        previous_heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])

        if previous_heading:
            heading_text = self._clean_inline_text(previous_heading.get_text(" ", strip=True))

            if heading_text:
                return heading_text

        return None

    def _extract_generic_value_hints(self, text: str) -> list[str]:
        text = self._clean_inline_text(text)

        if not text:
            return []

        hints: list[str] = []
        seen: set[str] = set()

        def add_hint(value: str) -> None:
            value = self._clean_inline_text(value)

            if not value or value in seen:
                return

            seen.add(value)
            hints.append(value)

        currency_after_amount_pattern = re.compile(
            r"(?<!\w)(\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?)\s*(€|\$|£|EUR|USD|GBP|euros?|dollars?|livres?)",
            re.IGNORECASE,
        )

        for amount, currency in currency_after_amount_pattern.findall(text):
            add_hint(
                f"Valeur monétaire détectée : {self._normalize_number(amount)} {self._normalize_currency(currency)}"
            )

        currency_before_amount_pattern = re.compile(
            r"(€|\$|£|EUR|USD|GBP)\s*(\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?)",
            re.IGNORECASE,
        )

        for currency, amount in currency_before_amount_pattern.findall(text):
            add_hint(
                f"Valeur monétaire détectée : {self._normalize_number(amount)} {self._normalize_currency(currency)}"
            )

        percent_pattern = re.compile(
            r"(?<!\w)(\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?)\s*%",
            re.IGNORECASE,
        )

        for percent in percent_pattern.findall(text):
            add_hint(f"Pourcentage détecté : {self._normalize_number(percent)} %")

        unit_after_slash_pattern = re.compile(
            r"(?:€|\$|£|EUR|USD|GBP|euros?|dollars?|livres?)?\s*/\s*([A-Za-zÀ-ÿ0-9_.%-]+(?:\s*/\s*[A-Za-zÀ-ÿ0-9_.%-]+)*)",
            re.IGNORECASE,
        )

        for unit in unit_after_slash_pattern.findall(text):
            clean_unit = re.sub(r"\s*/\s*", "/", unit).strip()

            if clean_unit:
                add_hint(f"Unité détectée : {clean_unit}")

        email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        )

        for email in email_pattern.findall(text):
            add_hint(f"Email détecté : {email}")

        url_pattern = re.compile(
            r"https?://[^\s)>\"]+",
            re.IGNORECASE,
        )

        for url in url_pattern.findall(text):
            add_hint(f"URL détectée : {url}")

        number_pattern = re.compile(
            r"(?<![\w,.])\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?(?![\w,.])"
        )

        numbers = [
            self._normalize_number(number)
            for number in number_pattern.findall(text)
        ]

        for number in numbers[:5]:
            add_hint(f"Nombre détecté : {number}")

        return hints

    def _fallback_extract(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        parts: list[str] = []

        title = self._extract_title(html)

        if title:
            parts.append(f"Titre de la page : {title}")

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
            text = tag.get_text(separator=" ", strip=True)
            text = self._clean_inline_text(text)

            if text:
                parts.append(text)

        structured_tables = self._extract_structured_tables(html)

        if structured_tables:
            parts.append(
                "Tableaux HTML structurés pour la recherche documentaire :\n"
                + "\n\n".join(structured_tables)
            )

        if parts:
            return "\n\n".join(parts)

        return soup.get_text(separator="\n", strip=True)

    def _extract_title(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")

        if soup.title and soup.title.string:
            return self._clean_inline_text(soup.title.string)

        return None

    def _normalize_currency(self, currency: str) -> str:
        value = currency.strip().lower()

        if value in {"€", "eur", "euro", "euros"}:
            return "EUR"

        if value in {"$", "usd", "dollar", "dollars"}:
            return "USD"

        if value in {"£", "gbp", "livre", "livres"}:
            return "GBP"

        return currency.strip().upper()

    def _normalize_number(self, number: str) -> str:
        number = number.replace("\xa0", " ")
        number = re.sub(r"\s+", "", number)
        return number.strip()

    def _clean_inline_text(self, text: str) -> str:
        text = text.replace("\x00", " ")
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _clean_text(self, text: str) -> str:
        text = text.replace("\x00", " ")
        text = text.replace("\xa0", " ")

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()
