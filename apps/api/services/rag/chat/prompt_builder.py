from __future__ import annotations


class RagPromptBuilder:
    """
    Construction du prompt RAG envoyé à vLLM.

    Le prompt force le modèle à répondre uniquement à partir des extraits
    récupérés dans Qdrant.
    """

    DEFAULT_SYSTEM_PROMPT = """
Tu es un assistant de support documentaire pour FormDev.

Règles impératives :
- Réponds uniquement à partir des extraits fournis.
- N'invente pas d'information absente des sources.
- Si les extraits ne permettent pas de répondre, dis clairement que tu ne sais pas.
- Réponds en français.
- Donne une réponse claire, utile et concise.
""".strip()

    @staticmethod
    def build_context(chunks: list[dict]) -> str:
        if not chunks:
            return "Aucun extrait documentaire pertinent n'a été trouvé."

        parts: list[str] = []

        for index, chunk in enumerate(chunks, start=1):
            source_name = chunk.get("source_name") or "source inconnue"
            page = chunk.get("page")
            text = (chunk.get("text") or "").strip()

            page_label = f" - page {page}" if page is not None else ""
            parts.append(
                f"[Source {index} - {source_name}{page_label}]\n{text}"
            )

        return "\n\n".join(parts)

    def build_messages(
        self,
        *,
        question: str,
        chunks: list[dict],
        system_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        context = self.build_context(chunks)
        final_system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT

        user_prompt = f"""
Extraits documentaires disponibles :

{context}

Question utilisateur :
{question}

Réponse :
""".strip()

        return [
            {"role": "system", "content": final_system_prompt},
            {"role": "user", "content": user_prompt},
        ]