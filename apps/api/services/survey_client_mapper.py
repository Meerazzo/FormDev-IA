from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from schemas.survey_client import (
    ClientCheckboxQuestionInput,
    ClientMultipleChoiceQuestionInput,
    ClientOpenQuestionInput,
    ClientQuestionInput,
    ClientQuestionnaireAnalyzeRequest,
    ClientQuestionnaireInput,
    ClientRatingQuestionInput,
    ClientSingleChoiceQuestionInput,
)


class SurveyClientInputMapper:
    """
    Transforme le format client "questionnaires/questions/answers"
    vers le format interne attendu par le pipeline de traitement.

    Le résultat produit une liste de questionnaires aplatis :
    - survey_id
    - questionnaire_id
    - items[]
      - question_id
      - response_id
      - question_text
      - response_text
      - skip_segmentation
      - metadata
    - metadata
    - original_questionnaire
    """

    @staticmethod
    def _new_response_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        if value is None:
            return ""
        return " ".join(value.strip().split())

    @staticmethod
    def _light_categories(categories: List[Any]) -> List[Dict[str, Any]]:
        return [
            {
                "id": category.id,
                "label": category.label,
            }
            for category in categories
        ]

    @staticmethod
    def _light_available_answers(
        available_answers: Optional[List[Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        if available_answers is None:
            return None

        return [
            {
                "id": answer.id,
                "label": answer.label,
            }
            for answer in available_answers
        ]

    @staticmethod
    def _base_metadata(
        *,
        questionnaire_id: int,
        question_id: int,
        question_type: str,
        available_categories: List[Any],
        question_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "questionnaire_id": str(questionnaire_id),
            "question_type": question_type,
            "answer_id": None,
            "selected_answer_id": None,
            "available_categories": SurveyClientInputMapper._light_categories(
                available_categories
            ),
            "available_answers": None,
            "value": None,
            "max_value": None,
            "checked": None,
            "question_metadata": question_metadata,
            "answer_metadata": None,
            "client_question_id": str(question_id),
            "client_answer_id": None,
        }

    @classmethod
    def _map_open_question(
        cls,
        *,
        questionnaire_id: int,
        available_categories: List[Any],
        question: ClientOpenQuestionInput,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        for answer in question.answers:
            if answer.type != "FREE_TEXT":
                continue

            response_text = cls._normalize_text(answer.label)
            if not response_text:
                continue

            metadata = cls._base_metadata(
                questionnaire_id=questionnaire_id,
                question_id=question.id,
                question_type=question.type,
                available_categories=available_categories,
                question_metadata=question.metadata,
            )
            metadata["answer_id"] = str(answer.id)
            metadata["client_answer_id"] = str(answer.id)
            metadata["answer_metadata"] = answer.metadata

            items.append(
                {
                    "question_id": str(question.id),
                    "response_id": cls._new_response_id(),
                    "question_text": question.label,
                    "response_text": response_text,
                    "skip_segmentation": False,
                    "metadata": metadata,
                }
            )

        return items

    @classmethod
    def _map_single_choice_question(
        cls,
        *,
        questionnaire_id: int,
        available_categories: List[Any],
        question: ClientSingleChoiceQuestionInput,
    ) -> List[Dict[str, Any]]:
        if question.answer is None:
            return []

        selected_id = question.answer.idAvailableAnswer
        selected_label = None

        for available_answer in question.availableAnswers:
            if available_answer.id == selected_id:
                selected_label = available_answer.label
                break

        response_text = cls._normalize_text(selected_label)
        if not response_text:
            return []

        metadata = cls._base_metadata(
            questionnaire_id=questionnaire_id,
            question_id=question.id,
            question_type=question.type,
            available_categories=available_categories,
            question_metadata=question.metadata,
        )
        metadata["answer_id"] = str(question.answer.id)
        metadata["client_answer_id"] = str(question.answer.id)
        metadata["selected_answer_id"] = selected_id
        metadata["available_answers"] = cls._light_available_answers(
            question.availableAnswers
        )
        metadata["answer_metadata"] = question.answer.metadata

        return [
            {
                "question_id": str(question.id),
                "response_id": cls._new_response_id(),
                "question_text": question.label,
                "response_text": response_text,
                "skip_segmentation": True,
                "metadata": metadata,
            }
        ]

    @classmethod
    def _map_multiple_choice_question(
        cls,
        *,
        questionnaire_id: int,
        available_categories: List[Any],
        question: ClientMultipleChoiceQuestionInput,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        available_answer_map = {
            answer.id: answer.label for answer in question.availableAnswers
        }

        for answer in question.answers:
            selected_label = available_answer_map.get(answer.idAvailableAnswer)
            response_text = cls._normalize_text(selected_label)
            if not response_text:
                continue

            metadata = cls._base_metadata(
                questionnaire_id=questionnaire_id,
                question_id=question.id,
                question_type=question.type,
                available_categories=available_categories,
                question_metadata=question.metadata,
            )
            metadata["answer_id"] = str(answer.id)
            metadata["client_answer_id"] = str(answer.id)
            metadata["selected_answer_id"] = answer.idAvailableAnswer
            metadata["available_answers"] = cls._light_available_answers(
                question.availableAnswers
            )
            metadata["answer_metadata"] = answer.metadata

            items.append(
                {
                    "question_id": str(question.id),
                    "response_id": cls._new_response_id(),
                    "question_text": question.label,
                    "response_text": response_text,
                    "skip_segmentation": True,
                    "metadata": metadata,
                }
            )

        return items

    @classmethod
    def _map_rating_question(
        cls,
        *,
        questionnaire_id: int,
        available_categories: List[Any],
        question: ClientRatingQuestionInput,
    ) -> List[Dict[str, Any]]:
        if question.value is None:
            return []

        response_text = f"Note: {question.value}/{question.maxValue}"

        metadata = cls._base_metadata(
            questionnaire_id=questionnaire_id,
            question_id=question.id,
            question_type=question.type,
            available_categories=available_categories,
            question_metadata=question.metadata,
        )
        metadata["value"] = question.value
        metadata["max_value"] = question.maxValue

        return [
            {
                "question_id": str(question.id),
                "response_id": cls._new_response_id(),
                "question_text": question.label,
                "response_text": response_text,
                "skip_segmentation": True,
                "metadata": metadata,
            }
        ]

    @classmethod
    def _map_checkbox_question(
        cls,
        *,
        questionnaire_id: int,
        available_categories: List[Any],
        question: ClientCheckboxQuestionInput,
    ) -> List[Dict[str, Any]]:
        if question.checked is None:
            return []

        response_text = "Oui" if question.checked else "Non"

        metadata = cls._base_metadata(
            questionnaire_id=questionnaire_id,
            question_id=question.id,
            question_type=question.type,
            available_categories=available_categories,
            question_metadata=question.metadata,
        )
        metadata["checked"] = question.checked

        return [
            {
                "question_id": str(question.id),
                "response_id": cls._new_response_id(),
                "question_text": question.label,
                "response_text": response_text,
                "skip_segmentation": True,
                "metadata": metadata,
            }
        ]

    @classmethod
    def _map_question(
        cls,
        *,
        questionnaire_id: int,
        available_categories: List[Any],
        question: ClientQuestionInput,
    ) -> List[Dict[str, Any]]:
        if isinstance(question, ClientOpenQuestionInput):
            return cls._map_open_question(
                questionnaire_id=questionnaire_id,
                available_categories=available_categories,
                question=question,
            )

        if isinstance(question, ClientSingleChoiceQuestionInput):
            return cls._map_single_choice_question(
                questionnaire_id=questionnaire_id,
                available_categories=available_categories,
                question=question,
            )

        if isinstance(question, ClientMultipleChoiceQuestionInput):
            return cls._map_multiple_choice_question(
                questionnaire_id=questionnaire_id,
                available_categories=available_categories,
                question=question,
            )

        if isinstance(question, ClientRatingQuestionInput):
            return cls._map_rating_question(
                questionnaire_id=questionnaire_id,
                available_categories=available_categories,
                question=question,
            )

        if isinstance(question, ClientCheckboxQuestionInput):
            return cls._map_checkbox_question(
                questionnaire_id=questionnaire_id,
                available_categories=available_categories,
                question=question,
            )

        raise ValueError(f"Unsupported question type: {type(question).__name__}")

    @classmethod
    def flatten_questionnaire(
        cls,
        *,
        questionnaire: ClientQuestionnaireInput,
    ) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []

        for question in questionnaire.questions:
            items.extend(
                cls._map_question(
                    questionnaire_id=questionnaire.id,
                    available_categories=questionnaire.availableCategories,
                    question=question,
                )
            )

        return {
            "survey_id": str(questionnaire.id),
            "questionnaire_id": questionnaire.id,
            "items": items,
            "metadata": questionnaire.metadata,
            "original_questionnaire": questionnaire.model_dump(),
        }

    @classmethod
    def flatten_request(
        cls,
        payload: ClientQuestionnaireAnalyzeRequest,
    ) -> List[Dict[str, Any]]:
        """
        Retourne une liste de questionnaires aplatis.
        Chaque élément contient :
        - survey_id
        - questionnaire_id
        - items
        - metadata
        - original_questionnaire
        """
        return [
            cls.flatten_questionnaire(questionnaire=questionnaire)
            for questionnaire in payload.questionnaires
        ]