"""
Prétraitement simple des réponses ouvertes de questionnaires.

Ce module gère :
- la normalisation du texte,
- la détection des réponses vides ou non exploitables,
- la détection des réponses courtes simples,
- un retour structuré exploitable par le pipeline d'analyse.
"""

from typing import Any, Dict, Optional

from core.feature_config import (
    SURVEY_ANALYSIS_EMPTY_MARKERS,
    SURVEY_ANALYSIS_SHORT_OPINIONS,
)


class SurveyPreprocessor:
    """
    Préprocesseur léger des réponses ouvertes.

    Cette version ne filtre pas encore les questions.
    Elle se concentre uniquement sur la qualité et l'exploitabilité
    de la réponse textuelle.
    """

    def normalize_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return " ".join(text.strip().split())

    def preprocess(
        self,
        question_text: str,
        response_text: Optional[str],
    ) -> Dict[str, Any]:
        normalized_question_text = self.normalize_text(question_text)
        normalized_response_text = self.normalize_text(response_text)
        lowered_response = normalized_response_text.lower().strip()

        if lowered_response in SURVEY_ANALYSIS_EMPTY_MARKERS:
            return {
                "should_analyze": False,
                "skip_reason": "empty_or_ignorable_response",
                "question_kind": "unknown",
                "response_kind": "empty",
                "normalized_question_text": normalized_question_text,
                "normalized_response_text": normalized_response_text,
                "short_opinion": None,
            }

        short_opinion = SURVEY_ANALYSIS_SHORT_OPINIONS.get(lowered_response)
        if short_opinion:
            sentiment, category = short_opinion
            return {
                "should_analyze": True,
                "skip_reason": None,
                "question_kind": "unknown",
                "response_kind": "short_simple_opinion",
                "normalized_question_text": normalized_question_text,
                "normalized_response_text": normalized_response_text,
                "short_opinion": {
                    "sentiment": sentiment,
                    "category": category,
                },
            }

        return {
            "should_analyze": True,
            "skip_reason": None,
            "question_kind": "unknown",
            "response_kind": "standard",
            "normalized_question_text": normalized_question_text,
            "normalized_response_text": normalized_response_text,
            "short_opinion": None,
        }