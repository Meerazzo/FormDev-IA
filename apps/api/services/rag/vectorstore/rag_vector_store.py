from uuid import uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient
from qdrant_client.http import models

from core.config import settings


class RagVectorStore:
    """
    Service Qdrant dédié au RAG documentaire.

    Il gère :
    - la vérification de santé
    - la création de la collection rag_chunks
    - l'insertion des chunks vectorisés
    - la recherche vectorielle filtrée par client_id / corpus_id
    """

    def __init__(self) -> None:
        self.collection_name = settings.RAG_QDRANT_COLLECTION
        self.vector_size = settings.RAG_VECTOR_SIZE
        self.client = QdrantClient(url=settings.QDRANT_URL)

    def health(self) -> dict:
        try:
            collections = self.client.get_collections()
            collection_exists = any(
                collection.name == self.collection_name
                for collection in collections.collections
            )

            return {
                "available": True,
                "collection_exists": collection_exists,
                "error": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "collection_exists": False,
                "error": str(exc),
            }

    def ensure_collection(self) -> None:
        """
        Crée la collection Qdrant si elle n'existe pas encore.
        """
        collections = self.client.get_collections()
        collection_exists = any(
            collection.name == self.collection_name
            for collection in collections.collections
        )

        if collection_exists:
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    def upsert_chunks(self, chunks: list[dict], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("Le nombre de chunks doit correspondre au nombre de vecteurs")

        self.ensure_collection()

        points: list[models.PointStruct] = []

        for chunk, vector in zip(chunks, vectors):
            source_id = chunk["source_id"]
            chunk_index = chunk["chunk_index"]

            point_id = str(uuid5(
                NAMESPACE_URL,
                f"rag:{source_id}:{chunk_index}",
            ))

            payload = {
                "client_id": chunk["client_id"],
                "corpus_id": chunk["corpus_id"],
                "source_id": chunk["source_id"],
                "source_type": chunk.get("source_type"),
                "source_name": chunk.get("source_name"),
                "page": chunk.get("page"),
                "chunk_index": chunk.get("chunk_index"),
                "text": chunk.get("text"),
                "metadata": chunk.get("metadata") or {},
            }

            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        if not points:
            return 0

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

        return len(points)

    def search(
        self,
        *,
        query_vector: list[float],
        client_id: str,
        corpus_id: str,
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict]:
        self.ensure_collection()

        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="client_id",
                    match=models.MatchValue(value=client_id),
                ),
                models.FieldCondition(
                    key="corpus_id",
                    match=models.MatchValue(value=corpus_id),
                ),
            ]
        )

        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )

        results: list[dict] = []

        for hit in hits:
            payload = hit.payload or {}
            results.append(
                {
                    "id": str(hit.id),
                    "score": hit.score,
                    "source_id": payload.get("source_id"),
                    "source_type": payload.get("source_type"),
                    "source_name": payload.get("source_name"),
                    "page": payload.get("page"),
                    "chunk_index": payload.get("chunk_index"),
                    "text": payload.get("text"),
                    "metadata": payload.get("metadata") or {},
                }
            )

        return results

    def delete_source(self, *, client_id: str, corpus_id: str, source_id: str) -> None:
        self.ensure_collection()

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="client_id",
                            match=models.MatchValue(value=client_id),
                        ),
                        models.FieldCondition(
                            key="corpus_id",
                            match=models.MatchValue(value=corpus_id),
                        ),
                        models.FieldCondition(
                            key="source_id",
                            match=models.MatchValue(value=source_id),
                        ),
                    ]
                )
            ),
            wait=True,
        )
