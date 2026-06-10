from services.rag.ingestion.parsers.base import BaseParser, ParsedDocument


class TxtParser(BaseParser):
    def parse(self, file_path: str) -> ParsedDocument:
        encodings = ["utf-8", "utf-8-sig", "latin-1"]

        last_error = None

        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as file:
                    text = file.read()

                return ParsedDocument(
                    text=text,
                    pages=[
                        {
                            "page": None,
                            "text": text,
                        }
                    ],
                    metadata={
                        "parser": "txt",
                        "encoding": encoding,
                    },
                )
            except UnicodeDecodeError as exc:
                last_error = exc

        raise ValueError(f"Impossible de lire le fichier TXT: {last_error}")
