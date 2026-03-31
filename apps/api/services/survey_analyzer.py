"""
Pipeline d'analyse des réponses ouvertes de questionnaires de satisfaction.

Ce service orchestre les différentes étapes du projet 3 :
- normalisation de la réponse,
- filtrage des cas non exploitables,
- segmentation en points élémentaires,
- classification de chaque point,
- persistance des résultats en base,
- journalisation des appels IA.
"""

import time
import uuid
from typing import Any, Dict, List, Optional

from db.models.survey_response import SurveyResponse
from db.models.response_point import ResponsePoint
from services.interaction_logger import (
    log_ai_interaction_error,
    log_ai_interaction_success,
)
from utils.json import parse_json_lenient

from core.feature_config import (
    SURVEY_ANALYSIS_ALLOWED_CATEGORIES,
    SURVEY_ANALYSIS_CLASSIFICATION_MAX_TOKENS,
    SURVEY_ANALYSIS_CLASSIFICATION_TEMPERATURE,
    SURVEY_ANALYSIS_EMPTY_MARKERS,
    SURVEY_ANALYSIS_NAME,
    SURVEY_ANALYSIS_PIPELINE_NAME,
    SURVEY_ANALYSIS_PIPELINE_VERSION,
    SURVEY_ANALYSIS_PROMPT_VERSION,
    SURVEY_ANALYSIS_SEGMENTATION_MAX_TOKENS,
    SURVEY_ANALYSIS_SEGMENTATION_SYSTEM_PROMPT,
    SURVEY_ANALYSIS_SEGMENTATION_TEMPERATURE,
    SURVEY_ANALYSIS_SHORT_OPINIONS,
    SURVEY_ANALYSIS_TOP_P,
    build_survey_analysis_classification_system_prompt,
)


class SurveyAnalyzerService:
    """
    Service métier principal du projet 3.

    Il reçoit une réponse ouverte issue d'un questionnaire et retourne une
    représentation structurée composée de points, chacun enrichi d'un sentiment
    et d'une catégorie métier.
    """
    PIPELINE_NAME = SURVEY_ANALYSIS_PIPELINE_NAME
    PIPELINE_VERSION = SURVEY_ANALYSIS_PIPELINE_VERSION
    PROMPT_VERSION = SURVEY_ANALYSIS_PROMPT_VERSION
    ALLOWED_CATEGORIES = SURVEY_ANALYSIS_ALLOWED_CATEGORIES

    def __init__(self, vllm_client, db):
        self.vllm_client = vllm_client
        self.db = db

    def _normalize_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return " ".join(text.strip().split())

    def _is_empty_or_ignorable(self, text: str) -> bool:
        return text.lower().strip() in SURVEY_ANALYSIS_EMPTY_MARKERS

    def _get_short_opinion(self, text: str) -> Optional[tuple[str, str]]:
        return SURVEY_ANALYSIS_SHORT_OPINIONS.get(text.lower().strip())

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
        sentiment: str,
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
        sentiment: str,
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

        cleaned = []
        for point in points:
            if isinstance(point, str):
                normalized = self._normalize_text(point)
                if normalized:
                    cleaned.append(normalized)
        return cleaned

    def _normalize_classification_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        # Le modèle peut parfois retourner une catégorie hors taxonomie.
        # On force alors un fallback contrôlé vers "unknown".
        category = result.get("category", "unknown")
        if category not in self.ALLOWED_CATEGORIES:
            category = "unknown"

        sentiment = result.get("sentiment", "unknown")
        if sentiment not in {"positive", "negative", "neutral", "unknown"}:
            sentiment = "unknown"

        return {
            "sentiment": sentiment,
            "category": category,
            "confidence": result.get("confidence"),
        }

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
        """
        Analyse une réponse ouverte issue d'un questionnaire de satisfaction.

        Étapes :
        1. génération d'un identifiant technique unique pour la réponse,
        2. normalisation du texte,
        3. gestion des réponses vides ou non exploitables,
        4. segmentation en points,
        5. classification de chaque point,
        6. stockage en base,
        7. retour du résultat structuré.

        Returns:
            Un dictionnaire contenant :
            - response_id
            - points
        """
        # L'identifiant technique de réponse est généré côté backend
        # afin d'éviter les collisions et de ne pas dépendre du client.

        response_id = str(uuid.uuid4())
        normalized_text = self._normalize_text(response_text)

        response = self._build_response_record(
            survey_id=survey_id,
            question_id=question_id,
            question_text=question_text,
            response_id=response_id,
            response_text=normalized_text,
            metadata=metadata,
        )
        self.db.add(response)
        self.db.flush()

        if self._is_empty_or_ignorable(normalized_text):
            self._finalize_response(response)
            return {"response_id": response_id, "points": []}

        short_opinion = self._get_short_opinion(normalized_text)
        if short_opinion:
            sentiment, category = short_opinion
            result = self._build_short_opinion_result(
                response_id=response_id,
                text=normalized_text,
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
            self._finalize_response(response)
            return result

        segmented_points = await self._segment(
            question_text=question_text,
            response_text=normalized_text,
            metadata=metadata,
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
                question_text=question_text,
                point_text=point_text,
                metadata=metadata,
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
        """
        Découpe une réponse libre en une liste de points élémentaires.

        Le modèle doit retourner uniquement un JSON du type :
        {"points": ["...", "..."]}

        Returns:
            Une liste de points textuels nettoyés.
        """
        messages = [
            {
                "role": "system",
                "content": SURVEY_ANALYSIS_SEGMENTATION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f'{{"question_text": "{question_text}", '
                    f'"response_text": "{response_text}", '
                    f'"metadata": {metadata or {}}}}'
                ),
            },
        ]

        result = await self._call_model_json(
            # Le logging ne doit jamais casser le pipeline principal.
            # Toute erreur de log est donc volontairement absorbée.
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
        """
        Attribue un sentiment et une catégorie à un point déjà segmenté.

        Returns:
            Un dictionnaire avec :
            - sentiment
            - category
            - confidence
        """
        messages = [
            {
                "role": "system",
                "content": build_survey_analysis_classification_system_prompt(self.ALLOWED_CATEGORIES),
            },
            {
                "role": "user",
                "content": (
                    f'{{"question_text": "{question_text}", '
                    f'"point_text": "{point_text}", '
                    f'"metadata": {metadata or {}}}}'
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
        """
        Appelle le modèle, tente de parser la sortie JSON et journalise l'interaction.

        Cette méthode centralise :
        - l'appel à vLLM,
        - la mesure de latence,
        - le parsing JSON,
        - le logging de succès / erreur dans ai_interactions.
        """
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