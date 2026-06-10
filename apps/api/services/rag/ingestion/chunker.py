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
    """
    Chunker RAG basé sur les caractères.

    Objectifs :
    - nettoyer le texte extrait
    - découper en chunks de taille contrôlée
    - appliquer un vrai overlap
    - essayer de couper sur des fins de phrases ou paragraphes
    - conserver des métadonnées utiles pour Qdrant
    """

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP

        if self.chunk_size <= 0:
            raise ValueError("RAG_CHUNK_SIZE doit être supérieur à 0")

        if self.chunk_overlap < 0:
            raise ValueError("RAG_CHUNK_OVERLAP ne peut pas être négatif")

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP doit être inférieur à RAG_CHUNK_SIZE")

    def chunk_pages(self, pages: list[dict]) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        global_chunk_index = 0

        for page in pages:
            page_number = page.get("page")
            raw_text = page.get("text") or ""
            text = self._clean_text(raw_text)

            if not text:
                continue

            page_chunks = self._chunk_text_with_offsets(text)

            for local_chunk_index, chunk_data in enumerate(page_chunks):
                chunk_text, char_start, char_end = chunk_data

                chunks.append(
                    RagChunk(
                        text=chunk_text,
                        chunk_index=global_chunk_index,
                        page=page_number,
                        metadata={
                            "page": page_number,
                            "local_chunk_index": local_chunk_index,
                            "char_start": char_start,
                            "char_end": char_end,
                            "chunk_char_length": len(chunk_text),
                            "source_text_char_length": len(text),
                            "chunk_size": self.chunk_size,
                            "chunk_overlap": self.chunk_overlap,
                        },
                    )
                )

                global_chunk_index += 1

        return chunks

    def _clean_text(self, text: str) -> str:
        text = text.replace("\x00", " ")

        # Normalisation espaces horizontaux
        text = re.sub(r"[ \t]+", " ", text)

        # Nettoyage des espaces autour des retours ligne
        text = re.sub(r" *\n *", "\n", text)

        # Limiter les sauts de ligne excessifs
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _chunk_text_with_offsets(self, text: str) -> list[tuple[str, int, int]]:
        if len(text) <= self.chunk_size:
            return [(text, 0, len(text))]

        chunks: list[tuple[str, int, int]] = []
        text_length = len(text)
        start = 0

        while start < text_length:
            max_end = min(start + self.chunk_size, text_length)
            end = max_end

            if max_end < text_length:
                end = self._find_best_cut(text, start, max_end)

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append((chunk_text, start, end))

            if end >= text_length:
                break

            # Vrai overlap : le prochain chunk reprend la fin du précédent.
            next_start = end - self.chunk_overlap

            # Sécurité anti-boucle infinie.
            if next_start <= start:
                next_start = end

            start = self._adjust_start_to_word_boundary(text, next_start, end)

            # Éviter de commencer par des espaces ou retours ligne.
            while start < text_length and text[start].isspace():
                start += 1

        return chunks

    def _find_best_cut(self, text: str, start: int, max_end: int) -> int:
        window = text[start:max_end]

        separators = [
            "\n\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ": ",
            "\n",
        ]

        best_cut = -1

        for separator in separators:
            cut = window.rfind(separator)
            if cut > best_cut:
                best_cut = cut

        # On accepte une coupe propre seulement si elle n'est pas trop tôt.
        min_acceptable_cut = int(self.chunk_size * 0.55)

        if best_cut >= min_acceptable_cut:
            return start + best_cut + 1

        # Sinon, fallback : essayer de couper sur le dernier espace.
        space_cut = window.rfind(" ")

        if space_cut >= min_acceptable_cut:
            return start + space_cut

        # Dernier fallback : coupe brute.
        return max_end
    
    def _adjust_start_to_word_boundary(self, text: str, start: int, previous_end: int) -> int:
        """
        Évite de commencer un chunk au milieu d'un mot.

        On avance jusqu'au prochain séparateur proche.
        Si aucun séparateur n'est trouvé rapidement, on garde le start initial.
        """
        if start <= 0 or start >= len(text):
            return start

        if text[start].isspace():
            return start

        max_shift = min(start + 40, previous_end, len(text))

        for index in range(start, max_shift):
            if text[index].isspace():
                return index + 1

        return start
