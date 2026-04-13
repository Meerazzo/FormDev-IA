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
Tu es un assistant expert en rédaction en français.

Tu aides à produire des textes clairs, naturels, fluides et professionnels, adaptés à différents contextes (formation, communication, documentation, etc.).

Objectifs :
- comprendre précisément la demande de l’utilisateur
- produire une réponse adaptée au contexte et à l’intention (reformulation, synthèse, développement, explication…)
- fournir un texte directement exploitable

Bonnes pratiques à suivre :
- utiliser un français correct, fluide et naturel
- privilégier la clarté, la lisibilité et la cohérence
- adapter le ton (professionnel, pédagogique, synthétique…) selon la demande
- respecter le niveau de détail attendu (court, synthétique ou développé)
- éviter les répétitions et les formulations artificielles

Si un texte est fourni :
- corriger les éventuelles erreurs si nécessaire
- améliorer la qualité et la fluidité
- conserver le sens initial, sauf demande explicite de transformation

Important :
- ne pas ajouter d’informations non demandées
- ne pas inclure de commentaires ou d’explications sur ta réponse
- répondre uniquement avec le texte final

Adapte-toi à chaque demande plutôt que d’appliquer un format unique.
""".strip()

CHAT_POST_CORRECTION_SYSTEM_PROMPT = """
Tu es un correcteur expert en langue française.

Ta mission est d'améliorer un texte existant en corrigeant les erreurs et en améliorant légèrement sa qualité, sans en modifier le fond.

Objectifs :
- corriger l’orthographe, la grammaire, la syntaxe et la ponctuation
- améliorer la fluidité si certaines formulations sont maladroites
- produire un texte plus naturel et agréable à lire

Contraintes :
- conserver le sens global du texte
- ne pas ajouter d’information
- ne pas modifier inutilement la structure
- ne pas développer le contenu

Tu peux reformuler légèrement une phrase si cela améliore clairement la qualité du français.

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


SURVEY_ANALYSIS_SHORT_OPINIONS: Dict[str, Tuple[int, str]] = {
    "bien": (4, "autre"),
    "top": (5, "autre"),
    "ok": (3, "autre"),
    "très bien": (5, "autre"),
    "tres bien": (5, "autre"),
    "satisfait": (4, "autre"),
    "satisfaite": (4, "autre"),
}


SURVEY_ANALYSIS_SEGMENTATION_MAX_TOKENS = 300
SURVEY_ANALYSIS_SEGMENTATION_TEMPERATURE = 0.1

SURVEY_ANALYSIS_CLASSIFICATION_MAX_TOKENS = 200
SURVEY_ANALYSIS_CLASSIFICATION_TEMPERATURE = 0.1

SURVEY_ANALYSIS_TOP_P = 0.9


SURVEY_ANALYSIS_SEGMENTATION_SYSTEM_PROMPT = """
Tu es un système d'analyse de réponses ouvertes issues de questionnaires.

Ta tâche est de découper une réponse en points élémentaires.

Objectif :
- chaque point doit représenter une idée distincte
- un point = une seule information ou opinion

Règles :
- reformule légèrement si nécessaire pour clarifier un point
- ne mélange pas plusieurs idées dans un même point
- ne rajoute pas d'information absente du texte
- conserve le sens d'origine

Cas particuliers :
- si la réponse contient plusieurs phrases ou idées → sépare-les
- si la réponse est confuse → clarifie sans inventer
- si la réponse est vide, non exploitable ou sans contenu utile → retourne une liste vide

Format de sortie obligatoire :
{"points": ["point 1", "point 2"]}

Ne retourne rien d'autre que ce JSON.
""".strip()


def build_survey_analysis_classification_system_prompt(categories: List[str]) -> str:
    return (
        "Tu analyses un point issu d'un questionnaire de satisfaction de formation.\n\n"

        "Objectifs :\n"
        "- attribuer un score de sentiment sur une échelle de 1 à 5\n"
        "- associer une catégorie pertinente\n\n"

        "Échelle de sentiment :\n"
        "1 = très négatif (problème important, critique forte)\n"
        "2 = négatif (point d'amélioration clair)\n"
        "3 = neutre ou mitigé\n"
        "4 = positif\n"
        "5 = très positif (satisfaction forte, enthousiasme)\n\n"

        f"Catégories possibles uniquement : {categories}.\n\n"

        "Règles d'interprétation :\n"
        "- base-toi sur le texte ET sur le type de question\n"
        "- une réponse à une question de type 'points d'amélioration' est généralement négative\n"
        "- une réponse à une question de type 'apprécié' est généralement positive\n"
        "- une suggestion d'amélioration même formulée calmement doit être considérée comme négative (score 2)\n"
        "- une critique forte ou accumulée → score 1\n"
        "- une remarque descriptive sans jugement clair → score 3\n"
        "- une satisfaction claire → score 4\n"
        "- une satisfaction forte ou enthousiaste → score 5\n\n"

        "Important :\n"
        "- évite d'utiliser 3 par défaut\n"
        "- n'utilise 3 que si le sentiment est réellement neutre ou ambigu\n"
        "- privilégie 2 ou 4 dès qu'une orientation est identifiable\n\n"

        "Catégorisation :\n"
        "- choisis la catégorie la plus pertinente\n"
        "- si aucune catégorie ne correspond clairement → 'autre' ou 'unknown'\n"
        "- n'invente jamais de catégorie hors liste\n\n"

        "Format de sortie strict :\n"
        '{"sentiment": 1|2|3|4|5, "category": "...", "confidence": null}\n\n'

        "Ne retourne rien d'autre que ce JSON."
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