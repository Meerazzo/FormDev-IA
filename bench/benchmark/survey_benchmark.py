import json
import os
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
API_KEY = os.getenv("API_KEY", "")
CONCURRENCY = int(os.getenv("CONCURRENCY", "5"))
TOTAL = int(os.getenv("TOTAL", "5"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2"))
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "900"))

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}

PAYLOAD = {
    "questionnaires": [
        {
            "id": 1,
            "availableCategories": [
                {"id": 10, "label": "Satisfaction", "metadata": {}},
                {"id": 11, "label": "Amélioration", "metadata": {}},
            ],
            "questions": [
                {
                    "id": 100,
                    "label": "Avez-vous des suggestions ?",
                    "type": "OPEN",
                    "answers": [
                        {
                            "id": 2000,
                            "type": "FREE_TEXT",
                            "label": "Plus de choix de produits et un service client plus réactif serait apprécié.",
                            "metadata": {},
                        }
                    ],
                    "metadata": {},
                },
                {
                    "id": 101,
                    "label": "Comment évaluez-vous notre service ?",
                    "type": "SINGLE_CHOICE",
                    "availableAnswers": [
                        {"id": 1000, "label": "Excellent", "metadata": {}},
                        {"id": 1001, "label": "Bon", "metadata": {}},
                        {"id": 1002, "label": "Moyen", "metadata": {}},
                        {"id": 1003, "label": "Mauvais", "metadata": {}},
                    ],
                    "answer": {
                        "id": 2001,
                        "type": "CHOICE",
                        "idAvailableAnswer": 1001,
                        "metadata": {},
                    },
                    "metadata": {},
                },
                {
                    "id": 102,
                    "label": "Quels aspects appréciez-vous ?",
                    "type": "MULTIPLE_CHOICE",
                    "availableAnswers": [
                        {"id": 1010, "label": "Accueil", "metadata": {}},
                        {"id": 1011, "label": "Prix", "metadata": {}},
                        {"id": 1012, "label": "Qualité", "metadata": {}},
                    ],
                    "answers": [
                        {"id": 2002, "type": "CHOICE", "idAvailableAnswer": 1010, "metadata": {}},
                        {"id": 2003, "type": "CHOICE", "idAvailableAnswer": 1012, "metadata": {}},
                    ],
                    "metadata": {},
                },
                {
                    "id": 103,
                    "label": "Notez notre site",
                    "type": "RATING",
                    "maxValue": 5,
                    "value": 4,
                    "metadata": {},
                },
                {
                    "id": 104,
                    "label": "Souhaitez-vous recevoir la newsletter ?",
                    "type": "CHECKBOX",
                    "checked": True,
                    "metadata": {},
                },
            ],
            "metadata": {
                "formation": "Benchmark survey",
            },
        }
    ]
}


def one_job(index: int) -> dict:
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/surveys/analyze", headers=HEADERS, json=PAYLOAD, timeout=60)
    r.raise_for_status()
    processing_id = r.json()["processing_id"]

    submitted_at = time.time()

    while time.time() - submitted_at < POLL_TIMEOUT:
        poll = requests.get(
            f"{BASE_URL}/surveys/processings/{processing_id}",
            headers={"X-API-Key": API_KEY},
            timeout=60,
        )
        poll.raise_for_status()
        body = poll.json()
        status = body["status"]

        if status == "FINISHED":
            return {
                "index": index,
                "processing_id": processing_id,
                "status": status,
                "submit_latency_s": round(submitted_at - t0, 3),
                "total_latency_s": round(time.time() - t0, 3),
            }

        if status == "FAILED":
            return {
                "index": index,
                "processing_id": processing_id,
                "status": status,
                "submit_latency_s": round(submitted_at - t0, 3),
                "total_latency_s": round(time.time() - t0, 3),
                "error_message": body.get("error_message"),
            }

        time.sleep(POLL_INTERVAL)

    return {
        "index": index,
        "processing_id": processing_id,
        "status": "TIMEOUT",
        "submit_latency_s": round(submitted_at - t0, 3),
        "total_latency_s": round(time.time() - t0, 3),
    }


def main() -> None:
    started = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = [ex.submit(one_job, i) for i in range(TOTAL)]
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            print(json.dumps(res, ensure_ascii=False))

    finished = [r["total_latency_s"] for r in results if r["status"] == "FINISHED"]
    failed = [r for r in results if r["status"] != "FINISHED"]

    print("\n=== SUMMARY ===")
    print(f"TOTAL={len(results)}")
    print(f"FINISHED={len(finished)}")
    print(f"FAILED_OR_TIMEOUT={len(failed)}")
    print(f"WALL_CLOCK_S={round(time.time() - started, 3)}")

    if finished:
        print(f"AVG_TOTAL_TIME={round(statistics.mean(finished), 3)}s")
        print(f"MEDIAN_TOTAL_TIME={round(statistics.median(finished), 3)}s")
        print(f"MAX_TOTAL_TIME={round(max(finished), 3)}s")


if __name__ == "__main__":
    main()