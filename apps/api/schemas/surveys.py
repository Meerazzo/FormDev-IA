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


class SurveyFormItem(BaseModel):
    question_id: str = Field(..., description="Identifiant de la question dans le formulaire.")
    question_text: str = Field(..., description="Texte de la question.")
    response_text: Optional[str] = Field(None, description="Réponse associée à la question.")


class SurveyFormPreviewRequest(BaseModel):
    form_id: Optional[str] = Field(None, description="Identifiant du formulaire.")
    items: List[SurveyFormItem] = Field(..., description="Liste des questions/réponses du formulaire.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Métadonnées du formulaire.")


class SurveyQuestionSelection(BaseModel):
    question_text: str = Field(..., description="Texte exact de la question.")
    decision: str = Field(..., description='Décision proposée : "analyze" ou "ignore".')


class SurveyFormPreviewResponse(BaseModel):
    questions: List[SurveyQuestionSelection] = Field(
        default_factory=list,
        description="Liste des questions distinctes du formulaire avec décision proposée.",
    )


class SurveyFormAnalyzeItem(BaseModel):
    question_id: str = Field(..., description="Identifiant de la question dans le formulaire.")
    question_text: str = Field(..., description="Texte de la question.")
    response_text: Optional[str] = Field(None, description="Réponse associée à la question.")


class SurveyFormAnalyzeRequest(BaseModel):
    survey_id: str = Field(..., description="Identifiant du formulaire ou de la session.")
    items: List[SurveyFormAnalyzeItem] = Field(
        ...,
        description="Liste des couples question/réponse du formulaire.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Métadonnées communes au formulaire : client, formation, date, etc.",
    )


class SurveyFormResponseItem(BaseModel):
    response_id: str = Field(..., description="Identifiant technique unique de la réponse.")
    question_id: str = Field(..., description="Identifiant de la question.")
    question_text: str = Field(..., description="Texte de la question.")
    selection_decision: str = Field(..., description='Décision prise pour la question : "analyze" ou "ignore".')
    points: List[SurveyPoint] = Field(default_factory=list, description="Points extraits pour la réponse.")


class SurveyFormAnalyzeResponse(BaseModel):
    survey_id: str = Field(..., description="Identifiant du formulaire traité.")
    question_decisions: List[SurveyQuestionSelection] = Field(
        default_factory=list,
        description="Décisions prises sur les questions distinctes du formulaire.",
    )
    responses: List[SurveyFormResponseItem] = Field(
        default_factory=list,
        description="Résultats réponse par réponse après application de la sélection.",
    )