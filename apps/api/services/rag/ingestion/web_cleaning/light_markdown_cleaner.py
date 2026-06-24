from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class LightCleanedMarkdown:
    text: str
    metadata: dict


class LightMarkdownCleaner:
    """
    Nettoyage conservateur pour contenu web destiné au RAG.

    Principe :
    - ne pas décider à la place du retrieval ce qui est utile ;
    - ne pas supprimer les URLs restantes ;
    - ne pas supprimer les listes, tableaux, prix, titres ou FAQ ;
    - nettoyer seulement le format et les répétitions évidentes.
    """

    def clean(self, markdown: str) -> LightCleanedMarkdown:
        raw_text = markdown or ""

        text = self._normalize_text(raw_text)
        text = self._remove_markdown_images(text)
        text = self._deduplicate_exact_blocks(text)
        text = self._remove_obvious_cookie_blocks(text)
        text = self._final_cleanup(text)

        return LightCleanedMarkdown(
            text=text,
            metadata={
                "cleaner": "light_markdown_cleaner",
                "raw_char_length": len(raw_text),
                "cleaned_char_length": len(text),
                "char_reduction_ratio": self._reduction_ratio(len(raw_text), len(text)),
                "urls_preserved": True,
                "aggressive_filtering": False,
            },
        )

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        text = text.replace("\xa0", " ")
        text = text.replace("\x00", " ")

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)

        return text.strip()

    def _remove_markdown_images(self, text: str) -> str:
        # On supprime uniquement les images Markdown, pas les liens texte ni les URLs.
        return re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)

    def _deduplicate_exact_blocks(self, text: str) -> str:
        blocks = re.split(r"\n\s*\n", text)
        seen: set[str] = set()
        kept: list[str] = []

        for block in blocks:
            cleaned_block = block.strip()

            if not cleaned_block:
                continue

            key = self._block_key(cleaned_block)

            if key in seen:
                continue

            seen.add(key)
            kept.append(cleaned_block)

        return "\n\n".join(kept)

    def _remove_obvious_cookie_blocks(self, text: str) -> str:
        blocks = re.split(r"\n\s*\n", text)
        kept: list[str] = []

        for block in blocks:
            lower = block.lower()

            cookie_score = sum(
                marker in lower
                for marker in [
                    "ce site utilise des cookies",
                    "nous utilisons des cookies",
                    "accepter les cookies",
                    "refuser les cookies",
                    "personnaliser les cookies",
                    "gérer les cookies",
                ]
            )

            if cookie_score >= 1 and len(block) < 1200:
                continue

            kept.append(block.strip())

        return "\n\n".join(block for block in kept if block)

    def _final_cleanup(self, text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()

    def _block_key(self, block: str) -> str:
        key = block.lower()
        key = re.sub(r"\s+", " ", key)
        return key.strip()

    def _reduction_ratio(self, before: int, after: int) -> float:
        if before <= 0:
            return 0.0

        return round(1 - (after / before), 4)
