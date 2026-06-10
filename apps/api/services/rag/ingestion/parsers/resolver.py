from pathlib import Path

from services.rag.ingestion.parsers.base import BaseParser
from services.rag.ingestion.parsers.pdf_parser import PdfParser
from services.rag.ingestion.parsers.txt_parser import TxtParser


class ParserResolver:
    @staticmethod
    def get_parser(file_path: str, source_type: str | None = None) -> BaseParser:
        suffix = Path(file_path).suffix.lower()

        if source_type == "pdf" or suffix == ".pdf":
            return PdfParser()

        if source_type == "txt" or suffix == ".txt":
            return TxtParser()

        raise ValueError(f"Type de fichier non supporté pour l'instant: {source_type or suffix}")
