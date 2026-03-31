from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class SurveyAnalyzeRequest(BaseModel):
    survey_id: str = Field(
        ...,
        description="Identifiant du questionnaire ou de la session de formation.",
        examples=["formation_word_mars_2026"],
    )
    question_id: str = Field(
        ...,
        description="Identifiant de la question dans le questionnaire.",
        examples=["q_appreciation"],
    )
    question_text: str = Field(
        ...,
        description="Texte de la question posée à l'utilisateur.",
        examples=["Ce que vous avez particulièrement apprécié :"],
    )
    response_text: Optional[str] = Field(
        None,
        description="Réponse textuelle libre fournie par le participant.",
        examples=["Petit groupe, tout le monde peut prendre la parole. Changement d'intervenant stimulant."],
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Contexte additionnel : client, formation, date, etc.",
        examples=[{
            "formation": "Word avancé",
            "client": "Entreprise X",
            "formateur": "Dupont",
            "date": "2026-03-30"
        }],
    )

class SurveyPoint(BaseModel):
    point_id: str = Field(
        ...,
        description="Identifiant technique du point extrait.",
        examples=["550e8400-e29b-41d4-a716-446655440000_pt_1"],
    )
    text: str = Field(
        ...,
        description="Texte du point segmenté.",
        examples=["Petit groupe, tout le monde peut prendre la parole."],
    )
    sentiment: Optional[str] = Field(
        None,
        description="Sentiment associé au point.",
        examples=["positive"],
    )
    category: Optional[str] = Field(
        None,
        description="Catégorie métier associée au point.",
        examples=["pedagogie"],
    )
    confidence: Optional[float] = Field(
        None,
        description="Score de confiance éventuel du modèle.",
        examples=[0.92],
    )

class SurveyAnalyzeResponse(BaseModel):
    response_id: str = Field(
        ...,
        description="Identifiant technique unique généré côté backend pour la réponse analysée.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    points: List[SurveyPoint] = Field(default_factory=list)

class SurveyFeedbackPoint(BaseModel):
    point_id: Optional[str] = None
    is_correct: bool = False
    corrected_text: Optional[str] = None
    corrected_sentiment: Optional[str] = None
    corrected_category: Optional[str] = None
    action: Optional[str] = None  # update / delete / add

class SurveyFeedbackRequest(BaseModel):
    response_id: str
    operator_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    points: List[SurveyFeedbackPoint]