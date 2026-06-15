import httpx

from core.config import settings
from schemas.rag import RagChatResponse, RagChatSource
from services.rag.chat.prompt_builder import RagPromptBuilder
from services.rag.chat.retrieval_postprocessor import RagRetrievalPostProcessor
from services.rag.embeddings.local_embedding_service import get_local_embedding_service
from services.rag.vectorstore.rag_vector_store import RagVectorStore


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

        messages = self.prompt_builder.build_messages(
            question=question,
            context_chunks=chunks,
            retrieval_confidence=retrieval["retrieval_confidence"],
            conversation_history=conversation_history or [],
        )

        answer_text = self._call_vllm(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return RagChatResponse(
            client_id=client_id,
            corpus_id=corpus_id,
            question=question,
            answer=answer_text,
            sources=[
                RagChatSource(
                    source_id=chunk.get("source_id"),
                    source_type=chunk.get("source_type"),
                    source_name=chunk.get("source_name"),
                    page=chunk.get("page"),
                    chunk_index=chunk.get("chunk_index"),
                    score=chunk.get("score"),
                    text=chunk.get("text"),
                )
                for chunk in chunks
            ],
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
