from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any


LengthOption = Literal["short", "medium", "long"]
StyleOption = Literal["pedagogic", "descriptive", "neutral"]


class ContentContext(BaseModel):
    training_name: Optional[str] = Field(default=None, description="Nom de la formation")
    level: Optional[str] = Field(default=None, description="Niveau (initiation, avancé...)")
    duration: Optional[str] = Field(default=None, description="Durée (ex: 2h, 1 jour)")
    audience: Optional[str] = Field(default=None, description="Public cible")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Contexte libre additionnel")


class ContentOptions(BaseModel):
    length: Optional[LengthOption] = Field(default="medium")
    style: Optional[StyleOption] = Field(default="pedagogic")
    language: Optional[str] = Field(default="fr", description="Langue de sortie, ex: fr/en")


class ContentEnrichRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=500, description="Intitulé/phrase à enrichir")
    context: Optional[ContentContext] = None
    options: Optional[ContentOptions] = None


class ContentEnrichResponse(BaseModel):
    enriched_text: str
    model: Optional[str] = None
    latency_ms: Optional[float] = None