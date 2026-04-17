"""
Pipeline d'analyse des réponses ouvertes de questionnaires de satisfaction.
"""

import json
import time
import uuid
import logging
from typing import Any, Dict, List, Optional
from core.config import settings

logger = logging.getLogger(__name__)
from core.feature_config import (
    SURVEY_ANALYSIS_ALLOWED_CATEGORIES,
    SURVEY_ANALYSIS_CLASSIFICATION_MAX_TOKENS,
    SURVEY_ANALYSIS_CLASSIFICATION_TEMPERATURE,
    SURVEY_ANALYSIS_NAME,
    SURVEY_ANALYSIS_PIPELINE_NAME,
    SURVEY_ANALYSIS_PIPELINE_VERSION,
    SURVEY_ANALYSIS_PROMPT_VERSION,
    SURVEY_ANALYSIS_SEGMENTATION_MAX_TOKENS,
    SURVEY_ANALYSIS_SEGMENTATION_SYSTEM_PROMPT,
    SURVEY_ANALYSIS_SEGMENTATION_TEMPERATURE,
    SURVEY_ANALYSIS_TOP_P,
    build_survey_analysis_classification_system_prompt,
)
from db.models.response_point import ResponsePoint
from db.models.survey_response import SurveyResponse
from db.models.validated_response_point import ValidatedResponsePoint
from services.interaction_logger import (
    log_ai_interaction_error,
    log_ai_interaction_success,
)
from services.survey_preprocessor import SurveyPreprocessor
from services.survey_example_memory import SurveyExampleMemoryService
from utils.json import parse_json_lenient


