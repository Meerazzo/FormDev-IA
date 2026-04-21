from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models


class SurveyExampleMemoryService:
    """
    Mémoire vectorielle des exemples opérateur pour améliorer la classification.

    Chaque exemple est stocké dans Qdrant avec :
    - un vecteur calculé à partir de "Question + Point"
    - un payload contenant la sortie finale corrigée et les métadonnées utiles

    Les recherches sont filtrées par :
    - client_id
    - is_active = true
    - final_category dans les catégories autorisées
    - question_type en priorité, avec fallback sans ce filtre
    """

    def __init__(
        self,
        qdrant_url: str,
        collection_name: str,
        embedding_model: str,
        vector_size: int,
    ):
        self.client = QdrantClient(url=qdrant_url)
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.vector_size = vector_size
        self.embedder = TextEmbedding(model_name=embedding_model)

    def ensure_collection(self) -> None:
        """
        Crée la collection Qdrant si elle n'existe pas encore.
        Crée également les index de payload utiles aux filtres.
        """
        if self.client.collection_exists(self.collection_name):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.vector_size,
                distance=models.Distance.COSINE,
            ),
        )

        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="client_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="example_type",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="final_category",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="question_type",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="is_active",
            field_schema=models.PayloadSchemaType.BOOL,
        )

    @staticmethod
    def build_document(question_text: str, input_point_text: str) -> str:
        """
        Construit le texte à vectoriser pour représenter un exemple.
        """
        return f"Question : {question_text}\nPoint : {input_point_text}"

    def _embed(self, text: str) -> List[float]:
        """
        Calcule l'embedding du texte avec fastembed.
        """
        vector = list(next(self.embedder.embed([text])))

        if len(vector) != self.vector_size:
            raise ValueError(
                f"Unexpected embedding size: got {len(vector)}, expected {self.vector_size}"
            )

        return vector

    @staticmethod
    def _build_point_qdrant_id(
        response_id: str,
        point_id: Optional[str],
        input_point_text: str,
    ) -> str:
        """
        Construit un identifiant UUID stable compatible Qdrant.

        - point existant : basé sur response_id + point_id
        - point ajouté manuellement : basé sur response_id + hash du texte
        """
        if point_id:
            stable_key = f"resp:{response_id}:pt:{point_id}"
        else:
            text_hash = hashlib.md5(input_point_text.encode("utf-8")).hexdigest()
            stable_key = f"resp:{response_id}:add:{text_hash}"

        return str(uuid.uuid5(uuid.NAMESPACE_DNS, stable_key))

    def upsert_example(
        self,
        *,
        client_id: str,
        question_text: str,
        input_point_text: str,
        final_text: str,
        final_sentiment: Optional[int],
        final_category: Optional[str],
        example_type: str,
        response_id: str,
        point_id: Optional[str],
        question_type: Optional[str] = None,
    ) -> str:
        """
        Ajoute ou met à jour un exemple dans Qdrant.
        """
        self.ensure_collection()

        document = self.build_document(question_text, input_point_text)
        vector = self._embed(document)
        qdrant_id = self._build_point_qdrant_id(
            response_id=response_id,
            point_id=point_id,
            input_point_text=input_point_text,
        )

        payload: Dict[str, Any] = {
            "client_id": client_id,
            "question_text": question_text,
            "input_point_text": input_point_text,
            "final_text": final_text,
            "final_sentiment": final_sentiment,
            "final_category": final_category,
            "question_type": question_type,
            "example_type": example_type,
            "response_id": response_id,
            "point_id": point_id,
            "is_active": True,
        }

        self.client.upsert(
            collection_name=self.collection_name,
            wait=True,
            points=[
                models.PointStruct(
                    id=qdrant_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

        return qdrant_id

    def deactivate_example(
        self,
        *,
        response_id: str,
        point_id: Optional[str],
        input_point_text: str,
    ) -> None:
        """
        Désactive logiquement un exemple déjà présent dans Qdrant.
        """
        self.ensure_collection()

        qdrant_id = self._build_point_qdrant_id(
            response_id=response_id,
            point_id=point_id,
            input_point_text=input_point_text,
        )

        self.client.set_payload(
            collection_name=self.collection_name,
            payload={"is_active": False},
            points=[qdrant_id],
        )

    @staticmethod
    def _build_base_must_conditions(
        *,
        client_id: str,
        allowed_categories: Optional[List[str]] = None,
    ) -> List[models.Condition]:
        must_conditions: List[models.Condition] = [
            models.FieldCondition(
                key="client_id",
                match=models.MatchValue(value=client_id),
            ),
            models.FieldCondition(
                key="is_active",
                match=models.MatchValue(value=True),
            ),
        ]

        if allowed_categories:
            must_conditions.append(
                models.FieldCondition(
                    key="final_category",
                    match=models.MatchAny(any=allowed_categories),
                )
            )

        return must_conditions

    def _query_examples(
        self,
        *,
        vector: List[float],
        must_conditions: List[models.Condition],
        limit: int,
    ) -> List[Dict[str, Any]]:
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=models.Filter(must=must_conditions),
            with_payload=True,
            limit=limit,
        ).points

        examples: List[Dict[str, Any]] = []
        for item in results:
            payload = item.payload or {}
            examples.append(
                {
                    "score": item.score,
                    "question_text": payload.get("question_text"),
                    "input_point_text": payload.get("input_point_text"),
                    "final_text": payload.get("final_text"),
                    "final_sentiment": payload.get("final_sentiment"),
                    "final_category": payload.get("final_category"),
                    "question_type": payload.get("question_type"),
                    "example_type": payload.get("example_type"),
                    "response_id": payload.get("response_id"),
                    "point_id": payload.get("point_id"),
                }
            )

        return examples

    def search_similar_examples(
        self,
        *,
        client_id: str,
        question_text: str,
        input_point_text: str,
        allowed_categories: Optional[List[str]] = None,
        question_type: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Recherche les exemples les plus proches pour un client donné.

        Filtrage :
        - client_id obligatoire
        - is_active = true
        - final_category dans allowed_categories si fourni
        - question_type prioritaire si fourni
        - fallback sans filtre question_type si le résultat est insuffisant
        """
        self.ensure_collection()

        document = self.build_document(question_text, input_point_text)
        vector = self._embed(document)

        base_must_conditions = self._build_base_must_conditions(
            client_id=client_id,
            allowed_categories=allowed_categories,
        )

        # 1. Recherche préférentielle avec même question_type
        if question_type:
            typed_conditions = list(base_must_conditions)
            typed_conditions.append(
                models.FieldCondition(
                    key="question_type",
                    match=models.MatchValue(value=question_type),
                )
            )

            typed_examples = self._query_examples(
                vector=vector,
                must_conditions=typed_conditions,
                limit=limit,
            )

            if len(typed_examples) >= limit:
                return typed_examples

            # 2. Fallback sans filtre question_type
            fallback_examples = self._query_examples(
                vector=vector,
                must_conditions=base_must_conditions,
                limit=limit,
            )

            # On fusionne sans doublons, en priorisant les typed_examples
            merged: List[Dict[str, Any]] = []
            seen_keys: set[tuple] = set()

            for ex in typed_examples + fallback_examples:
                key = (
                    ex.get("response_id"),
                    ex.get("point_id"),
                    ex.get("input_point_text"),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.append(ex)

                if len(merged) >= limit:
                    break

            return merged

        # 3. Recherche classique sans question_type
        return self._query_examples(
            vector=vector,
            must_conditions=base_must_conditions,
            limit=limit,
        )