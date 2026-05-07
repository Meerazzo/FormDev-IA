"""
Gestion des traitements d'analyse de formulaires.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from schemas.survey_client import ClientQuestionnaireAnalyzeRequest
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
    def _resolve_selection_decision(
        *,
        question_text: str,
        item_metadata: Dict[str, Any],
        form_metadata: Optional[Dict[str, Any]],
        decision_map: Dict[str, str],
    ) -> str:
        source_format = (form_metadata or {}).get("source_format")
        question_type = (item_metadata or {}).get("question_type")

        if source_format == "client_questionnaire_v1":
            if question_type in {"SINGLE_CHOICE", "MULTIPLE_CHOICE", "RATING", "CHECKBOX"}:
                return "analyze"

        return decision_map.get(question_text.lower(), "ignore")

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

    def mark_processing_job_queued(
        self,
        processing_id: str,
        rq_job_id: Optional[str] = None,
    ) -> Optional[SurveyProcessingJob]:
        job = (
            self.db.query(SurveyProcessingJob)
            .filter(SurveyProcessingJob.processing_id == processing_id)
            .first()
        )

        if not job:
            return None

        job.status = "QUEUED"

        metadata = job.request_payload_json or {}
        metadata["_queue"] = {
            "rq_job_id": rq_job_id,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
        job.request_payload_json = metadata

        self.db.commit()
        self.db.refresh(job)

        return job

    def mark_processing_job_enqueue_failed(
        self,
        processing_id: str,
        error_message: str,
    ) -> Optional[SurveyProcessingJob]:
        job = (
            self.db.query(SurveyProcessingJob)
            .filter(SurveyProcessingJob.processing_id == processing_id)
            .first()
        )

        if not job:
            return None

        job.status = "RECEIVED"
        job.error_message = error_message

        self.db.commit()
        self.db.refresh(job)

        return job

    def create_client_processing_job(
        self,
        payload: ClientQuestionnaireAnalyzeRequest,
        client_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> SurveyProcessingJob:
        processing_id = str(uuid.uuid4())

        job = SurveyProcessingJob(
            processing_id=processing_id,
            survey_id="client_questionnaires",
            client_id=client_id,
            request_id=request_id,
            status="RECEIVED",
            request_payload_json=payload.model_dump(),
        )

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

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
            status="RECEIVED",
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

    async def run_client_processing_job(
        self,
        processing_id: str,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from schemas.survey_client import ClientQuestionnaireAnalyzeRequest
        from services.survey_client_analyzer import SurveyClientAnalyzerService

        job = (
            self.db.query(SurveyProcessingJob)
            .filter(SurveyProcessingJob.processing_id == processing_id)
            .first()
        )

        if not job:
            raise ValueError(f"Processing job not found: {processing_id}")

        job.status = "STARTED"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()

        try:
            payload = ClientQuestionnaireAnalyzeRequest(**(job.request_payload_json or {}))

            client_service = SurveyClientAnalyzerService(form_analyzer=self)

            result = await client_service.analyze(
                payload=payload,
                request_id=request_id,
                client_id=job.client_id,
            )

            job.status = "FINISHED"
            job.result_json = result.model_dump()
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = None
            self.db.commit()

            return result.model_dump()

        except Exception as e:
            job.status = "FAILED"
            job.error_message = str(e)
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            raise

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
        self._validate_form_payload(items)
        open_items = [
            item for item in items
            if (item.get("metadata") or {}).get("question_type") == "OPEN"
        ]

        distinct_questions = self.question_selector.extract_distinct_questions(open_items)
        selection_result = await self.question_selector.select_questions_in_chunks(
            distinct_questions
        )

        question_decisions = selection_result.get("questions", [])
        decision_map = self._build_question_decision_map(question_decisions)

        response_results: List[Dict[str, Any]] = []

        for item in items:
            question_id = item.get("question_id")
            input_response_id = item.get("response_id")
            question_text = " ".join((item.get("question_text") or "").strip().split())
            response_text = item.get("response_text")
            item_metadata = item.get("metadata") or {}
            skip_segmentation = bool(item.get("skip_segmentation", False))

            if not question_text:
                continue

            selection_decision = self._resolve_selection_decision(
                question_text=question_text,
                item_metadata=item_metadata,
                form_metadata=metadata,
                decision_map=decision_map,
            )

            analysis_item_metadata = {
                **(metadata or {}),
                **item_metadata,
                "skip_segmentation": skip_segmentation,
                "selection_decision": selection_decision,
                "selection_source": "llm_form_selector",
            }

            if selection_decision == "analyze":
                analyzed = await self.survey_analyzer.analyze(
                    survey_id=survey_id,
                    question_id=question_id,
                    question_text=question_text,
                    response_text=response_text,
                    response_id=input_response_id,
                    metadata=analysis_item_metadata,
                    request_id=request_id,
                    client_id=client_id,
                    source_endpoint="/surveys/analyze"
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
                    response_id=input_response_id,
                    metadata={
                        **analysis_item_metadata,
                        "skip_reason": "question_not_selected",
                        "force_ignore": True,
                    },
                    request_id=request_id,
                    client_id=client_id,
                    source_endpoint="/surveys/analyze"
                )

                response_results.append(
                    {
                        "response_id": ignored["response_id"],
                        "question_id": question_id,
                        "question_text": question_text,
                        "selection_decision": "ignore",
                        "points": ignored["points"],
                    }
                )

        return {
            "survey_id": survey_id,
            "question_decisions": question_decisions,
            "responses": response_results,
        }