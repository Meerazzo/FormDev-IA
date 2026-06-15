class RagPromptBuilder:
    """
    Construit le prompt RAG envoyé au modèle.

    Objectif :
    - limiter les hallucinations
    - forcer l'utilisation des extraits fournis
    - produire une réponse claire
    - citer les sources sans inventer de page
    - utiliser l'historique uniquement pour comprendre la question
    """

    def build_messages(
        self,
        *,
        question: str,
        context_chunks: list[dict],
        retrieval_confidence: str,
        conversation_history: list[dict] | None = None,
    ) -> list[dict]:
        context = self._format_context(context_chunks)
        history = self._format_history(conversation_history or [])

        system_prompt = (
            "Tu es un assistant documentaire pour FormDev.\n"
            "\n"
            "Règles obligatoires :\n"
            "1. Tu dois répondre uniquement à partir des extraits documentaires fournis.\n"
            "2. Tu ne dois pas inventer d'information.\n"
            "3. Tu ne dois pas utiliser de connaissances externes.\n"
            "4. Si les extraits ne permettent pas de répondre, dis clairement que l'information n'est pas présente dans les documents fournis.\n"
            "5. Si la réponse est partielle, indique que la réponse est partielle.\n"
            "6. Réponds en français, avec un style clair et professionnel.\n"
            "7. Cite uniquement les sources réellement fournies dans le contexte.\n"
            "8. N'invente jamais de numéro de page.\n"
            "9. Si aucune page n'est indiquée dans une source, ne mentionne pas de page pour cette source.\n"
            "10. L'historique de conversation sert uniquement à comprendre la demande de l'utilisateur.\n"
            "11. Les faits de la réponse doivent toujours provenir des extraits documentaires fournis.\n12. Ne cite jamais deux fois la même source avec le même chunk dans la section Sources utilisées.\n"
            "\n"
            "Format attendu :\n"
            "Réponse :\n"
            "<réponse courte et précise>\n"
            "\n"
            "Sources utilisées :\n"
            "- <nom du document>, chunk <numéro>\n"
            "- <nom du document>, page <page>, chunk <numéro> uniquement si une page est explicitement indiquée\n"
        )

        user_prompt = (
            f"Historique récent de la conversation :\n{history}\n\n"
            f"Question utilisateur actuelle :\n{question}\n\n"
            f"Niveau de confiance du retrieval : {retrieval_confidence}\n\n"
            "Extraits documentaires disponibles :\n"
            f"{context}\n\n"
            "Consigne finale :\n"
            "Réponds uniquement avec les informations présentes dans les extraits ci-dessus. "
            "Utilise l'historique seulement pour comprendre les références implicites de la question. "
            "Pour les sources, recopie uniquement les informations explicitement indiquées dans les libellés de source."
        )

        return [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]

    def _format_context(self, context_chunks: list[dict]) -> str:
        if not context_chunks:
            return "Aucun extrait documentaire disponible."

        formatted_chunks: list[str] = []

        for index, chunk in enumerate(context_chunks, start=1):
            source_name = chunk.get("source_name") or "Source inconnue"
            page = chunk.get("page")
            chunk_index = chunk.get("chunk_index")
            score = chunk.get("score")
            text = chunk.get("text") or ""

            source_label = f"[Source {index}] document={source_name}"

            if chunk_index is not None:
                source_label += f", chunk={chunk_index}"

            if page is not None:
                source_label += f", page={page}"

            if score is not None:
                source_label += f", score={score:.3f}"

            formatted_chunks.append(
                f"{source_label}\n{text.strip()}"
            )

        return "\n\n---\n\n".join(formatted_chunks)

    def _format_history(self, conversation_history: list[dict]) -> str:
        if not conversation_history:
            return "Aucun historique disponible."

        formatted_messages: list[str] = []

        for message in conversation_history:
            role = message.get("role") or "unknown"
            content = (message.get("content") or "").strip()

            if not content:
                continue

            if len(content) > 700:
                content = content[:697].rstrip() + "..."

            if role == "user":
                label = "Utilisateur"
            elif role == "assistant":
                label = "Assistant"
            else:
                label = role

            formatted_messages.append(f"{label} : {content}")

        return "\n".join(formatted_messages) if formatted_messages else "Aucun historique disponible."
