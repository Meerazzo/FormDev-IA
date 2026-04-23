from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SurveyPoint(StrictModel):
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


class SurveyFeedbackPoint(StrictModel):
    point_id: Optional[str] = Field(
        default=None,
        description="Identifiant du point concerné. Laisser vide pour ajouter un nouveau point manuel.",
        examples=["83744cf8-878e-4a3d-b0ed-e523aac431ef_pt_1"],
    )
    is_correct: bool = Field(
        default=False,
        description="Indique si le point proposé par le modèle est validé tel quel par l'opérateur.",
        examples=[False],
    )
    corrected_text: Optional[str] = Field(
        default=None,
        description="Texte corrigé ou reformulé par l'opérateur.",
        examples=["Service jugé satisfaisant"],
    )
    corrected_sentiment: Optional[int] = Field(
        default=None,
        description="Sentiment corrigé sur 5 : 1 très négatif, 2 négatif, 3 neutre, 4 positif, 5 très positif.",
        examples=[4],
    )
    corrected_category: Optional[str] = Field(
        default=None,
        description="Catégorie corrigée par l'opérateur.",
        examples=["Satisfaction"],
    )
    action: Optional[Literal["update", "delete", "add"]] = Field(
        default=None,
        description='Action opérateur à appliquer : "update" pour corriger, "delete" pour désactiver, "add" pour ajouter un nouveau point.',
        examples=["update"],
    )


class SurveyFeedbackRequest(StrictModel):
    response_id: str = Field(
        ...,
        description="Identifiant technique de la réponse concernée par le feedback.",
        examples=["83744cf8-878e-4a3d-b0ed-e523aac431ef"],
    )
    operator_id: Optional[str] = Field(
        default=None,
        description="Identifiant de l'opérateur ou du relecteur ayant effectué la correction.",
        examples=["op_test_001"],
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Métadonnées métier associées à la session de relecture.",
        examples=[{"review_source": "manual_test"}],
    )
    points: List[SurveyFeedbackPoint] = Field(
        ...,
        description="Liste des validations, corrections, suppressions ou ajouts de points.",
    )

class SurveyFeedbackResponse(StrictModel):
    response_id: str = Field(
        ...,
        description="Identifiant de la réponse concernée par le feedback.",
        examples=["83744cf8-878e-4a3d-b0ed-e523aac431ef"],
    )
    saved_feedback_count: int = Field(
        ...,
        description="Nombre d'actions de feedback enregistrées.",
        examples=[1],
    )
    status: str = Field(
        ...,
        description="Statut de l'enregistrement du feedback.",
        examples=["ok"],
    )


class SurveyFormItem(StrictModel):
    question_id: str = Field(..., description="Identifiant technique de la question.")
    question_text: str = Field(..., description="Texte de la question.")
    response_text: Optional[str] = Field(
        None,
        description="Réponse associée à la question.",
    )


class SurveyFormAnalyzeRequest(StrictModel):
    survey_id: str = Field(..., description="Identifiant du formulaire ou de la session.")
    items: List[SurveyFormItem] = Field(
        ...,
        description="Liste des couples question/réponse du formulaire.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Métadonnées communes au formulaire : client, formation, date, taxonomy_id, etc.",
    )


class SurveyQuestionSelection(StrictModel):
    question_text: str = Field(..., description="Texte exact de la question.")
    decision: Literal["analyze", "ignore"] = Field(
        ...,
        description='Décision proposée : "analyze" ou "ignore".',
    )


class SurveyFormResponseItem(StrictModel):
    response_id: str = Field(..., description="Identifiant technique unique de la réponse.")
    question_id: str = Field(..., description="Identifiant de la question.")
    question_text: str = Field(..., description="Texte de la question.")
    selection_decision: Literal["analyze", "ignore"] = Field(
        ...,
        description='Décision prise pour la question : "analyze" ou "ignore".',
    )
    points: List[SurveyPoint] = Field(
        default_factory=list,
        description="Points extraits pour la réponse.",
    )


class SurveyFormResult(StrictModel):
    survey_id: str = Field(..., description="Identifiant du formulaire traité.")
    question_decisions: List[SurveyQuestionSelection] = Field(
        default_factory=list,
        description="Décisions prises sur les questions distinctes du formulaire.",
    )
    responses: List[SurveyFormResponseItem] = Field(
        default_factory=list,
        description="Résultats réponse par réponse après application de la sélection.",
    )


class SurveyProcessingCreateResponse(StrictModel):
    processing_id: str = Field(
        ...,
        description="Identifiant unique du traitement asynchrone à utiliser pour suivre l'analyse.",
        examples=["90affa60-99a4-488f-9e4d-2a752de4ca1f"],
    )
    status: str = Field(
        ...,
        description="Statut initial du traitement, généralement PENDING juste après la création.",
        examples=["PENDING"],
    )


class SurveyProcessingStatusResponse(StrictModel):
    processing_id: str = Field(
        ...,
        description="Identifiant unique du traitement.",
        examples=["90affa60-99a4-488f-9e4d-2a752de4ca1f"],
    )
    status: str = Field(
        ...,
        description="Statut courant du traitement : PENDING, STARTED, FINISHED ou FAILED.",
        examples=["FINISHED"],
    )
    survey_id: Optional[str] = Field(
        None,
        description="Identifiant technique associé au traitement.",
        examples=["client_questionnaires"],
    )
    error_message: Optional[str] = Field(
        None,
        description="Message d'erreur si le traitement a échoué.",
        examples=[None],
    )
    result: Optional[Dict[str, Any]] = Field(
        None,
        description="Résultat final de l'analyse lorsque le traitement est terminé.",
    )