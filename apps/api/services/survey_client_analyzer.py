from typing import Any, Dict, List, Optional, Tuple

from schemas.survey_client import (
    ClientAnswerOutput,
    ClientOpenQuestionOutput,
    ClientMultipleChoiceQuestionOutput,
    ClientQuestionnaireAnalyzeRequest,
    ClientQuestionnaireAnalyzeResponse,
    ClientQuestionnaireOutput,
    ClientQuestionWithSegmentsOutput,
    ClientSegment,
    ClientSingleChoiceQuestionOutput,
)
from services.survey_client_mapper import SurveyClientInputMapper
from services.survey_form_analyzer import SurveyFormAnalyzerService


class SurveyClientAnalyzerService:
    def __init__(self, form_analyzer: SurveyFormAnalyzerService):
        self.form_analyzer = form_analyzer

    async def analyze(
        self,
        payload: ClientQuestionnaireAnalyzeRequest,
        request_id: str | None = None,
        client_id: str | None = None,
    ) -> ClientQuestionnaireAnalyzeResponse:
        flattened = SurveyClientInputMapper.flatten_request(payload)

        questionnaires_output: List[ClientQuestionnaireOutput] = []

        for questionnaire_input, flat in zip(payload.questionnaires, flattened):
            analysis_metadata = {
                **(flat.get("metadata") or {}),
                "source_format": "client_questionnaire_v1",
            }

            questionnaire_client_id = questionnaire_input.metadata.get("client_id")

            effective_client_id = client_id or questionnaire_client_id

            if not effective_client_id:
                raise ValueError("metadata.client_id is required")

            analysis_metadata["client_id"] = str(effective_client_id)

            result = await self.form_analyzer._analyze_form_payload(
                survey_id=flat["survey_id"],
                items=flat["items"],
                metadata=analysis_metadata,
                request_id=request_id,
                client_id=str(effective_client_id),
            )

            response_points_map = self._build_response_points_map(result)
            response_locator_map = self._build_response_locator_map(flat["items"])

            questionnaire_output = self._rebuild_questionnaire(
                original=questionnaire_input,
                response_points_map=response_points_map,
                response_locator_map=response_locator_map,
            )
            questionnaires_output.append(questionnaire_output)

        return ClientQuestionnaireAnalyzeResponse(
            questionnaires=questionnaires_output
        )

    def _build_response_points_map(
        self,
        result: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        responses = result.get("responses", [])
        return {
            response["response_id"]: response.get("points", [])
            for response in responses
        }

    def _build_response_locator_map(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, str, Optional[str]], str]:
        """
        Construit un index de correspondance :
        (questionnaire_id, question_id, answer_id) -> response_id

        - answer_id est None pour RATING / CHECKBOX
        """
        locator: Dict[Tuple[str, str, Optional[str]], str] = {}

        for item in items:
            metadata = item.get("metadata") or {}
            questionnaire_id = str(metadata.get("questionnaire_id"))
            question_id = str(item.get("question_id"))
            answer_id = metadata.get("answer_id")
            if answer_id is not None:
                answer_id = str(answer_id)

            response_id = str(item.get("response_id"))

            locator[(questionnaire_id, question_id, answer_id)] = response_id

        return locator

    def _get_points_for_answer(
        self,
        *,
        questionnaire_id: int,
        question_id: int,
        answer_id: Optional[int],
        response_locator_map: Dict[Tuple[str, str, Optional[str]], str],
        response_points_map: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        key = (
            str(questionnaire_id),
            str(question_id),
            str(answer_id) if answer_id is not None else None,
        )
        response_id = response_locator_map.get(key)
        if not response_id:
            return []
        return response_points_map.get(response_id, [])

    def _map_segments(
        self,
        *,
        points: List[Dict[str, Any]],
        available_categories: List[Any],
    ) -> List[ClientSegment]:
        sentiment_map = {
            1: "VERY_NEGATIVE",
            2: "NEGATIVE",
            3: "NEUTRAL",
            4: "POSITIVE",
            5: "VERY_POSITIVE",
        }

        category_id_by_label = {
            str(category.label): category.id
            for category in available_categories
        }

        fallback_category_id = available_categories[0].id if available_categories else 0

        segments: List[ClientSegment] = []
        for point in points:
            category_label = point.get("category")
            category_id = category_id_by_label.get(category_label, fallback_category_id)

            segments.append(
                ClientSegment(
                    point_id=point.get("point_id"),
                    text=point.get("text", ""),
                    sentiment=sentiment_map.get(point.get("sentiment", 3), "NEUTRAL"),
                    categoryId=category_id,
                )
            )

        return segments

    def _rebuild_questionnaire(
        self,
        *,
        original,
        response_points_map: Dict[str, List[Dict[str, Any]]],
        response_locator_map: Dict[Tuple[str, str, Optional[str]], str],
    ) -> ClientQuestionnaireOutput:
        questions_output = []

        for question in original.questions:
            q_type = question.type

            if q_type == "OPEN":
                questions_output.append(
                    self._build_open_question(
                        questionnaire_id=original.id,
                        question=question,
                        available_categories=original.availableCategories,
                        response_locator_map=response_locator_map,
                        response_points_map=response_points_map,
                    )
                )

            elif q_type == "SINGLE_CHOICE":
                questions_output.append(
                    self._build_single_choice_question(
                        questionnaire_id=original.id,
                        question=question,
                        available_categories=original.availableCategories,
                        response_locator_map=response_locator_map,
                        response_points_map=response_points_map,
                    )
                )

            elif q_type == "MULTIPLE_CHOICE":
                questions_output.append(
                    self._build_multiple_choice_question(
                        questionnaire_id=original.id,
                        question=question,
                        available_categories=original.availableCategories,
                        response_locator_map=response_locator_map,
                        response_points_map=response_points_map,
                    )
                )

            elif q_type == "RATING":
                questions_output.append(
                    self._build_rating_question(
                        questionnaire_id=original.id,
                        question=question,
                        available_categories=original.availableCategories,
                        response_locator_map=response_locator_map,
                        response_points_map=response_points_map,
                    )
                )

            elif q_type == "CHECKBOX":
                questions_output.append(
                    self._build_checkbox_question(
                        questionnaire_id=original.id,
                        question=question,
                        available_categories=original.availableCategories,
                        response_locator_map=response_locator_map,
                        response_points_map=response_points_map,
                    )
                )

        return ClientQuestionnaireOutput(
            id=original.id,
            availableCategories=original.availableCategories,
            questions=questions_output,
            metadata=original.metadata,
        )

    def _build_open_question(
        self,
        *,
        questionnaire_id: int,
        question,
        available_categories: List[Any],
        response_locator_map: Dict[Tuple[str, str, Optional[str]], str],
        response_points_map: Dict[str, List[Dict[str, Any]]],
    ) -> ClientOpenQuestionOutput:
        answers_output: List[ClientAnswerOutput] = []

        for answer in question.answers:
            points = self._get_points_for_answer(
                questionnaire_id=questionnaire_id,
                question_id=question.id,
                answer_id=answer.id,
                response_locator_map=response_locator_map,
                response_points_map=response_points_map,
            )
            key = (
                str(questionnaire_id),
                str(question.id),
                str(answer.id),
            )
            response_id = response_locator_map.get(key)
            answers_output.append(
                ClientAnswerOutput(
                    id=answer.id,
                    response_id=response_id,
                    segments=self._map_segments(
                        points=points,
                        available_categories=available_categories,
                    ),
                    metadata=answer.metadata,
                )
            )

        return ClientOpenQuestionOutput(
            id=question.id,
            answers=answers_output,
            metadata=question.metadata,
        )

    def _build_single_choice_question(
        self,
        *,
        questionnaire_id: int,
        question,
        available_categories: List[Any],
        response_locator_map: Dict[Tuple[str, str, Optional[str]], str],
        response_points_map: Dict[str, List[Dict[str, Any]]],
    ) -> ClientSingleChoiceQuestionOutput:
        answer_output = None

        if question.answer is not None:
            points = self._get_points_for_answer(
                questionnaire_id=questionnaire_id,
                question_id=question.id,
                answer_id=question.answer.id,
                response_locator_map=response_locator_map,
                response_points_map=response_points_map,
            )
            key = (
                str(questionnaire_id),
                str(question.id),
                str(question.answer.id),
            )
            response_id = response_locator_map.get(key)
            answer_output = ClientAnswerOutput(
                id=question.answer.id,
                response_id=response_id,
                segments=self._map_segments(
                    points=points,
                    available_categories=available_categories,
                ),
                metadata=question.answer.metadata,
            )

        return ClientSingleChoiceQuestionOutput(
            id=question.id,
            answer=answer_output,
            metadata=question.metadata,
        )

    def _build_multiple_choice_question(
        self,
        *,
        questionnaire_id: int,
        question,
        available_categories: List[Any],
        response_locator_map: Dict[Tuple[str, str, Optional[str]], str],
        response_points_map: Dict[str, List[Dict[str, Any]]],
    ) -> ClientMultipleChoiceQuestionOutput:
        answers_output: List[ClientAnswerOutput] = []

        for answer in question.answers:
            points = self._get_points_for_answer(
                questionnaire_id=questionnaire_id,
                question_id=question.id,
                answer_id=answer.id,
                response_locator_map=response_locator_map,
                response_points_map=response_points_map,
            )
            key = (
                str(questionnaire_id),
                str(question.id),
                str(answer.id),
            )
            response_id = response_locator_map.get(key)
            answers_output.append(
                ClientAnswerOutput(
                    id=answer.id,
                    response_id=response_id,
                    segments=self._map_segments(
                        points=points,
                        available_categories=available_categories,
                    ),
                    metadata=answer.metadata,
                )
            )

        return ClientMultipleChoiceQuestionOutput(
            id=question.id,
            answers=answers_output,
            metadata=question.metadata,
        )

    def _build_rating_question(
        self,
        *,
        questionnaire_id: int,
        question,
        available_categories: List[Any],
        response_locator_map: Dict[Tuple[str, str, Optional[str]], str],
        response_points_map: Dict[str, List[Dict[str, Any]]],
    ) -> ClientQuestionWithSegmentsOutput:
        points = self._get_points_for_answer(
            questionnaire_id=questionnaire_id,
            question_id=question.id,
            answer_id=None,
            response_locator_map=response_locator_map,
            response_points_map=response_points_map,
        )
        key = (
            str(questionnaire_id),
            str(question.id),
            None,
        )
        response_id = response_locator_map.get(key)
        
        return ClientQuestionWithSegmentsOutput(
            id=question.id,
            response_id=response_id,
            segments=self._map_segments(
                points=points,
                available_categories=available_categories,
            ),
            metadata=question.metadata,
        )

    def _build_checkbox_question(
        self,
        *,
        questionnaire_id: int,
        question,
        available_categories: List[Any],
        response_locator_map: Dict[Tuple[str, str, Optional[str]], str],
        response_points_map: Dict[str, List[Dict[str, Any]]],
    ) -> ClientQuestionWithSegmentsOutput:
        points = self._get_points_for_answer(
            questionnaire_id=questionnaire_id,
            question_id=question.id,
            answer_id=None,
            response_locator_map=response_locator_map,
            response_points_map=response_points_map,
        )
        key = (
            str(questionnaire_id),
            str(question.id),
            None,
        )
        response_id = response_locator_map.get(key)

        return ClientQuestionWithSegmentsOutput(
            id=question.id,
            response_id=response_id,
            segments=self._map_segments(
                points=points,
                available_categories=available_categories,
            ),
            metadata=question.metadata,
        )