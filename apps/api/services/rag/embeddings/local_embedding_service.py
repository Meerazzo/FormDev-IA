from functools import lru_cache

from fastembed import TextEmbedding

from core.config import settings


class LocalEmbeddingService:
    """
    Service d'embeddings local basé sur FastEmbed.

    Il transforme du texte en vecteurs numériques.
    Ces vecteurs seront ensuite stockés dans Qdrant.
    """

    def __init__(self) -> None:
        self.model_name = settings.RAG_EMBEDDING_MODEL
        self.model = TextEmbedding(model_name=self.model_name)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = list(self.model.embed(texts))

        return [
            vector.tolist() if hasattr(vector, "tolist") else list(vector)
            for vector in vectors
        ]

    def embed_query(self, query: str) -> list[float]:
        vectors = self.embed_texts([query])
        if not vectors:
            raise ValueError("Impossible de générer l'embedding de la requête")
        return vectors[0]


@lru_cache(maxsize=1)
def get_local_embedding_service() -> LocalEmbeddingService:
    """
    Cache le modèle en mémoire pour éviter de le recharger à chaque requête.
    """
    return LocalEmbeddingService()
