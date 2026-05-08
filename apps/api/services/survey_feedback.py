from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging

from core.config import settings
from db.models.survey_processing_job import SurveyProcessingJob
from db.models.point_feedback import PointFeedback
from db.models.response_point import ResponsePoint
from db.models.survey_response import SurveyResponse
from db.models.validated_response_point import ValidatedResponsePoint
from db.models.ai_interaction import AIInteraction
from services.survey_example_memory import SurveyExampleMemoryService
from sqlalchemy.orm.attributes import flag_modified
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
    
    def _get_processing_job_for_response(self, response: SurveyResponse) -> Optional[SurveyProcessingJob]:
        metadata = response.metadata_json or {}
        client_id = metadata.get("client_id")

        query = self.db.query(SurveyProcessingJob).filter(
            SurveyProcessingJob.survey_id == "client_questionnaires",
            SurveyProcessingJob.status == "FINISHED",
        )

        if client_id:
            query = query.filter(SurveyProcessingJob.client_id == client_id)

        # On prend le job le plus récent qui contient ce response_id dans son result_json
        jobs = query.order_by(SurveyProcessingJob.finished_at.desc()).limit(20).all()

        for job in jobs:
            if self._json_contains_response_id(job.result_json or {}, response.response_id):
                return job

        return None


    def _json_contains_response_id(self, data: Dict[str, Any], response_id: str) -> bool:
        questionnaires = (data or {}).get("questionnaires", [])

        for questionnaire in questionnaires:
            for question in questionnaire.get("questions", []):
                if question.get("response_id") == response_id:
                    return True

                answer = question.get("answer")
                if isinstance(answer, dict) and answer.get("response_id") == response_id:
                    return True

                for ans in question.get("answers", []) or []:
                    if ans.get("response_id") == response_id:
                        return True

        return False


    def _segments_from_validated_points(self, response_id: str) -> list[dict[str, Any]]:
        points = (
            self.db.query(ValidatedResponsePoint)
            .filter(
                ValidatedResponsePoint.response_id == response_id,
                ValidatedResponsePoint.is_active == "true",
            )
            .all()
        )

        sentiment_map = {
            1: "VERY_NEGATIVE",
            2: "NEGATIVE",
            3: "NEUTRAL",
            4: "POSITIVE",
            5: "VERY_POSITIVE",
        }

        segments = []
        for point in points:
            segments.append(
                {
                    "text": point.final_text,
                    "point_id": point.point_id,
                    "sentiment": sentiment_map.get(point.final_sentiment, "NEUTRAL"),
                    # on ne peut pas retrouver proprement categoryId ici sans availableCategories,
                    # il sera résolu dans _replace_segments_in_result_json
                    "category_label": point.final_category,
                }
            )

        return segments


    def _category_id_by_label(self, questionnaire: Dict[str, Any]) -> Dict[str, int]:
        return {
            str(category.get("label")): category.get("id")
            for category in questionnaire.get("availableCategories", [])
            if category.get("label") is not None
        }


    def _replace_segments_in_result_json(
        self,
        data: Dict[str, Any],
        response_id: str,
        new_segments: list[dict[str, Any]],
    ) -> Dict[str, Any]:
        for questionnaire in data.get("questionnaires", []):
            category_map = self._category_id_by_label(questionnaire)

            final_segments = []
            for segment in new_segments:
                category_label = segment.get("category_label")
                final_segments.append({
                    "text": segment.get("text", ""),
                    "point_id": segment.get("point_id"),
                    "sentiment": segment.get("sentiment", "NEUTRAL"),
                    "categoryId": category_map.get(category_label, 0),
                })

            for question in questionnaire.get("questions", []):
                if question.get("response_id") == response_id:
                    question["segments"] = final_segments
                    return data

                answer = question.get("answer")
                if isinstance(answer, dict) and answer.get("response_id") == response_id:
                    answer["segments"] = final_segments
                    return data

                for ans in question.get("answers", []) or []:
                    if ans.get("response_id") == response_id:
                        ans["segments"] = final_segments
                        return data

        return data


    def _sync_processing_result_json(self, response_id: str) -> None:
        from sqlalchemy.orm.attributes import flag_modified

        survey_response = self._get_survey_response(response_id)
        if not survey_response:
            return

        job = self._get_processing_job_for_response(survey_response)
        if not job or not job.result_json:
            return

        new_segments = self._segments_from_validated_points(response_id)

        updated_json = self._replace_segments_in_result_json(
            data=job.result_json,
            response_id=response_id,
            new_segments=new_segments,
        )

        job.result_json = updated_json
        flag_modified(job, "result_json")
        
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
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        saved_count = 0

        survey_response = self._get_survey_response(response_id)
        if not survey_response:
            raise ValueError("Survey response not found")

        response_client_id = (
            getattr(survey_response, "client_id", None)
            or (survey_response.metadata_json or {}).get("client_id")
        )

        if client_id and response_client_id != client_id:
            raise ValueError("Response does not belong to this client_id")
        response_metadata = survey_response.metadata_json if survey_response else {}

        enriched_metadata = {
            **(response_metadata or {}),
            **(metadata or {}),
            "question_text": survey_response.question_text if survey_response else None,
            "question_type": (response_metadata or {}).get("question_type"),
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
        self._sync_processing_result_json(response_id=response_id)

        if settings.SURVEY_PURGE_AFTER_FEEDBACK:
            self.db.flush()
            self._purge_response_data_after_feedback(response_id=response_id)

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

    def _get_memory_input_point_text(
        self,
        *,
        response_id: str,
        metadata: Optional[Dict[str, Any]],
        existing_point: Optional[ResponsePoint],
        item: Dict[str, Any],
    ) -> Optional[str]:
        question_type = (metadata or {}).get("question_type")
        survey_response = self._get_survey_response(response_id)

        if question_type in {"SINGLE_CHOICE", "MULTIPLE_CHOICE", "RATING", "CHECKBOX"}:
            if survey_response and survey_response.response_text:
                return survey_response.response_text

        if existing_point:
            return existing_point.point_text

        corrected_text = (item.get("corrected_text") or "").strip()
        if corrected_text:
            return corrected_text

        return None

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
        question_type = (metadata or {}).get("question_type")

        if not client_id or not question_text:
            return

        action = self._normalize_action(item.get("action"))
        is_correct = bool(item.get("is_correct", False))
        memory_input_text = self._get_memory_input_point_text(
            response_id=response_id,
            metadata=metadata,
            existing_point=existing_point,
            item=item,
        )

        if not memory_input_text:
            return
        if action == "delete" and existing_point:
            self.example_memory.deactivate_example(
                response_id=response_id,
                point_id=item.get("point_id"),
                input_point_text=memory_input_text,
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
                    input_point_text=memory_input_text,
                    final_text=existing_point.point_text,
                    final_sentiment=existing_point.sentiment,
                    final_category=existing_point.category,
                    question_type=question_type,
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
                input_point_text=memory_input_text,
                final_text=final_text,
                final_sentiment=final_sentiment,
                final_category=final_category,
                question_type=question_type,
                example_type="operator_corrected",
                response_id=response_id,
                point_id=item.get("point_id"),
            )
            return

        if action == "add":
            corrected_text = (item.get("corrected_text") or "").strip()
            if not corrected_text:
                return

            if question_type in {"SINGLE_CHOICE", "MULTIPLE_CHOICE", "RATING", "CHECKBOX"}:
                input_point_text = memory_input_text
            else:
                input_point_text = corrected_text

            self.example_memory.upsert_example(
                client_id=client_id,
                question_text=question_text,
                input_point_text=input_point_text,
                final_text=corrected_text,
                final_sentiment=item.get("corrected_sentiment"),
                final_category=item.get("corrected_category"),
                question_type=question_type,
                example_type="operator_added",
                response_id=response_id,
                point_id=None,
            )

    def _purge_response_data_after_feedback(self, response_id: str) -> None:
        """
        Supprime les données PostgreSQL temporaires liées à une réponse après feedback.

        La mémoire métier utile est conservée dans Qdrant.
        """
        self.db.query(AIInteraction).filter(
            AIInteraction.source_ref == response_id,
        ).delete(synchronize_session=False)

        self.db.query(PointFeedback).filter(
            PointFeedback.response_id == response_id,
        ).delete(synchronize_session=False)

        self.db.query(ResponsePoint).filter(
            ResponsePoint.response_id == response_id,
        ).delete(synchronize_session=False)

        self.db.query(ValidatedResponsePoint).filter(
            ValidatedResponsePoint.response_id == response_id,
        ).delete(synchronize_session=False)

        self.db.query(SurveyResponse).filter(
            SurveyResponse.response_id == response_id,
        ).delete(synchronize_session=False)