"""
Export CSV de développement pour le dernier traitement de formulaire.

Le fichier est écrasé à chaque nouveau traitement afin de faciliter
les tests manuels et l'inspection rapide des résultats.
"""

import csv
from pathlib import Path
from typing import Any, Dict

from core.feature_config import (
    SURVEY_FORM_EXPORT_LAST_CSV,
    SURVEY_FORM_LAST_CSV_PATH,
)


def export_latest_form_result_to_csv(result: Dict[str, Any]) -> None:
    if not SURVEY_FORM_EXPORT_LAST_CSV:
        return

    path = Path(SURVEY_FORM_LAST_CSV_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "survey_id",
        "question_id",
        "question_text",
        "selection_decision",
        "response_id",
        "point_id",
        "point_text",
        "sentiment",
        "category",
        "confidence",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        survey_id = result.get("survey_id")
        responses = result.get("responses", [])

        for response in responses:
            base_row = {
                "survey_id": survey_id,
                "question_id": response.get("question_id"),
                "question_text": response.get("question_text"),
                "selection_decision": response.get("selection_decision"),
                "response_id": response.get("response_id"),
            }

            points = response.get("points") or []

            if not points:
                writer.writerow(
                    {
                        **base_row,
                        "point_id": "",
                        "point_text": "",
                        "sentiment": "",
                        "category": "",
                        "confidence": "",
                    }
                )
                continue

            for point in points:
                writer.writerow(
                    {
                        **base_row,
                        "point_id": point.get("point_id", ""),
                        "point_text": point.get("text", ""),
                        "sentiment": point.get("sentiment", ""),
                        "category": point.get("category", ""),
                        "confidence": point.get("confidence", ""),
                    }
                )