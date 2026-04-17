from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging
from core.config import settings
from db.models.point_feedback import PointFeedback
from db.models.response_point import ResponsePoint
from db.models.survey_response import SurveyResponse
from db.models.validated_response_point import ValidatedResponsePoint
from services.survey_example_memory import SurveyExampleMemoryService

logger = logging.getLogger(__name__)

class SurveyFeedbackService:
    def __init__(self, db):
        self.db = db
        self.example_memory = SurveyExampleMemoryService(
            qdrant_url=settings.QDRANT_URL,
            collection_name=settings.QDRANT_COLLECTION,
            embedding_model=settings.QDRANT_EMBEDDING_MODEL,
            vector_size=settings.QDRANT_VECTOR_SIZE,
        )

    @staticmethod
    def _normalize_action(action: Optional[str]) -> str:
        value = (action or "update").strip().lower()
        if value not in {"update", "delete", "add"}:
            return "update"
        return value

    def _get_existing_point(
        self,
        response_id: str,
        point_id: Optional[str],
    ) -> Optional[ResponsePoint]:
        if not point_id:
            return None

        return (
            self.db.query(ResponsePoint)
            .filter(
                ResponsePoint.point_id == point_id,
                ResponsePoint.response_id == response_id,
            )
            .first()
        )

    def _get_survey_response(self, response_id: str) -> Optional[SurveyResponse]:
        return (
            self.db.query(SurveyResponse)
            .filter(SurveyResponse.response_id == response_id)
            .first()
        )

    def save_feedback(
        self,
        response_id: str,
        points: list[Dict[str, Any]],
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        saved_count = 0

        survey_response = self._get_survey_response(response_id)
        enriched_metadata = {
            **(metadata or {}),
            "question_text": survey_response.question_text if survey_response else None,
        }

        for item in points:
            point_id = item.get("point_id")
            existing_point = self._get_existing_point(response_id, point_id)

            feedback = PointFeedback(
                response_id=response_id,
                point_id=point_id,
                is_correct=bool(item.get("is_correct", False)),
                original_text=existing_point.point_text if existing_point else None,
                original_sentiment=existing_point.sentiment if existing_point else None,
                original_category=existing_point.category if existing_point else None,
                corrected_text=item.get("corrected_text"),
                corrected_sentiment=item.get("corrected_sentiment"),
                corrected_category=item.get("corrected_category"),
                action=self._normalize_action(item.get("action")),
                operator_id=operator_id,
                metadata_json={
                    **enriched_metadata,
                    "feedback_source": "operator",
                },
            )

            self.db.add(feedback)

            self._apply_feedback_to_validated_points(
                response_id=response_id,
                item=item,
                operator_id=operator_id,
            )

            try:
                self._push_feedback_example_to_memory(
                    response_id=response_id,
                    item=item,
                    metadata=enriched_metadata,
                    existing_point=existing_point,
                )
            except Exception as e:
                logger.warning(
                    "Qdrant memory update failed during feedback save "
                    "(response_id=%s, point_id=%s, action=%s): %s",
                    response_id,
                    point_id,
                    item.get("action"),
                    str(e),
                )

            saved_count += 1

        self.db.commit()

        return {
            "response_id": response_id,
            "saved_feedback_count": saved_count,
            "status": "ok",
        }

    def _get_validated_point(
        self,
        response_id: str,
        point_id: Optional[str],
    ) -> Optional[ValidatedResponsePoint]:
        if not point_id:
            return None

        return (
            self.db.query(ValidatedResponsePoint)
            .filter(
                ValidatedResponsePoint.point_id == point_id,
                ValidatedResponsePoint.response_id == response_id,
                ValidatedResponsePoint.is_active == "true",
            )
            .first()
        )

    def _apply_feedback_to_validated_points(
        self,
        response_id: str,
        item: Dict[str, Any],
        operator_id: Optional[str] = None,
    ) -> None:
        action = self._normalize_action(item.get("action"))
        point_id = item.get("point_id")

        validated_point = self._get_validated_point(response_id, point_id)

        if action == "update" and validated_point:
            if item.get("corrected_text"):
                validated_point.final_text = item["corrected_text"]
            if item.get("corrected_sentiment") is not None:
                validated_point.final_sentiment = item["corrected_sentiment"]
            if item.get("corrected_category"):
                validated_point.final_category = item["corrected_category"]

            validated_point.source = "operator_corrected"
            validated_point.operator_id = operator_id
            validated_point.validated_at = datetime.now(timezone.utc)

        elif action == "delete" and validated_point:
            validated_point.is_active = "false"
            validated_point.source = "operator_corrected"
            validated_point.operator_id = operator_id
            validated_point.validated_at = datetime.now(timezone.utc)

        elif action == "add":
            corrected_text = (item.get("corrected_text") or "").strip()
            if not corrected_text:
                return

            self.db.add(
                ValidatedResponsePoint(
                    response_id=response_id,
                    point_id=None,
                    final_text=corrected_text,
                    final_sentiment=item.get("corrected_sentiment"),
                    final_category=item.get("corrected_category"),
                    source="operator_added",
                    is_active="true",
                    operator_id=operator_id,
                    validated_at=datetime.now(timezone.utc),
                )
            )

    def _push_feedback_example_to_memory(
        self,
        *,
        response_id: str,
        item: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
        existing_point: Optional[ResponsePoint],
    ) -> None:
        client_id = (metadata or {}).get("client_id")
        question_text = (metadata or {}).get("question_text")

        if not client_id or not question_text:
            return

        action = self._normalize_action(item.get("action"))
        is_correct = bool(item.get("is_correct", False))

        if action == "delete" and existing_point:
            self.example_memory.deactivate_example(
                response_id=response_id,
                point_id=item.get("point_id"),
                input_point_text=existing_point.point_text,
            )
            return

        if action == "update" and existing_point:
            # Cas 1 : validation explicite sans correction
            if (
                is_correct
                and not item.get("corrected_text")
                and item.get("corrected_sentiment") is None
                and not item.get("corrected_category")
            ):
                self.example_memory.upsert_example(
                    client_id=client_id,
                    question_text=question_text,
                    input_point_text=existing_point.point_text,
                    final_text=existing_point.point_text,
                    final_sentiment=existing_point.sentiment,
                    final_category=existing_point.category,
                    example_type="operator_validated",
                    response_id=response_id,
                    point_id=item.get("point_id"),
                )
                return

            # Cas 2 : correction opérateur
            final_text = item.get("corrected_text") or existing_point.point_text
            final_sentiment = (
                item.get("corrected_sentiment")
                if item.get("corrected_sentiment") is not None
                else existing_point.sentiment
            )
            final_category = item.get("corrected_category") or existing_point.category

            self.example_memory.upsert_example(
                client_id=client_id,
                question_text=question_text,
                input_point_text=existing_point.point_text,
                final_text=final_text,
                final_sentiment=final_sentiment,
                final_category=final_category,
                example_type="operator_corrected",
                response_id=response_id,
                point_id=item.get("point_id"),
            )
            return

        if action == "add":
            corrected_text = (item.get("corrected_text") or "").strip()
            if not corrected_text:
                return

            self.example_memory.upsert_example(
                client_id=client_id,
                question_text=question_text,
                input_point_text=corrected_text,
                final_text=corrected_text,
                final_sentiment=item.get("corrected_sentiment"),
                final_category=item.get("corrected_category"),
                example_type="operator_added",
                response_id=response_id,
                point_id=None,
            )