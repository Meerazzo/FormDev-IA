"""
Sélection des questions pertinentes d'un formulaire de satisfaction.

Ce service extrait les questions distinctes d'un formulaire puis demande au LLM
quelles questions doivent être analysées pour la suite du pipeline.
"""

import json
from typing import Dict, List

from core.feature_config import (
    SURVEY_QUESTION_SELECTION_MAX_TOKENS,
    SURVEY_QUESTION_SELECTION_SYSTEM_PROMPT,
    SURVEY_QUESTION_SELECTION_TEMPERATURE,
    SURVEY_QUESTION_SELECTION_TOP_P,
    SURVEY_FORM_SELECTOR_CHUNK_SIZE,
)


class SurveyQuestionSelectorService:
    def __init__(self, vllm_client):
        self.vllm_client = vllm_client

    @staticmethod
    def _chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
        if chunk_size <= 0:
            return [items]
        return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    @staticmethod
    def extract_distinct_questions(items: List[Dict]) -> List[str]:
        seen = set()
        distinct_questions = []

        for item in items:
            question_text = " ".join((item.get("question_text") or "").strip().split())
            if not question_text:
                continue

            normalized = question_text.lower()
            if normalized in seen:
                continue

            seen.add(normalized)
            distinct_questions.append(question_text)

        return distinct_questions

    async def select_questions_in_chunks(self, questions: List[str]) -> Dict:
        if not questions:
            return {"questions": []}

        chunks = self._chunk_list(questions, SURVEY_FORM_SELECTOR_CHUNK_SIZE)

        merged_questions: List[Dict] = []
        seen = set()

        for chunk in chunks:
            result = await self.select_questions(chunk)
            for item in result.get("questions", []):
                question_text = " ".join((item.get("question_text") or "").strip().split())
                decision = (item.get("decision") or "").strip().lower()

                if not question_text or decision not in {"analyze", "ignore"}:
                    continue

                normalized = question_text.lower()
                if normalized in seen:
                    continue

                seen.add(normalized)
                merged_questions.append(
                    {
                        "question_text": question_text,
                        "decision": decision,
                    }
                )

        return {"questions": merged_questions}

    async def select_questions(self, questions: List[str]) -> Dict:
        messages = [
            {
                "role": "system",
                "content": SURVEY_QUESTION_SELECTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(questions, ensure_ascii=False),
            },
        ]

        result = await self.vllm_client.generate_json(
            messages=messages,
            max_tokens=SURVEY_QUESTION_SELECTION_MAX_TOKENS,
            temperature=SURVEY_QUESTION_SELECTION_TEMPERATURE,
            top_p=SURVEY_QUESTION_SELECTION_TOP_P,
        )

        raw_questions = result.get("questions", [])
        if not isinstance(raw_questions, list):
            return {"questions": []}

        cleaned = []
        allowed_decisions = {"analyze", "ignore"}

        for item in raw_questions:
            if not isinstance(item, dict):
                continue

            question_text = " ".join((item.get("question_text") or "").strip().split())
            decision = (item.get("decision") or "").strip().lower()

            if not question_text or decision not in allowed_decisions:
                continue

            cleaned.append(
                {
                    "question_text": question_text,
                    "decision": decision,
                }
            )

        return {"questions": cleaned}