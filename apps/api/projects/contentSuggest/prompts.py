from __future__ import annotations
from typing import Optional

from schemas.content import ContentContext, ContentOptions

LENGTH_GUIDE = {
    "short": "5 à 7 lignes maximum.",
    "medium": "8 à 12 lignes environ.",
    "long": "12 à 18 lignes environ.",
}

STYLE_GUIDE = {
    "pedagogic": "Ton pédagogique, clair, orienté objectifs.",
    "descriptive": "Ton descriptif, factuel, orienté contenu.",
    "neutral": "Ton neutre, concis, sans marketing.",
}


def build_system_prompt(context: Optional[ContentContext], options: Optional[ContentOptions]) -> str:
    lang = (options.language if options else "fr") or "fr"
    length = (options.length if options else "medium") or "medium"
    style = (options.style if options else "pedagogic") or "pedagogic"

    ctx_lines = []
    if context:
        if context.training_name:
            ctx_lines.append(f"- Formation: {context.training_name}")
        if context.level:
            ctx_lines.append(f"- Niveau: {context.level}")
        if context.duration:
            ctx_lines.append(f"- Durée: {context.duration}")
        if context.audience:
            ctx_lines.append(f"- Public: {context.audience}")
        if context.extra:
            ctx_lines.append(f"- Contexte additionnel: {context.extra}")

    ctx_block = "\n".join(ctx_lines) if ctx_lines else "- (aucun contexte fourni)"

    # Prompt volontairement strict : structure + pas de balises + pas de listes à rallonge
    return f"""
Tu es un assistant spécialisé en ingénierie pédagogique. Ta mission: transformer un intitulé de programme en un paragraphe clair, directement réutilisable dans un logiciel de formation.

Contraintes:
- Langue: {lang}
- {STYLE_GUIDE.get(style, STYLE_GUIDE["pedagogic"])}
- Longueur: {LENGTH_GUIDE.get(length, LENGTH_GUIDE["medium"])}
- Réponds en TEXTE PLAIN (pas de markdown, pas de titres en majuscules, pas de puces longues).
- Structure attendue dans un seul paragraphe fluide:
  1) Objectif pédagogique (ce que l'apprenant saura faire)
  2) Notions/compétences travaillées
  3) Bénéfices concrets / mise en pratique

Contexte à respecter:
{ctx_block}

Interdictions:
- Ne fais pas de promesses exagérées.
- N'invente pas des prérequis ou outils non mentionnés par le contexte.
- Ne parle pas de "prompt", "modèle", "IA", "LLM".
""".strip()