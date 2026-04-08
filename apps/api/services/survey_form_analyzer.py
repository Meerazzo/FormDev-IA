"""
Analyse d'un formulaire complet de satisfaction.

Ce service orchestre :
- l'extraction des questions distinctes,
- la sélection des questions pertinentes,
- le stockage des réponses,
- l'analyse unitaire des réponses retenues.
"""
from utils.dev_csv_export import export_latest_form_result_to_csv
from typing import Any, Dict, List, Optional

from services.survey_analyzer import SurveyAnalyzerService
from services.survey_question_selector import SurveyQuestionSelectorService
from core.feature_config import (
    SURVEY_FORM_MAX_DISTINCT_QUESTIONS,
    SURVEY_FORM_MAX_ITEMS,
    SURVEY_FORM_MAX_RESPONSE_LENGTH,
)

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
    def _build_question_decision_map(question_decisions: List[Dict[str, str]]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for item in question_decisions:
            question_text = " ".join((item.get("question_text") or "").strip().split())
            decision = (item.get("decision") or "").strip().lower()

            if not question_text or decision not in {"analyze", "ignore"}:
                continue

            mapping[question_text.lower()] = decision

        return mapping

    async def analyze_form(
        self,
        survey_id: str,
        items: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_form_payload(items)
        distinct_questions = self.question_selector.extract_distinct_questions(items)
        if len(distinct_questions) > SURVEY_FORM_MAX_DISTINCT_QUESTIONS:
            raise ValueError(
                f"Too many distinct questions: {len(distinct_questions)}. "
                f"Maximum allowed is {SURVEY_FORM_MAX_DISTINCT_QUESTIONS}."
            )
        selection_result = await self.question_selector.select_questions_in_chunks(distinct_questions)

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
                # Même si la question est ignorée, on stocke la réponse
                # dans survey_responses pour conserver la traçabilité du formulaire.
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

        result = {
            "survey_id": survey_id,
            "question_decisions": question_decisions,
            "responses": response_results,
        }

        try:
            export_latest_form_result_to_csv(result)
        except Exception:
            pass

        return result