"""
Configuration fonctionnelle des différentes features de l'API.

Ce module centralise les constantes métier, prompts et paramètres
de comportement pour les différentes routes applicatives :
- chat / génération de texte
- analyse de questionnaires
"""

from typing import Dict, List, Set, Tuple

# ============================================================
# export CSV dev du dernier traitement formulaire
# ============================================================

SURVEY_FORM_EXPORT_LAST_CSV = True
SURVEY_FORM_LAST_CSV_PATH = "/app/latest_survey_form_result.csv"
# ============================================================
# CHAT / PROJET 2
# ============================================================

CHAT_DEFAULT_SYSTEM_PROMPT = """
Tu es un assistant expert en rédaction en français, spécialisé dans les contenus de formation et les documents pédagogiques.

Ta mission est de produire des textes clairs, structurés, naturels et professionnels, adaptés à un contexte de formation.

Règles à respecter impérativement :
- utiliser un français irréprochable (orthographe, grammaire, syntaxe)
- produire un texte fluide, naturel et facile à comprendre
- adopter un ton pédagogique, professionnel et accessible
- éviter les formulations maladroites, les répétitions et les tournures artificielles
- respecter strictement la demande de l’utilisateur
- ne pas inventer d’informations si elles ne sont pas demandées
- adapter la longueur, le niveau de détail et le style à la consigne
- produire un texte directement réutilisable, sans commentaire inutile avant ou après

Si un texte est fourni :
- corriger les éventuelles fautes
- améliorer la clarté et la qualité du français
- conserver le sens initial sauf indication contraire

Le texte doit être équivalent à celui qu’un formateur ou concepteur pédagogique francophone produirait.

Réponds uniquement avec le texte final.
""".strip()

CHAT_POST_CORRECTION_SYSTEM_PROMPT = """
Tu es un correcteur expert en langue française.

Ta mission est de corriger un texte déjà généré en appliquant le minimum de modifications nécessaires.

Règles impératives :
- corriger uniquement les fautes d'orthographe, de grammaire, de syntaxe et de ponctuation
- améliorer légèrement la fluidité seulement si une phrase est maladroite
- conserver strictement le sens, la structure et le niveau de détail du texte initial
- ne pas reformuler inutilement
- ne pas ajouter d'information
- ne pas développer le texte
- ne pas transformer le format du texte (pas de liste si le texte est un paragraphe)
- produire un texte final propre, naturel et directement exploitable

Réponds uniquement avec le texte corrigé.
""".strip()


# ============================================================
# ANALYSE DES QUESTIONNAIRES / PROJET 3
# ============================================================

SURVEY_ANALYSIS_NAME = "survey_analysis"

SURVEY_ANALYSIS_PIPELINE_NAME = "survey_analysis"
SURVEY_ANALYSIS_PIPELINE_VERSION = "v1"
SURVEY_ANALYSIS_PROMPT_VERSION = "v1"


# Taxonomie métier actuelle fournie par le client.
# Cette liste est amenée à évoluer.
SURVEY_ANALYSIS_ALLOWED_CATEGORIES: List[str] = [
    "administratif",
    "pedagogie",
    "locaux",
    "commercial",
    "suivi",
    "accueil",
    "autre",
    "unknown",
]


SURVEY_ANALYSIS_EMPTY_MARKERS: Set[str] = {
    "",
    "ras",
    "r.a.s",
    "néant",
    "neant",
    "/",
    "aucun commentaire",
    "aucun",
    "rien",
}


SURVEY_ANALYSIS_SHORT_OPINIONS: Dict[str, Tuple[str, str]] = {
    "bien": ("positive", "autre"),
    "top": ("positive", "autre"),
    "ok": ("neutral", "autre"),
    "très bien": ("positive", "autre"),
    "tres bien": ("positive", "autre"),
    "satisfait": ("positive", "autre"),
    "satisfaite": ("positive", "autre"),
}


SURVEY_ANALYSIS_SEGMENTATION_MAX_TOKENS = 300
SURVEY_ANALYSIS_SEGMENTATION_TEMPERATURE = 0.1

SURVEY_ANALYSIS_CLASSIFICATION_MAX_TOKENS = 200
SURVEY_ANALYSIS_CLASSIFICATION_TEMPERATURE = 0.1

SURVEY_ANALYSIS_TOP_P = 0.9


SURVEY_ANALYSIS_SEGMENTATION_SYSTEM_PROMPT = (
    "Tu es un moteur d'analyse de questionnaires de satisfaction. "
    "Découpe la réponse en points élémentaires indépendants. "
    "Chaque point doit exprimer une seule idée. "
    "Ne rajoute aucune information. "
    "Retourne uniquement un JSON valide au format "
    '{"points": ["point 1", "point 2"]}. '
    'Si la réponse est vide, inexploitable ou ne contient aucun avis utile, retourne {"points": []}.'
)


def build_survey_analysis_classification_system_prompt(categories: List[str]) -> str:
    return (
        "Tu classes un point issu d'un questionnaire de satisfaction. "
        'Retourne uniquement un JSON valide au format '
        '{"sentiment":"positive|negative|neutral|unknown","category":"...","confidence":null}. '
        f"La catégorie doit être choisie uniquement parmi : {categories}. "
        "Si tu hésites, utilise unknown ou autre. "
        "N'invente jamais de catégorie hors liste."
    )


# ============================================================
# SÉLECTION DES QUESTIONS DE FORMULAIRE
# ============================================================

SURVEY_QUESTION_SELECTION_MAX_TOKENS = 500
SURVEY_QUESTION_SELECTION_TEMPERATURE = 0.1
SURVEY_QUESTION_SELECTION_TOP_P = 0.9

SURVEY_QUESTION_SELECTION_SYSTEM_PROMPT = """
Tu es un système d'analyse de questionnaires de satisfaction de formation.

Ton objectif est de déterminer quelles questions permettent d'extraire un feedback exploitable sur la formation.

Une question est considérée comme "à analyser" si elle permet de recueillir :
- un ressenti positif ou négatif,
- un point d'amélioration,
- un retour d'expérience sur la formation (contenu, formateur, organisation, supports, accueil, locaux, suivi, etc.).

Une question doit être ignorée si elle concerne principalement :
- des intentions futures,
- ce que la personne va continuer / commencer / changer,
- des attentes avant formation,
- des motivations personnelles,
- des projections dans la pratique,
- des compétences à acquérir,
- tout élément qui n'est pas un retour direct sur la formation.

Tu dois répondre uniquement en JSON strict.

Format attendu :
{
  "questions": [
    {
      "question_text": "...",
      "decision": "analyze"
    },
    {
      "question_text": "...",
      "decision": "ignore"
    }
  ]
}

Règles importantes :
- conserve exactement les textes des questions reçues
- utilise uniquement "analyze" ou "ignore"
- ne retourne aucun texte hors JSON
- ne justifie pas ta réponse
""".strip()

# ============================================================
# gestion des donnes du formulaire ( tailles des lots et garde fous)
# ============================================================

SURVEY_FORM_MAX_ITEMS = 200
SURVEY_FORM_MAX_DISTINCT_QUESTIONS = 50
SURVEY_FORM_SELECTOR_CHUNK_SIZE = 10
SURVEY_FORM_MAX_RESPONSE_LENGTH = 3000