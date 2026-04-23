from typing import Any, Dict, List, Literal, Optional, Union, Annotated

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ============================================================
# Blocs communs
# ============================================================

class ClientMetadata(StrictModel):
    model_config = ConfigDict(extra="allow")


class ClientCategory(StrictModel):
    id: int = Field(..., description="Identifiant de la catégorie.", examples=[10])
    label: str = Field(..., description="Libellé de la catégorie.", examples=["Satisfaction"])
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la catégorie.",
    )


class ClientAvailableAnswer(StrictModel):
    id: int = Field(..., description="Identifiant de la réponse proposée.", examples=[1001])
    label: str = Field(..., description="Libellé de la réponse proposée.", examples=["Bon"])
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la réponse proposée.",
    )


class ClientSegment(StrictModel):
    text: str = Field(
        ...,
        description="Texte du segment produit par l'analyse.",
        examples=["Plus de choix de produits"],
    )
    sentiment: Literal[
        "VERY_NEGATIVE",
        "NEGATIVE",
        "NEUTRAL",
        "POSITIVE",
        "VERY_POSITIVE",
    ] = Field(
        ...,
        description="Sentiment métier du segment.",
        examples=["NEGATIVE"],
    )
    categoryId: int = Field(
        ...,
        description="Identifiant de la catégorie associée au segment.",
        examples=[11],
    )


# ============================================================
# Entrée client
# ============================================================

class ClientOpenAnswerInput(StrictModel):
    id: int = Field(..., description="Identifiant de la réponse.", examples=[2000])
    type: Literal["FREE_TEXT"] = Field(..., description="Type de réponse.", examples=["FREE_TEXT"])
    label: str = Field(..., description="Texte libre saisi par le répondant.", examples=["Plus de choix de produits et un service client plus réactif serait apprécié."])
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la réponse.",
    )


class ClientChoiceAnswerInput(StrictModel):
    id: int = Field(..., description="Identifiant de la réponse.", examples=[2001])
    type: Literal["CHOICE"] = Field(..., description="Type de réponse.", examples=["CHOICE"])
    idAvailableAnswer: int = Field(
        ...,
        description="Identifiant de la réponse sélectionnée parmi les réponses possibles.",
        examples=[1001],
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la réponse.",
    )


class ClientOpenQuestionInput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    label: str = Field(..., description="Libellé de la question.")
    type: Literal["OPEN"] = Field(..., description="Type de question.")
    answers: List[ClientOpenAnswerInput] = Field(
        default_factory=list,
        description="Réponses ouvertes associées à la question.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


class ClientSingleChoiceQuestionInput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    label: str = Field(..., description="Libellé de la question.")
    type: Literal["SINGLE_CHOICE"] = Field(..., description="Type de question.")
    availableAnswers: List[ClientAvailableAnswer] = Field(
        default_factory=list,
        description="Liste des réponses proposées.",
    )
    answer: Optional[ClientChoiceAnswerInput] = Field(
        default=None,
        description="Réponse sélectionnée.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


class ClientMultipleChoiceQuestionInput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    label: str = Field(..., description="Libellé de la question.")
    type: Literal["MULTIPLE_CHOICE"] = Field(..., description="Type de question.")
    availableAnswers: List[ClientAvailableAnswer] = Field(
        default_factory=list,
        description="Liste des réponses proposées.",
    )
    answers: List[ClientChoiceAnswerInput] = Field(
        default_factory=list,
        description="Réponses sélectionnées.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


class ClientRatingQuestionInput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    label: str = Field(..., description="Libellé de la question.")
    type: Literal["RATING"] = Field(..., description="Type de question.")
    maxValue: int = Field(..., description="Valeur maximale de la note.")
    value: Optional[int] = Field(
        default=None,
        description="Valeur sélectionnée.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


class ClientCheckboxQuestionInput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    label: str = Field(..., description="Libellé de la question.")
    type: Literal["CHECKBOX"] = Field(..., description="Type de question.")
    checked: Optional[bool] = Field(
        default=None,
        description="Valeur cochée ou non.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


ClientQuestionInput = Annotated[
    Union[
        ClientOpenQuestionInput,
        ClientSingleChoiceQuestionInput,
        ClientMultipleChoiceQuestionInput,
        ClientRatingQuestionInput,
        ClientCheckboxQuestionInput,
    ],
    Field(discriminator="type"),
]


class ClientQuestionnaireInput(StrictModel):
    id: int = Field(..., description="Identifiant du questionnaire.")
    availableCategories: List[ClientCategory] = Field(
        default_factory=list,
        description="Liste globale des catégories disponibles pour le questionnaire.",
    )
    questions: List[ClientQuestionInput] = Field(
        default_factory=list,
        description="Liste des questions du questionnaire.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées au questionnaire.",
    )


class ClientQuestionnaireAnalyzeRequest(StrictModel):
    questionnaires: List[ClientQuestionnaireInput] = Field(
        default_factory=list,
        description="Liste des questionnaires à analyser.",
        examples=[[
            {
                "id": 1,
                "availableCategories": [
                    {"id": 10, "label": "Satisfaction", "metadata": {}},
                    {"id": 11, "label": "Amélioration", "metadata": {}}
                ],
                "questions": [],
                "metadata": {"formation": "Questionnaire exemple"}
            }
        ]],
    )

# ============================================================
# Sortie client
# ============================================================

class ClientAnswerOutput(StrictModel):
    id: int = Field(..., description="Identifiant de la réponse.")
    segments: List[ClientSegment] = Field(
        default_factory=list,
        description="Segments d'analyse associés à cette réponse.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la réponse.",
    )


class ClientOpenQuestionOutput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    answers: List[ClientAnswerOutput] = Field(
        default_factory=list,
        description="Réponses ouvertes enrichies avec leurs segments.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


class ClientSingleChoiceQuestionOutput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    answer: Optional[ClientAnswerOutput] = Field(
        default=None,
        description="Réponse unique enrichie avec ses segments.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


class ClientMultipleChoiceQuestionOutput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    answers: List[ClientAnswerOutput] = Field(
        default_factory=list,
        description="Réponses multiples enrichies avec leurs segments.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


class ClientQuestionWithSegmentsOutput(StrictModel):
    id: int = Field(..., description="Identifiant de la question.")
    segments: List[ClientSegment] = Field(
        default_factory=list,
        description="Segments produits directement au niveau de la question.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées à la question.",
    )


ClientQuestionOutput = Union[
    ClientOpenQuestionOutput,
    ClientSingleChoiceQuestionOutput,
    ClientMultipleChoiceQuestionOutput,
    ClientQuestionWithSegmentsOutput,
]


class ClientQuestionnaireOutput(StrictModel):
    id: int = Field(..., description="Identifiant du questionnaire.")
    availableCategories: List[ClientCategory] = Field(
        default_factory=list,
        description="Liste globale des catégories disponibles pour le questionnaire.",
    )
    questions: List[ClientQuestionOutput] = Field(
        default_factory=list,
        description="Questions enrichies avec les résultats d'analyse.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées associées au questionnaire.",
    )


class ClientQuestionnaireAnalyzeResponse(StrictModel):
    questionnaires: List[ClientQuestionnaireOutput] = Field(
        default_factory=list,
        description="Liste des questionnaires enrichis.",
    )