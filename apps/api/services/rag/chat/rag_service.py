import httpx
import re

from core.config import settings
from schemas.rag import RagChatResponse, RagChatSource
from services.rag.chat.prompt_builder import RagPromptBuilder
from services.rag.chat.retrieval_postprocessor import RagRetrievalPostProcessor
from services.rag.embeddings.local_embedding_service import get_local_embedding_service
from services.rag.vectorstore.rag_vector_store import RagVectorStore



STRICT_RAG_FALLBACK_ANSWER = (
    "Je ne dispose pas d'information suffisante dans les documents fournis "
    "pour répondre à cette question."
)
class RagService:
    """
    Service principal de réponse RAG.

    Étapes :
    1. Construit une requête de retrieval avec la question et l'historique court.
    2. Embed la requête.
    3. Recherche davantage de candidats dans Qdrant.
    4. Filtre et diversifie les chunks.
    5. Construit un prompt RAG strict.
    6. Appelle vLLM.
    7. Retourne réponse + sources + informations de retrieval.
    """


    def _has_enough_relevance(self, sources: list) -> bool:
        """Détermine si les sources retrouvées sont assez pertinentes pour répondre."""
        if not sources:
            return False

        scores = []

        for source in sources:
            score = None

            if isinstance(source, dict):
                score = source.get("score")
            else:
                score = getattr(source, "score", None)

            if score is not None:
                try:
                    scores.append(float(score))
                except (TypeError, ValueError):
                    continue

        if not scores:
            return False

        best_score = max(scores)

        return best_score >= settings.RAG_MIN_RELEVANT_SCORE

    def _build_strict_fallback_response(
        self,
        *,
        client_id: str,
        corpus_id: str,
        question: str,
        retrieval: dict,
    ) -> RagChatResponse:
        """Construit une réponse fallback quand le contexte documentaire est insuffisant."""
        return RagChatResponse(
            client_id=client_id,
            corpus_id=corpus_id,
            question=question,
            answer=STRICT_RAG_FALLBACK_ANSWER,
            sources=[],
            used_chunks_count=0,
            retrieval_confidence="low",
            top_score=retrieval.get("top_score"),
            retrieval_candidates_count=retrieval.get("initial_candidates_count", 0),
            filtered_chunks_count=retrieval.get("filtered_candidates_count", 0),
            metadata={
                "fallback": True,
                "fallback_reason": "insufficient_retrieval_score",
                "min_relevant_score": settings.RAG_MIN_RELEVANT_SCORE,
            },
        )


    def __init__(self) -> None:
        self.embedding_service = get_local_embedding_service()
        self.vector_store = RagVectorStore()
        self.prompt_builder = RagPromptBuilder()
        self.retrieval_postprocessor = RagRetrievalPostProcessor()

    def answer(
        self,
        *,
        client_id: str,
        corpus_id: str,
        question: str,
        top_k: int,
        score_threshold: float | None,
        temperature: float,
        max_tokens: int,
        conversation_history: list[dict] | None = None,
    ) -> RagChatResponse:
        retrieval_query = self._build_retrieval_query(
            question=question,
            conversation_history=conversation_history or [],
        )

        query_vector = self.embedding_service.embed_query(retrieval_query)

        candidate_top_k = max(
            top_k,
            top_k * settings.RAG_RETRIEVAL_CANDIDATE_MULTIPLIER,
        )

        raw_chunks = self.vector_store.search(
            query_vector=query_vector,
            client_id=client_id,
            corpus_id=corpus_id,
            top_k=candidate_top_k,
            score_threshold=None,
        )

        retrieval = self.retrieval_postprocessor.process(
            chunks=raw_chunks,
            requested_top_k=top_k,
            score_threshold=score_threshold,
        )

        chunks = retrieval["chunks"]

        if not chunks:
            return RagChatResponse(
                client_id=client_id,
                corpus_id=corpus_id,
                question=question,
                answer=(
                    "Je n'ai pas trouvé d'information suffisamment pertinente dans les documents "
                    "indexés pour répondre à cette question."
                ),
                sources=[],
                used_chunks_count=0,
                retrieval_confidence=retrieval["retrieval_confidence"],
                top_score=retrieval["top_score"],
                retrieval_candidates_count=retrieval["initial_candidates_count"],
                filtered_chunks_count=retrieval["filtered_candidates_count"],
            )

        if not self._has_enough_relevance(chunks):
            return self._build_strict_fallback_response(
                client_id=client_id,
                corpus_id=corpus_id,
                question=question,
                retrieval=retrieval,
            )

        messages = self.prompt_builder.build_messages(
            question=question,
            context_chunks=chunks,
            retrieval_confidence=retrieval["retrieval_confidence"],
            conversation_history=conversation_history or [],
        )

        answer_text = self._strip_generated_sources_section(
            self._call_vllm(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        return RagChatResponse(
            client_id=client_id,
            corpus_id=corpus_id,
            question=question,
            answer=answer_text,
            sources=self._build_chat_sources(chunks),
            used_chunks_count=len(chunks),
            retrieval_confidence=retrieval["retrieval_confidence"],
            top_score=retrieval["top_score"],
            retrieval_candidates_count=retrieval["initial_candidates_count"],
            filtered_chunks_count=retrieval["filtered_candidates_count"],
        )

    def _build_retrieval_query(
        self,
        *,
        question: str,
        conversation_history: list[dict],
    ) -> str:
        recent_user_messages = [
            (message.get("content") or "").strip()
            for message in conversation_history
            if message.get("role") == "user" and message.get("content")
        ]

        recent_user_messages = recent_user_messages[-2:]

        if not recent_user_messages:
            return question

        history_text = "\n".join(recent_user_messages)

        return (
            "Contexte récent de la conversation :\n"
            f"{history_text}\n\n"
            "Question actuelle :\n"
            f"{question}"
        )



    def _build_chat_sources(self, chunks: list[dict]) -> list[RagChatSource]:
        """Construit une liste de sources API stable et dédupliquée."""
        sources: list[RagChatSource] = []
        seen: set[tuple[str | None, int | None, int | None]] = set()

        for chunk in chunks:
            key = (
                chunk.get("source_id"),
                chunk.get("chunk_index"),
                chunk.get("page"),
            )

            if key in seen:
                continue

            seen.add(key)

            sources.append(
                RagChatSource(
                    source_id=chunk.get("source_id"),
                    source_type=chunk.get("source_type"),
                    source_name=chunk.get("source_name"),
                    page=chunk.get("page"),
                    chunk_index=chunk.get("chunk_index"),
                    score=chunk.get("score"),
                    text=chunk.get("text"),
                )
            )

        return sources


    def _strip_generated_sources_section(self, answer: str) -> str:
        """
        Supprime une éventuelle section de sources générée par le LLM.

        Les sources doivent être consommées depuis le champ JSON `sources`,
        pas depuis le texte libre `answer`.
        """
        if not answer:
            return answer

        patterns = [
            r"\n+\s*Sources utilisées\s*:\s*[\s\S]*$",
            r"\n+\s*Sources\s*:\s*[\s\S]*$",
            r"\n+\s*Références\s*:\s*[\s\S]*$",
        ]

        cleaned = answer.strip()

        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

        cleaned = re.sub(
            r"^\s*Réponse\s*:\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()

        return cleaned


    def _call_vllm(
        self,
        *,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        model_name = self._get_vllm_model_name()

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        url = f"{settings.VLLM_BASE_URL.rstrip('/')}/v1/chat/completions"

        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"].strip()

    def _get_vllm_model_name(self) -> str:
        for attr in ("VLLM_MODEL", "MODEL_NAME", "MODEL_ID", "LLM_MODEL"):
            value = getattr(settings, attr, None)
            if value:
                return value

        url = f"{settings.VLLM_BASE_URL.rstrip('/')}/v1/models"

        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

        models = data.get("data") or []

        if not models:
            raise ValueError("Aucun modèle vLLM disponible via /v1/models")

        return models[0]["id"]
