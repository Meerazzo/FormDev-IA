"""
Schemas Pydantic utilisés par l'API d'enrichissement de contenu.

Ces modèles définissent :
- la structure des requêtes envoyées par les clients
- la validation des entrées
- le format des réponses retournées par l'API
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class LengthOption(str, Enum):
    short = "short"
    medium = "medium"
    long = "long"


class StyleOption(str, Enum):
    pedagogic = "pedagogic"
    descriptive = "descriptive"
    neutral = "neutral"


class ContentContext(BaseModel):
    """
    Contexte pédagogique facultatif utilisé pour guider la génération.

    Permet d'adapter le texte produit selon :
    - la formation
    - le niveau
    - la durée
    - le public cible
    """
    training_name: Optional[str] = Field(
        default=None,
        description="Nom de la formation dans FormDev",
        examples=["Word - Initiation"],
    )
    level: Optional[str] = Field(
        default=None,
        description="Niveau visé par la formation",
        examples=["débutant", "intermédiaire", "avancé"],
    )
    duration: Optional[str] = Field(
        default=None,
        description="Durée prévue de la formation",
        examples=["2 heures", "1 jour"],
    )
    audience: Optional[str] = Field(
        default=None,
        description="Public cible de la formation",
        examples=["assistants administratifs", "utilisateurs bureautiques"],
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Contexte complémentaire libre à transmettre au modèle",
    )

class ContentOptions(BaseModel):
    """
    Options de génération permettant d'ajuster le style du texte.

    length : longueur souhaitée
    style : ton rédactionnel
    language : langue de sortie
    """
    length: LengthOption = Field(
        default=LengthOption.medium,
        description="Longueur souhaitée du texte généré",
        examples=["medium"],
    )
    style: StyleOption = Field(
        default=StyleOption.pedagogic,
        description="Style rédactionnel attendu",
        examples=["pedagogic"],
    )
    language: str = Field(
        default="fr",
        description="Langue de sortie, par exemple fr ou en",
        examples=["fr"],
    )

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
    enriched_text: str = Field(
        ...,
        description="Paragraphe pédagogique généré à partir de l’intitulé fourni",
    )
    model: Optional[str] = Field(
        default=None,
        description="Nom du modèle utilisé pour la génération",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Temps de génération mesuré côté API, en millisecondes",
    )