class SurveyAnalyzerService:
    PIPELINE_NAME = SURVEY_ANALYSIS_PIPELINE_NAME
    PIPELINE_VERSION = SURVEY_ANALYSIS_PIPELINE_VERSION
    PROMPT_VERSION = SURVEY_ANALYSIS_PROMPT_VERSION
    ALLOWED_CATEGORIES = SURVEY_ANALYSIS_ALLOWED_CATEGORIES

    def __init__(self, vllm_client, db):
        self.preprocessor = SurveyPreprocessor()
        self.vllm_client = vllm_client
        self.db = db
        self.example_memory = SurveyExampleMemoryService(
            qdrant_url=settings.QDRANT_URL,
            collection_name=settings.QDRANT_COLLECTION,
            embedding_model=settings.QDRANT_EMBEDDING_MODEL,
            vector_size=settings.QDRANT_VECTOR_SIZE,
        )

    def _normalize_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return " ".join(text.strip().split())

    def _build_response_record(
        self,
        survey_id: str,
        question_id: str,
        question_text: str,
        response_id: str,
        response_text: str,
        metadata: Optional[Dict[str, Any]],
    ) -> SurveyResponse:
        return SurveyResponse(
            survey_id=survey_id,
            question_id=question_id,
            question_text=question_text,
            response_id=response_id,
            response_text=response_text,
            response_type="open",
            status="pending",
            metadata_json=metadata,
            pipeline_name=self.PIPELINE_NAME,
            pipeline_version=self.PIPELINE_VERSION,
            prompt_version=self.PROMPT_VERSION,
        )

    def _build_point_record(
        self,
        response_id: str,
        point_id: str,
        text: str,
        sentiment: int,
        category: str,
        confidence: Optional[float],
    ) -> ResponsePoint:
        return ResponsePoint(
            point_id=point_id,
            response_id=response_id,
            point_text=text,
            sentiment=sentiment,
            category=category,
            confidence=confidence,
            source="model",
            is_active="true",
            pipeline_name=self.PIPELINE_NAME,
            pipeline_version=self.PIPELINE_VERSION,
            prompt_version=self.PROMPT_VERSION,
        )

    def _build_short_opinion_result(
        self,
        response_id: str,
        text: str,
        sentiment: int,
        category: str,
    ) -> Dict[str, Any]:
        return {
            "response_id": response_id,
            "points": [
                {
                    "point_id": f"{response_id}_pt_1",
                    "text": text,
                    "sentiment": sentiment,
                    "category": category,
                    "confidence": None,
                }
            ],
        }

    def _finalize_response(self, response: SurveyResponse) -> None:
        response.status = "processed"
        self.db.commit()

    def _extract_clean_points(self, result: Dict[str, Any]) -> List[str]:
        points = result.get("points", [])
        if not isinstance(points, list):
            return []

        cleaned: List[str] = []
        for point in points:
            if isinstance(point, str):
                normalized = self._normalize_text(point)
                if normalized:
                    cleaned.append(normalized)
        return cleaned

    def _normalize_classification_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        category = result.get("category", "unknown")
        if category not in self.ALLOWED_CATEGORIES:
            category = "unknown"

        sentiment = result.get("sentiment")
        if sentiment not in {1, 2, 3, 4, 5}:
            sentiment = 3

        return {
            "sentiment": sentiment,
            "category": category,
            "confidence": result.get("confidence"),
        }

    def _build_validated_point_record(
        self,
        response_id: str,
        point_id: Optional[str],
        text: str,
        sentiment: Optional[int],
        category: Optional[str],
        source: str = "model",
        operator_id: Optional[str] = None,
    ) -> ValidatedResponsePoint:
        return ValidatedResponsePoint(
            response_id=response_id,
            point_id=point_id,
            final_text=text,
            final_sentiment=sentiment,
            final_category=category,
            source=source,
            is_active="true",
            operator_id=operator_id,
        )

    def _get_few_shot_examples(
        self,
        question_text: str,
        point_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        client_id = (metadata or {}).get("client_id")
        if not client_id:
            return []

        try:
            return self.example_memory.search_similar_examples(
                client_id=client_id,
                question_text=question_text,
                input_point_text=point_text,
                allowed_categories=self.ALLOWED_CATEGORIES,
                limit=limit,
            )
        except Exception as e:
            logger.warning(
                "Qdrant few-shot retrieval failed "
                "(client_id=%s, question_text=%s, point_text=%s): %s",
                client_id,
                question_text,
                point_text,
                str(e),
            )
            return []
        
    async def analyze(
        self,
        survey_id: str,
        question_id: str,
        question_text: str,
        response_text: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        response_id = str(uuid.uuid4())

        pre = self.preprocessor.preprocess(
            question_text=question_text,
            response_text=response_text,
        )
        normalized_question_text = pre["normalized_question_text"]
        normalized_response_text = pre["normalized_response_text"]

        analysis_metadata = {
            **(metadata or {}),
            "response_kind": pre["response_kind"],
            "skip_reason": pre["skip_reason"],
            "question_kind": pre["question_kind"],
        }

        response = self._build_response_record(
            survey_id=survey_id,
            question_id=question_id,
            question_text=normalized_question_text,
            response_id=response_id,
            response_text=normalized_response_text,
            metadata=analysis_metadata,
        )
        self.db.add(response)
        self.db.flush()

        forced_ignore = bool((metadata or {}).get("force_ignore"))
        if forced_ignore:
            self._finalize_response(response)
            return {"response_id": response_id, "points": []}

        if not pre["should_analyze"]:
            self._finalize_response(response)
            return {"response_id": response_id, "points": []}

        if pre["response_kind"] == "short_simple_opinion" and pre["short_opinion"]:
            sentiment = pre["short_opinion"]["sentiment"]
            category = pre["short_opinion"]["category"]

            result = self._build_short_opinion_result(
                response_id=response_id,
                text=normalized_response_text,
                sentiment=sentiment,
                category=category,
            )
            point = result["points"][0]

            self.db.add(
                self._build_point_record(
                    response_id=response_id,
                    point_id=point["point_id"],
                    text=point["text"],
                    sentiment=point["sentiment"],
                    category=point["category"],
                    confidence=point["confidence"],
                )
            )
            self.db.add(
                self._build_validated_point_record(
                    response_id=response_id,
                    point_id=point["point_id"],
                    text=point["text"],
                    sentiment=point["sentiment"],
                    category=point["category"],
                    source="model",
                )
            )
            self._finalize_response(response)
            return result

        segmented_points = await self._segment(
            question_text=normalized_question_text,
            response_text=normalized_response_text,
            metadata=analysis_metadata,
            response_id=response_id,
            request_id=request_id,
            client_id=client_id,
        )

        if not segmented_points:
            self._finalize_response(response)
            return {"response_id": response_id, "points": []}

        points: List[Dict[str, Any]] = []
        for idx, point_text in enumerate(segmented_points, start=1):
            cls = await self._classify(
                question_text=normalized_question_text,
                point_text=point_text,
                metadata=analysis_metadata,
                response_id=response_id,
                request_id=request_id,
                client_id=client_id,
            )

            point = {
                "point_id": f"{response_id}_pt_{idx}",
                "text": point_text,
                "sentiment": cls["sentiment"],
                "category": cls["category"],
                "confidence": cls["confidence"],
            }
            points.append(point)

            self.db.add(
                self._build_point_record(
                    response_id=response_id,
                    point_id=point["point_id"],
                    text=point["text"],
                    sentiment=point["sentiment"],
                    category=point["category"],
                    confidence=point["confidence"],
                )
            )
            self.db.add(
                self._build_validated_point_record(
                    response_id=response_id,
                    point_id=point["point_id"],
                    text=point["text"],
                    sentiment=point["sentiment"],
                    category=point["category"],
                    source="model",
                )
            )

        self._finalize_response(response)
        return {"response_id": response_id, "points": points}

    async def _segment(
        self,
        question_text: str,
        response_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        response_id: Optional[str] = None,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> List[str]:
        messages = [
            {
                "role": "system",
                "content": SURVEY_ANALYSIS_SEGMENTATION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question_text": question_text,
                        "response_text": response_text,
                        "metadata": metadata or {},
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        result = await self._call_model_json(
            feature="survey_segmentation",
            messages=messages,
            max_tokens=SURVEY_ANALYSIS_SEGMENTATION_MAX_TOKENS,
            temperature=SURVEY_ANALYSIS_SEGMENTATION_TEMPERATURE,
            top_p=SURVEY_ANALYSIS_TOP_P,
            response_id=response_id or "unknown_response",
            request_id=request_id,
            client_id=client_id,
            metadata={
                **(metadata or {}),
                "question_text": question_text,
                "stage": "segmentation",
            },
        )

        return self._extract_clean_points(result)

    async def _classify(
        self,
        question_text: str,
        point_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        response_id: Optional[str] = None,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        few_shot_examples = self._get_few_shot_examples(
            question_text=question_text,
            point_text=point_text,
            metadata=metadata,
            limit=3,
        )

        messages = [
            {
                "role": "system",
                "content": build_survey_analysis_classification_system_prompt(
                    self.ALLOWED_CATEGORIES,
                    few_shot_examples=few_shot_examples,
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question_text": question_text,
                        "point_text": point_text,
                        "metadata": metadata or {},
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        result = await self._call_model_json(
            feature="survey_classification",
            messages=messages,
            max_tokens=SURVEY_ANALYSIS_CLASSIFICATION_MAX_TOKENS,
            temperature=SURVEY_ANALYSIS_CLASSIFICATION_TEMPERATURE,
            top_p=SURVEY_ANALYSIS_TOP_P,
            response_id=response_id or "unknown_response",
            request_id=request_id,
            client_id=client_id,
            metadata={
                **(metadata or {}),
                "question_text": question_text,
                "point_text": point_text,
                "stage": "classification",
            },
        )

        return self._normalize_classification_result(result)

    async def _call_model_json(
        self,
        *,
        feature: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float = 0.9,
        response_id: str,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()

        try:
            result = await self.vllm_client.chat(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )

            latency_ms = (time.perf_counter() - t0) * 1000.0
            text = (result.text or "").strip()
            raw = result.raw or {}
            usage = raw.get("usage", {}) if isinstance(raw, dict) else {}

            parsed, parse_mode = parse_json_lenient(text)

            try:
                log_ai_interaction_success(
                    request_id=request_id,
                    project=SURVEY_ANALYSIS_NAME,
                    client_id=client_id,
                    endpoint="/surveys/analyze",
                    feature=feature,
                    model_requested=None,
                    model_used=result.model,
                    input_text=None,
                    messages_json=messages,
                    request_params_json={
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "top_p": top_p,
                    },
                    output_text=text,
                    response_json=raw if isinstance(raw, dict) else {"parsed": parsed},
                    finish_reason=((raw.get("choices") or [{}])[0].get("finish_reason") if isinstance(raw, dict) else None),
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                    latency_ms=round(latency_ms, 1),
                    status_code=200,
                    pipeline_name=self.PIPELINE_NAME,
                    pipeline_version=self.PIPELINE_VERSION,
                    prompt_version=self.PROMPT_VERSION,
                    source_ref=response_id,
                    metadata_json={
                        **(metadata or {}),
                        "parse_mode": parse_mode,
                    },
                )
            except Exception:
                pass

            return parsed

        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0

            try:
                log_ai_interaction_error(
                    request_id=request_id,
                    project=SURVEY_ANALYSIS_NAME,
                    client_id=client_id,
                    endpoint="/surveys/analyze",
                    feature=feature,
                    model_requested=None,
                    input_text=None,
                    messages_json=messages,
                    request_params_json={
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "top_p": top_p,
                    },
                    status_code=502,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    pipeline_name=self.PIPELINE_NAME,
                    pipeline_version=self.PIPELINE_VERSION,
                    prompt_version=self.PROMPT_VERSION,
                    source_ref=response_id,
                    metadata_json={
                        **(metadata or {}),
                        "latency_ms": round(latency_ms, 1),
                    },
                )
            except Exception:
                pass

            raise