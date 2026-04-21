"""
Pipeline d'analyse des réponses de questionnaires de satisfaction.
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from core.config import settings
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
from services.survey_example_memory import SurveyExampleMemoryService
from services.survey_preprocessor import SurveyPreprocessor
from utils.json import parse_json_lenient

logger = logging.getLogger(__name__)


class SurveyAnalyzerService:
    PIPELINE_NAME = SURVEY_ANALYSIS_PIPELINE_NAME
    PIPELINE_VERSION = SURVEY_ANALYSIS_PIPELINE_VERSION
    PROMPT_VERSION = SURVEY_ANALYSIS_PROMPT_VERSION
    FALLBACK_ALLOWED_CATEGORIES = SURVEY_ANALYSIS_ALLOWED_CATEGORIES

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

    @staticmethod
    def _normalize_label(value: Optional[str]) -> str:
        if not value:
            return ""
        return " ".join(value.strip().split()).lower()

    def _get_allowed_categories(self, metadata: Optional[Dict[str, Any]]) -> List[str]:
        available_categories = (metadata or {}).get("available_categories") or []
        labels: List[str] = []

        for category in available_categories:
            if not isinstance(category, dict):
                continue

            label = self._normalize_text(category.get("label"))
            if label:
                labels.append(label)

        if labels:
            return labels

        return list(self.FALLBACK_ALLOWED_CATEGORIES)

    def _build_normalized_category_map(
        self,
        allowed_categories: List[str],
    ) -> Dict[str, str]:
        normalized_map: Dict[str, str] = {}

        for category in allowed_categories:
            normalized = self._normalize_label(category)
            if normalized:
                normalized_map[normalized] = category

        return normalized_map

    def _resolve_category(
        self,
        raw_category: Optional[str],
        allowed_categories: List[str],
    ) -> str:
        if not allowed_categories:
            return "unknown"

        normalized_map = self._build_normalized_category_map(allowed_categories)
        normalized_raw = self._normalize_label(raw_category)

        if normalized_raw in normalized_map:
            return normalized_map[normalized_raw]

        logger.warning(
            "Classification returned unknown category '%s'. Falling back to first allowed category '%s'.",
            raw_category,
            allowed_categories[0],
        )
        return allowed_categories[0]

    def _build_response_record(
        self,
        survey_id: str,
        question_id: str,
        question_text: str,
        response_id: str,
        response_text: str,
        metadata: Optional[Dict[str, Any]],
    ) -> SurveyResponse:
        question_type = (metadata or {}).get("question_type")
        response_type = "open" if question_type == "OPEN" else "structured"

        return SurveyResponse(
            survey_id=survey_id,
            question_id=question_id,
            question_text=question_text,
            response_id=response_id,
            response_text=response_text,
            response_type=response_type,
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

    def _save_point(
        self,
        response_id: str,
        point: Dict[str, Any],
    ) -> None:
        """
        Persiste un point dans les deux tables :
        - response_points : sortie brute modèle
        - validated_response_points : version finale initiale
        """
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

    def _normalize_classification_result(
        self,
        result: Dict[str, Any],
        allowed_categories: List[str],
    ) -> Dict[str, Any]:
        category = self._resolve_category(
            raw_category=result.get("category"),
            allowed_categories=allowed_categories,
        )

        sentiment = result.get("sentiment")
        if sentiment not in {1, 2, 3, 4, 5}:
            sentiment = 3

        return {
            "sentiment": sentiment,
            "category": category,
            "confidence": result.get("confidence"),
        }

    def _get_few_shot_examples(
        self,
        question_text: str,
        point_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        client_id = (metadata or {}).get("client_id")
        question_type = (metadata or {}).get("question_type")
        allowed_categories = self._get_allowed_categories(metadata)

        if not client_id:
            return []

        try:
            raw_examples = self.example_memory.search_similar_examples(
                client_id=client_id,
                question_text=question_text,
                input_point_text=point_text,
                allowed_categories=allowed_categories,
                question_type=question_type,
                limit=max(limit * 3, 10),
            )

            deduplicated: List[Dict[str, Any]] = []
            seen: set[tuple] = set()

            for ex in raw_examples:
                key = (
                    ex.get("question_text"),
                    ex.get("input_point_text"),
                    ex.get("final_category"),
                    ex.get("final_sentiment"),
                )
                if key in seen:
                    continue
                seen.add(key)
                deduplicated.append(ex)

                if len(deduplicated) >= limit:
                    break

            return deduplicated

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
        response_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
        source_endpoint: str = "/surveys/forms/analyze",
    ) -> Dict[str, Any]:
        """
        Analyse une réponse unitaire :
        - preprocessing
        - sortie anticipée si non pertinente
        - segmentation ou bypass segmentation
        - classification
        - persistance
        """
        response_id = response_id or str(uuid.uuid4())

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

        if bool((metadata or {}).get("force_ignore")) or not pre["should_analyze"]:
            self._finalize_response(response)
            return {"response_id": response_id, "points": []}

        allowed_categories = self._get_allowed_categories(analysis_metadata)
        skip_segmentation = bool((analysis_metadata or {}).get("skip_segmentation", False))
        has_dynamic_categories = bool((analysis_metadata or {}).get("available_categories"))

        # On désactive le shortcut "short_simple_opinion" lorsque :
        # - on est sur un mode catégories dynamiques
        # - ou quand on a explicitement demandé de bypass la segmentation
        if (
            not has_dynamic_categories
            and not skip_segmentation
            and pre["response_kind"] == "short_simple_opinion"
            and pre["short_opinion"]
        ):
            shortcut_category = self._resolve_category(
                raw_category=pre["short_opinion"]["category"],
                allowed_categories=allowed_categories,
            )

            result = self._build_short_opinion_result(
                response_id=response_id,
                text=normalized_response_text,
                sentiment=pre["short_opinion"]["sentiment"],
                category=shortcut_category,
            )

            self._save_point(response_id, result["points"][0])
            self._finalize_response(response)
            return result

        if skip_segmentation:
            segmented_points = [normalized_response_text] if normalized_response_text else []
        else:
            segmented_points = await self._segment(
                question_text=normalized_question_text,
                response_text=normalized_response_text,
                metadata=analysis_metadata,
                response_id=response_id,
                request_id=request_id,
                client_id=client_id,
                source_endpoint=source_endpoint,
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
                source_endpoint=source_endpoint,
            )

            point = {
                "point_id": f"{response_id}_pt_{idx}",
                "text": point_text,
                "sentiment": cls["sentiment"],
                "category": cls["category"],
                "confidence": cls["confidence"],
            }

            points.append(point)
            self._save_point(response_id, point)

        self._finalize_response(response)

        return {
            "response_id": response_id,
            "points": points,
        }

    async def _segment(
        self,
        question_text: str,
        response_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        response_id: Optional[str] = None,
        request_id: Optional[str] = None,
        client_id: Optional[str] = None,
        source_endpoint: str = "/surveys/forms/analyze",
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
            endpoint=source_endpoint,
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
        source_endpoint: str = "/surveys/forms/analyze",
    ) -> Dict[str, Any]:
        allowed_categories = self._get_allowed_categories(metadata)

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
                    allowed_categories,
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
            endpoint=source_endpoint,
            metadata={
                **(metadata or {}),
                "question_text": question_text,
                "point_text": point_text,
                "stage": "classification",
            },
        )

        return self._normalize_classification_result(result, allowed_categories)

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
        endpoint: str = "/surveys/forms/analyze",
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
                    endpoint=endpoint,
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
                    endpoint=endpoint,
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