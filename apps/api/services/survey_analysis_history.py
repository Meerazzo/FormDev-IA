from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from db.models.survey_processing_job import SurveyProcessingJob
from db.models.survey_processing_questionnaire import SurveyProcessingQuestionnaire


class SurveyAnalysisHistoryService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _extract_questionnaire_result(
        result_json: dict[str, Any] | None,
        questionnaire_id: str,
    ) -> dict[str, Any] | None:
        if not isinstance(result_json, dict):
            return None

        questionnaires = result_json.get("questionnaires")
        if not isinstance(questionnaires, list):
            return None

        for questionnaire in questionnaires:
            if not isinstance(questionnaire, dict):
                continue
            if str(questionnaire.get("id")) == questionnaire_id:
                return questionnaire

        return None

    def list_analyses(
        self,
        *,
        client_id: str,
        questionnaire_id: str,
        limit: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        base_query = (
            self.db.query(
                SurveyProcessingQuestionnaire,
                SurveyProcessingJob,
            )
            .join(
                SurveyProcessingJob,
                SurveyProcessingJob.processing_id
                == SurveyProcessingQuestionnaire.processing_id,
            )
            .filter(
                SurveyProcessingQuestionnaire.client_id == client_id,
                SurveyProcessingQuestionnaire.questionnaire_id == questionnaire_id,
                SurveyProcessingJob.client_id == client_id,
            )
        )

        total = base_query.count()

        rows = (
            base_query
            .order_by(
                SurveyProcessingQuestionnaire.created_at.desc(),
                SurveyProcessingQuestionnaire.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        items: list[dict[str, Any]] = []
        for _, job in rows:
            result = None
            if job.status == "FINISHED":
                result = self._extract_questionnaire_result(
                    job.result_json,
                    questionnaire_id,
                )

            items.append(
                {
                    "processing_id": job.processing_id,
                    "status": job.status,
                    "created_at": job.created_at,
                    "finished_at": job.finished_at,
                    "error_message": job.error_message,
                    "result": result,
                }
            )

        return total, items
