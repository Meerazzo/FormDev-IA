"""
Service métier pour l'enrichissement de contenu pédagogique.

Ce module contient la logique principale :
- construction du prompt
- appel au modèle via vLLM
- nettoyage du texte généré
- mesure du temps de réponse
"""

from __future__ import annotations

import re
import time
from typing import Tuple, Optional

from schemas.content import ContentEnrichRequest
from services.vllm_client import VLLMClient
from projects.contentSuggest.prompts import build_system_prompt


def _sanitize_output(text: str) -> str:
    """
    Nettoie la sortie du modèle.

    Supprime notamment :
    - blocs markdown accidentels
    - espaces excessifs
    - lignes vides inutiles
    """
    t = text.strip()
    t = re.sub(r"^```.*?\n", "", t, flags=re.DOTALL)
    t = re.sub(r"\n```$", "", t)
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _max_tokens_for_options(length: str) -> int: # Détermine la limite de tokens selon la longueur souhaitée
    if length == "short":
        return 220
    if length == "long":
        return 500
    return 320


async def enrich_content(req: ContentEnrichRequest, client: VLLMClient) -> Tuple[str, Optional[str], float]:
    """
    Génère un texte pédagogique enrichi.

    Étapes :
    1. Construction du prompt système
    2. Création des messages pour le modèle
    3. Appel du serveur vLLM
    4. Nettoyage de la sortie
    5. Retour du texte généré et du temps de réponse
    """
    options = req.options
    length = (options.length if options else "medium") or "medium"
    max_tokens = _max_tokens_for_options(length)

    system_prompt = build_system_prompt(req.context, req.options)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.text.strip()},
    ]

    t0 = time.perf_counter() # Mesure du temps de génération du modèle
    resp = await client.chat(
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.4,
        top_p=0.9,
        timeout_s=120,
    )
    dt_ms = (time.perf_counter() - t0) * 1000.0

    enriched = _sanitize_output(resp.text or "") # Sécurité : on refuse une réponse vide du modèle
    if not enriched:
        raise RuntimeError("Empty model output") 

    return enriched, resp.model, dt_ms