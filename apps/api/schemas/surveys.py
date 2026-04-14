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
    sentiment: Optional[int] = Field(
        None,
        description="Sentiment sur 5 : 1 très négatif, 2 négatif, 3 neutre, 4 positif, 5 très positif.",
        examples=[4],
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
    point_id: Optional[str] = Field(
        default=None,
        description="Identifiant du point corrigé. Peut être absent pour un ajout manuel."
    )
    is_correct: bool = Field(
        default=False,
        description="Indique si le point proposé par le modèle est validé tel quel."
    )
    corrected_text: Optional[str] = Field(
        default=None,
        description="Texte corrigé par l'opérateur."
    )
    corrected_sentiment: Optional[int] = Field(
        default=None,
        description="Sentiment corrigé sur 5 : 1 très négatif, 2 négatif, 3 neutre, 4 positif, 5 très positif.",
    )
    corrected_category: Optional[str] = Field(
        default=None,
        description="Catégorie corrigée par l'opérateur."
    )
    action: Optional[str] = Field(
        default=None,
        description='Action opérateur : "update", "delete" ou "add".'
    )

class SurveyFeedbackRequest(BaseModel):
    response_id: str = Field(..., description="Identifiant de la réponse concernée par le feedback.")
    operator_id: Optional[str] = Field(default=None, description="Identifiant de l'opérateur ayant relu la réponse.")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Métadonnées de la session de relecture.")
    points: List[SurveyFeedbackPoint] = Field(..., description="Liste des validations ou corrections opérateur.")

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
    question_id: str = Field(..., description="Identifiant technique de la ligne ou de la question.")
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


class SurveyFormResult(BaseModel):
    survey_id: str = Field(..., description="Identifiant du formulaire traité.")
    question_decisions: List[SurveyQuestionSelection] = Field(
        default_factory=list,
        description="Décisions prises sur les questions distinctes du formulaire.",
    )
    responses: List[SurveyFormResponseItem] = Field(
        default_factory=list,
        description="Résultats réponse par réponse après application de la sélection.",
    )


class SurveyProcessingCreateResponse(BaseModel):
    processing_id: str = Field(
        ...,
        description="Identifiant unique du traitement à suivre côté client.",
        examples=["8df0f6f5-3c73-4e84-9dd4-2c4c6d64c111"],
    )
    status: str = Field(
        ...,
        description="Statut initial du traitement.",
        examples=["PENDING"],
    )


class SurveyProcessingStatusResponse(BaseModel):
    processing_id: str = Field(
        ...,
        description="Identifiant unique du traitement.",
    )
    status: str = Field(
        ...,
        description="Statut courant : PENDING, STARTED, FINISHED ou FAILED.",
        examples=["FINISHED"],
    )
    survey_id: Optional[str] = Field(
        None,
        description="Identifiant du formulaire associé au traitement.",
    )
    error_message: Optional[str] = Field(
        None,
        description="Message d'erreur si le traitement a échoué.",
    )
    result: Optional[SurveyFormResult] = Field(
        None,
        description="Résultat final du traitement si le statut est FINISHED.",
    )

class SurveyFeedbackResponse(BaseModel):
    response_id: str = Field(
        ...,
        description="Identifiant de la réponse concernée par le feedback.",
    )
    saved_feedback_count: int = Field(
        ...,
        description="Nombre de lignes de feedback enregistrées.",
        examples=[3],
    )
    status: str = Field(
        ...,
        description="Statut de l'enregistrement du feedback.",
        examples=["ok"],
    )