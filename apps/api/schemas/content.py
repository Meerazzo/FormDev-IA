"""
Schemas Pydantic utilisés par l'API d'enrichissement de contenu.

Ces modèles définissent :
- la structure des requêtes envoyées par les clients
- la validation des entrées
- le format des réponses retournées par l'API
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any


LengthOption = Literal["short", "medium", "long"]
StyleOption = Literal["pedagogic", "descriptive", "neutral"]


class ContentContext(BaseModel):
    """
    Contexte pédagogique facultatif utilisé pour guider la génération.

    Permet d'adapter le texte produit selon :
    - la formation
    - le niveau
    - la durée
    - le public cible
    """
    training_name: Optional[str] = Field(default=None, description="Nom de la formation", examples=["Word - Initiation"])
    level: Optional[str] = Field(default=None, description="Niveau (initiation, avancé...)")
    duration: Optional[str] = Field(default=None, description="Durée (ex: 2h, 1 jour)")
    audience: Optional[str] = Field(default=None, description="Public cible")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Contexte libre additionnel")


class ContentOptions(BaseModel):
    """
    Options de génération permettant d'ajuster le style du texte.

    length : longueur souhaitée
    style : ton rédactionnel
    language : langue de sortie
    """
    length: Optional[LengthOption] = Field(default="medium")
    style: Optional[StyleOption] = Field(default="pedagogic")
    language: Optional[str] = Field(default="fr", description="Langue de sortie, ex: fr/en")


class ContentEnrichRequest(BaseModel):
    """
    Requête principale de l'API /content/enrich.

    text : intitulé ou phrase décrivant une notion de formation
    context : informations pédagogiques complémentaires
    options : paramètres de génération
    """
    text: str = Field(..., min_length=2, max_length=500, description="Intitulé/phrase à enrichir", examples=["Travailler les titres dans Word"])
    context: Optional[ContentContext] = None
    options: Optional[ContentOptions] = None


class ContentEnrichResponse(BaseModel):
    enriched_text: str
    model: Optional[str] = None
    latency_ms: Optional[float] = None