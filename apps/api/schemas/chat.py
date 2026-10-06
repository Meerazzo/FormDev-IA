"""
Schemas Pydantic pour l'endpoint /v1/chat.

Ces modèles documentent :
- le format de requête attendu par la gateway
- le format de réponse simplifié renvoyé au client
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

# Garde-fous applicatifs, sans conversion caracteres/tokens.
CHAT_MAX_TEXT_CHARS = 100_000
CHAT_MAX_MESSAGES = 256


class ChatRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole = Field(
        ...,
        description="Rôle du message dans la conversation",
        examples=["user"],
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=CHAT_MAX_TEXT_CHARS,
        description="Contenu textuel du message",
        examples=["Dis bonjour en une phrase."],
    )


class ChatRequest(BaseModel):
    model: Optional[str] = Field(
        default=None,
        description="Nom du modèle à utiliser. Si absent, le modèle par défaut servi par vLLM est utilisé.",
        examples=["Qwen/Qwen2.5-7B-Instruct-AWQ"],
    )
    messages: List[ChatMessage] = Field(
        ...,
        min_length=1,
        max_length=CHAT_MAX_MESSAGES,
        description="Historique des messages transmis au modèle",
    )
    max_tokens: int = Field(
        default=256,
        ge=1,
        le=1024,
        description="Nombre maximal de tokens à générer",
        examples=[256],
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Température d'échantillonnage",
        examples=[0.7],
    )
    top_p: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Paramètre nucleus sampling",
        examples=[0.9],
    )
    post_correction: bool = Field(
        default=False,
        description=(
            "Si activé, l'API effectue une seconde inférence pour corriger les fautes, "
            "améliorer la fluidité et la tournure des phrases sans changer le sens."
        ),
        examples=[False],
    )
    system_prompt: Optional[str] = Field(
        default=None,
        max_length=CHAT_MAX_TEXT_CHARS,
        description=(
            "Prompt système optionnel fourni par le client. "
            "S'il est renseigné, il remplace les instructions métier par défaut. Le contrat technique backend reste présent."
        ),
        examples=[
            "Tu es un assistant de reformulation. Reformule le texte en français professionnel, clair et fluide."
        ],
    )
    post_correction_prompt: Optional[str] = Field(
        default=None,
        max_length=CHAT_MAX_TEXT_CHARS,
        description=(
            "Prompt système optionnel pour la phase de post-correction. "
            "Avec post_correction=true, il remplace les instructions métier de correction. Le contrat technique backend reste présent."
        ),
        examples=[
            "Tu es un correcteur linguistique. Corrige les fautes et améliore légèrement la fluidité sans changer le sens."
        ],
    )

    @model_validator(mode="after")
    def validate_text_budget(self):
        total = sum(len(message.content) for message in self.messages)
        total += len(self.system_prompt or "")
        total += len(self.post_correction_prompt or "")
        total += len(self.model or "")
        if total > CHAT_MAX_TEXT_CHARS:
            raise ValueError(
                f"Chat text exceeds the {CHAT_MAX_TEXT_CHARS} character safety limit"
            )
        return self


class ChatResponseMessage(BaseModel):
    role: str = Field(
        default="assistant",
        description="Rôle du message retourné",
    )
    content: str = Field(
        ...,
        description="Texte généré par le modèle",
    )


class ChatUsage(BaseModel):
    prompt_tokens: Optional[int] = Field(default=None, description="Nombre de tokens d'entrée")
    completion_tokens: Optional[int] = Field(default=None, description="Nombre de tokens générés")
    total_tokens: Optional[int] = Field(default=None, description="Nombre total de tokens")


class ChatResponse(BaseModel):
    model: Optional[str] = Field(
        default=None,
        description="Nom du modèle utilisé pour la génération",
    )
    content: str = Field(
        ...,
        description="Texte généré par le modèle",
    )
    finish_reason: Optional[str] = Field(
        default=None,
        description="Raison d'arrêt de la génération",
    )
    usage: Optional[ChatUsage] = Field(
        default=None,
        description="Statistiques de consommation des tokens",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Temps de réponse mesuré côté API, en millisecondes",
    )