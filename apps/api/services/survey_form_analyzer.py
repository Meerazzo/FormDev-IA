"""
Gestion des traitements d'analyse de formulaires.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.feature_config import (
    SURVEY_FORM_MAX_DISTINCT_QUESTIONS,
    SURVEY_FORM_MAX_ITEMS,
    SURVEY_FORM_MAX_RESPONSE_LENGTH,
)
from db.models.survey_processing_job import SurveyProcessingJob
from services.survey_analyzer import SurveyAnalyzerService
from services.survey_question_selector import SurveyQuestionSelectorService


class SurveyFormAnalyzerService:
    def __init__(self, vllm_client, db):
        self.vllm_client = vllm_client
        self.db = db
        self.question_selector = SurveyQuestionSelectorService(vllm_client=vllm_client)
        self.survey_analyzer = SurveyAnalyzerService(vllm_client=vllm_client, db=db)

    @staticmethod
    def _validate_form_payload(items: List[Dict[str, Any]]) -> None:
        if len(items) > SURVEY_FORM_MAX_ITEMS:
            raise ValueError(
                f"Too many form items: {len(items)}. Maximum allowed is {SURVEY_FORM_MAX_ITEMS}."
            )

        for item in items:
            response_text = item.get("response_text") or ""
            if len(response_text) > SURVEY_FORM_MAX_RESPONSE_LENGTH:
                question_id = item.get("question_id", "unknown")
                raise ValueError(
                    f"Response too long for question_id={question_id}. "
                    f"Maximum allowed length is {SURVEY_FORM_MAX_RESPONSE_LENGTH} characters."
                )

    @staticmethod
    def _build_question_decision_map(
        question_decisions: List[Dict[str, str]],
    ) -> Dict[str, str]:
        mapping: Dict[str, str] = {}

        for item in question_decisions:
            question_text = " ".join((item.get("question_text") or "").strip().split())
            decision = (item.get("decision") or "").strip().lower()

            if not question_text or decision not in {"analyze", "ignore"}:
                continue

            mapping[question_text.lower()] = decision

        return mapping

    def create_processing_job(
        self,
        survey_id: str,
        items: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        client_id: Optional[str] = None,
    ) -> SurveyProcessingJob:
        self._validate_form_payload(items)

        distinct_questions = self.question_selector.extract_distinct_questions(items)
        if len(distinct_questions) > SURVEY_FORM_MAX_DISTINCT_QUESTIONS:
            raise ValueError(
                f"Too many distinct questions: {len(distinct_questions)}. "
                f"Maximum allowed is {SURVEY_FORM_MAX_DISTINCT_QUESTIONS}."
            )

        processing_id = str(uuid.uuid4())

        job = SurveyProcessingJob(
            processing_id=processing_id,
            survey_id=survey_id,
            client_id=client_id,
            status="PENDING",
            request_payload_json={
                "survey_id": survey_id,
                "items": items,
                "metadata": metadata or {},
            },
        )

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_processing_job(
        self,
        processing_id: str,
        client_id: Optional[str] = None,
    ) -> Optional[SurveyProcessingJob]:
        query = self.db.query(SurveyProcessingJob).filter(
            SurveyProcessingJob.processing_id == processing_id
        )

        if client_id is not None:
            query = query.filter(SurveyProcessingJob.client_id == client_id)

        return query.first()

    async def run_processing_job(
        self,
        processing_id: str,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        job = (
            self.db.query(SurveyProcessingJob)
            .filter(SurveyProcessingJob.processing_id == processing_id)
            .first()
        )

        if not job:
            raise ValueError(f"Processing job not found: {processing_id}")

        payload = job.request_payload_json or {}
        survey_id = payload.get("survey_id")
        items = payload.get("items") or []
        metadata = payload.get("metadata") or {}
        client_id = job.client_id

        job.status = "STARTED"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()

        try:
            result = await self._analyze_form_payload(
                survey_id=survey_id,
                items=items,
                metadata=metadata,
                request_id=request_id,
                client_id=client_id,
            )

            job.status = "FINISHED"
            job.result_json = result
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = None
            self.db.commit()

            return result

        except Exception as e:
            job.status = "FAILED"
            job.error_message = str(e)
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            raise

    async def _analyze_form_payload(
        self,
        survey_id: str,
        items: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        distinct_questions = self.question_selector.extract_distinct_questions(items)
        selection_result = await self.question_selector.select_questions_in_chunks(
            distinct_questions
        )

        question_decisions = selection_result.get("questions", [])
        decision_map = self._build_question_decision_map(question_decisions)

        response_results: List[Dict[str, Any]] = []

        for item in items:
            question_id = item.get("question_id")
            question_text = " ".join((item.get("question_text") or "").strip().split())
            response_text = item.get("response_text")

            if not question_text:
                continue

            selection_decision = decision_map.get(question_text.lower(), "ignore")

            item_metadata = {
                **(metadata or {}),
                "selection_decision": selection_decision,
                "selection_source": "llm_form_selector",
            }

            if selection_decision == "analyze":
                analyzed = await self.survey_analyzer.analyze(
                    survey_id=survey_id,
                    question_id=question_id,
                    question_text=question_text,
                    response_text=response_text,
                    metadata=item_metadata,
                    request_id=request_id,
                    client_id=client_id,
                    source_endpoint="/surveys/forms/analyze",
                )

                response_results.append(
                    {
                        "response_id": analyzed["response_id"],
                        "question_id": question_id,
                        "question_text": question_text,
                        "selection_decision": "analyze",
                        "points": analyzed["points"],
                    }
                )
            else:
                ignored = await self.survey_analyzer.analyze(
                    survey_id=survey_id,
                    question_id=question_id,
                    question_text=question_text,
                    response_text=response_text,
                    metadata={
                        **item_metadata,
                        "skip_reason": "question_not_selected",
                        "force_ignore": True,
                    },
                    request_id=request_id,
                    client_id=client_id,
                    source_endpoint="/surveys/forms/analyze",
                )

                response_results.append(
                    {
                        "response_id": ignored["response_id"],
                        "question_id": question_id,
                        "question_text": question_text,
                        "selection_decision": "ignore",
                        "points": [],
                    }
                )

        return {
            "survey_id": survey_id,
            "question_decisions": question_decisions,
            "responses": response_results,
        }