from typing import Any, Dict, Optional
from datetime import datetime, timezone

from db.models.validated_response_point import ValidatedResponsePoint
from db.models.point_feedback import PointFeedback
from db.models.response_point import ResponsePoint


class SurveyFeedbackService:
    def __init__(self, db):
        self.db = db

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
    
    def save_feedback(
        self,
        response_id: str,
        points: list[Dict[str, Any]],
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        saved_count = 0

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
                    **(metadata or {}),
                    "feedback_source": "operator",
                },
            )

            self.db.add(feedback)
            self._apply_feedback_to_validated_points(
                response_id=response_id,
                item=item,
                operator_id=operator_id,
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