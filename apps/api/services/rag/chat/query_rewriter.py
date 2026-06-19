from __future__ import annotations

import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class RagQueryRewriter:
    """
    Reformule une question de suivi en question autonome pour améliorer le retrieval RAG.

    Exemple :
    Historique :
    - User: Quel est le tarif annuel de l'offre Premium FormDev RAG ?
    - Assistant: L'offre Premium FormDev RAG coûte 1290 euros par an.

    Question actuelle :
    - Et qu'est-ce qui est inclus dans cette offre ?

    Question reformulée :
    - Qu'est-ce qui est inclus dans l'offre Premium FormDev RAG ?

    La question reformulée sert uniquement à la recherche vectorielle.
    La question originale reste conservée dans l'historique et dans la réponse API.
    """

    def __init__(self) -> None:
        self.vllm_base_url = settings.VLLM_BASE_URL.rstrip("/")

    def rewrite(
        self,
        *,
        question: str,
        conversation_history: list[dict[str, Any]],
        model_name: str,
    ) -> str:
        question = (question or "").strip()

        if not question or not conversation_history:
            return question

        if not self._looks_like_follow_up(question):
            return question

        messages = self._build_messages(
            question=question,
            conversation_history=conversation_history,
        )

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.vllm_base_url}/v1/chat/completions",
                    json={
                        "model": model_name,
                        "messages": messages,
                        "temperature": 0.0,
                        "max_tokens": 96,
                        "stream": False,
                    },
                )

            response.raise_for_status()
            payload = response.json()

            rewritten = (
                payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )

            rewritten = self._clean_rewritten_query(rewritten)

            if not rewritten:
                return question

            return rewritten

        except Exception as exc:
            logger.warning("RAG query rewriting failed: %s", exc)
            return question

    def _build_messages(
        self,
        *,
        question: str,
        conversation_history: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        formatted_history = self._format_history(conversation_history)

        system_prompt = (
            "Tu es un module de reformulation de requêtes pour un moteur RAG. "
            "Ta tâche est de transformer une question de suivi en question autonome. "
            "Utilise l'historique uniquement pour résoudre les références implicites "
            "comme 'cette offre', 'ce tarif', 'elle', 'ça', etc. "
            "Ne réponds jamais à la question. "
            "Ne donne aucune explication. "
            "Ne cite aucune source. "
            "Retourne uniquement la question reformulée. "
            "Si la question est déjà autonome, retourne-la telle quelle."
        )

        user_prompt = (
            "Historique récent de conversation :\n"
            f"{formatted_history}\n\n"
            "Question actuelle :\n"
            f"{question}\n\n"
            "Question autonome reformulée :"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _format_history(self, conversation_history: list[dict[str, Any]]) -> str:
        if not conversation_history:
            return "Aucun historique."

        recent_messages = conversation_history[-6:]

        lines: list[str] = []

        for message in recent_messages:
            role = message.get("role", "unknown")
            content = str(message.get("content", "")).strip()

            if not content:
                continue

            if role == "user":
                label = "Utilisateur"
            elif role == "assistant":
                label = "Assistant"
            else:
                label = str(role)

            lines.append(f"{label} : {content}")

        return "\n".join(lines) if lines else "Aucun historique."

    def _looks_like_follow_up(self, question: str) -> bool:
        lowered = question.lower().strip()

        follow_up_markers = [
            "cette offre",
            "cet offre",
            "cette formule",
            "ce forfait",
            "ce pack",
            "cette option",
            "ce tarif",
            "ce prix",
            "ce montant",
            "cette fonctionnalité",
            "ces fonctionnalités",
            "ce document",
            "cette source",
            "cette réponse",
            "celle-ci",
            "celui-ci",
            "celui là",
            "celle là",
            "celui-là",
            "celle-là",
            "ça",
            "cela",
            "lui",
            "leur",
            "et qu",
            "et est-ce",
            "et ça",
        ]

        if any(marker in lowered for marker in follow_up_markers):
            return True

        token_count = len(lowered.replace("?", "").split())

        if token_count <= 7 and lowered.startswith(("et ", "mais ", "donc ", "alors ")):
            return True

        return False

    def _clean_rewritten_query(self, rewritten: str) -> str:
        rewritten = rewritten.strip()

        prefixes = [
            "Question autonome reformulée :",
            "Question reformulée :",
            "Requête reformulée :",
            "Réponse :",
        ]

        for prefix in prefixes:
            if rewritten.lower().startswith(prefix.lower()):
                rewritten = rewritten[len(prefix):].strip()

        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1].strip()

        if rewritten.startswith("'") and rewritten.endswith("'"):
            rewritten = rewritten[1:-1].strip()

        rewritten = rewritten.split("\n")[0].strip()

        # Sécurité : si le modèle génère une phrase explicative, on garde la question originale ailleurs.
        if len(rewritten) > 400:
            return ""

        return rewritten
