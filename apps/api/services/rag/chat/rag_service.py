from __future__ import annotations

from schemas.rag import RagChatRequest, RagChatResponse
from services.vllm_client import VLLMClient
from services.rag.chat.prompt_builder import RagPromptBuilder


class RagService:
    """
    Service applicatif du chatbot RAG.

    Jour 1 :
    - structure du service ;
    - branchement au VLLMClient existant ;
    - réponse contrôlée si aucun retrieval n'est encore disponible.

    Le retrieval Qdrant sera ajouté après l'ingestion et l'indexation.
    """

    def __init__(
        self,
        vllm_client: VLLMClient | None = None,
        prompt_builder: RagPromptBuilder | None = None,
    ) -> None:
        self.vllm_client = vllm_client or VLLMClient()
        self.prompt_builder = prompt_builder or RagPromptBuilder()

    async def chat(self, payload: RagChatRequest) -> RagChatResponse:
        """
        Réponse temporaire tant que le retrieval n'est pas encore implémenté.
        """
        return RagChatResponse(
            answer=(
                "Le module RAG est initialisé, mais l'indexation documentaire "
                "et la recherche Qdrant ne sont pas encore activées."
            ),
            sources=[],
            confidence="low",
            conversation_id=payload.conversation_id,
        )