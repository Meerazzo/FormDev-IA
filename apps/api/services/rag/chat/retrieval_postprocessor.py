import re
from difflib import SequenceMatcher
from statistics import mean

from core.config import settings


class RagRetrievalPostProcessor:
    """
    Nettoie et améliore les résultats retournés par Qdrant avant de les envoyer au LLM.

    Objectifs :
    - filtrer les chunks trop faibles
    - éviter les doublons exacts
    - éviter les chunks trop similaires
    - limiter le nombre de chunks par source
    - limiter la taille totale du contexte
    - produire une confidence simple
    """

    def process(
        self,
        *,
        chunks: list[dict],
        requested_top_k: int,
        score_threshold: float | None = None,
    ) -> dict:
        initial_count = len(chunks)
        effective_threshold = (
            score_threshold
            if score_threshold is not None
            else settings.RAG_MIN_RELEVANT_SCORE
        )

        filtered = [
            chunk for chunk in chunks
            if chunk.get("score") is not None and chunk["score"] >= effective_threshold
        ]

        filtered.sort(key=lambda item: item.get("score") or 0.0, reverse=True)

        selected = self._select_diverse_chunks(
            chunks=filtered,
            requested_top_k=requested_top_k,
        )

        selected = self._apply_context_budget(selected)

        scores = [
            chunk.get("score")
            for chunk in selected
            if chunk.get("score") is not None
        ]

        top_score = max(scores) if scores else None
        average_score = mean(scores) if scores else None

        return {
            "chunks": selected,
            "initial_candidates_count": initial_count,
            "filtered_candidates_count": len(filtered),
            "selected_chunks_count": len(selected),
            "score_threshold": effective_threshold,
            "top_score": top_score,
            "average_score": average_score,
            "retrieval_confidence": self._compute_confidence(
                top_score=top_score,
                selected_chunks_count=len(selected),
            ),
        }

    def _select_diverse_chunks(
        self,
        *,
        chunks: list[dict],
        requested_top_k: int,
    ) -> list[dict]:
        selected: list[dict] = []
        seen_chunk_keys: set[tuple[str | None, int | None]] = set()
        source_counts: dict[str, int] = {}

        for chunk in chunks:
            source_id = chunk.get("source_id")
            chunk_index = chunk.get("chunk_index")
            chunk_key = (source_id, chunk_index)

            if chunk_key in seen_chunk_keys:
                continue

            if source_id:
                count_for_source = source_counts.get(source_id, 0)
                if count_for_source >= settings.RAG_MAX_CHUNKS_PER_SOURCE:
                    continue

            if self._is_too_similar_to_selected(chunk, selected):
                continue

            selected.append(self._trim_chunk_text(chunk))
            seen_chunk_keys.add(chunk_key)

            if source_id:
                source_counts[source_id] = source_counts.get(source_id, 0) + 1

            if len(selected) >= requested_top_k:
                break

        return selected

    def _is_too_similar_to_selected(
        self,
        chunk: dict,
        selected: list[dict],
    ) -> bool:
        text = self._fingerprint(chunk.get("text") or "")

        if not text:
            return True

        for existing in selected:
            existing_text = self._fingerprint(existing.get("text") or "")

            if not existing_text:
                continue

            similarity = SequenceMatcher(None, text, existing_text).ratio()

            if similarity >= settings.RAG_DEDUP_TEXT_SIMILARITY:
                return True

        return False

    def _apply_context_budget(self, chunks: list[dict]) -> list[dict]:
        selected: list[dict] = []
        total_chars = 0

        for chunk in chunks:
            text = chunk.get("text") or ""
            next_total = total_chars + len(text)

            if selected and next_total > settings.RAG_MAX_CONTEXT_CHARS:
                break

            selected.append(chunk)
            total_chars = next_total

        return selected

    def _trim_chunk_text(self, chunk: dict) -> dict:
        text = chunk.get("text") or ""

        if len(text) <= settings.RAG_MAX_SOURCE_TEXT_CHARS:
            return chunk

        trimmed = {
            **chunk,
            "text": text[: settings.RAG_MAX_SOURCE_TEXT_CHARS].rstrip() + "...",
        }

        metadata = dict(trimmed.get("metadata") or {})
        metadata["text_trimmed_for_context"] = True
        metadata["original_text_length"] = len(text)
        metadata["trimmed_text_length"] = len(trimmed["text"])
        trimmed["metadata"] = metadata

        return trimmed

    def _fingerprint(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"section\s+\d+", "section", text)
        text = re.sub(r"\d+", "0", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        return text[:1000]

    def _compute_confidence(
        self,
        *,
        top_score: float | None,
        selected_chunks_count: int,
    ) -> str:
        if top_score is None or selected_chunks_count == 0:
            return "none"

        if top_score >= 0.52:
            return "high"

        if top_score >= 0.45:
            return "medium"

        return "low"
