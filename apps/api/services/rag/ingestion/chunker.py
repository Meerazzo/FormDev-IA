import re
from dataclasses import dataclass

from core.config import settings


@dataclass
class RagChunk:
    text: str
    chunk_index: int
    page: int | None
    metadata: dict


class RagChunker:
    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP doit être inférieur à RAG_CHUNK_SIZE")

    def chunk_pages(self, pages: list[dict]) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        chunk_index = 0

        for page in pages:
            page_number = page.get("page")
            text = self._clean_text(page.get("text") or "")

            if not text:
                continue

            page_chunks = self._chunk_text(text)

            for chunk_text in page_chunks:
                chunks.append(
                    RagChunk(
                        text=chunk_text,
                        chunk_index=chunk_index,
                        page=page_number,
                        metadata={},
                    )
                )
                chunk_index += 1

        return chunks

    def _clean_text(self, text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            # Essayer de couper proprement à la fin d'une phrase ou d'un paragraphe
            if end < len(text):
                best_cut = max(
                    chunk.rfind("\n\n"),
                    chunk.rfind(". "),
                    chunk.rfind("? "),
                    chunk.rfind("! "),
                )

                if best_cut > int(self.chunk_size * 0.5):
                    chunk = chunk[: best_cut + 1]
                    end = start + best_cut + 1

            chunk = chunk.strip()
            if chunk:
                chunks.append(chunk)

            start = max(end - self.chunk_overlap, end)

            if start >= len(text):
                break

        return chunks
