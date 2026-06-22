from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
API_DIR = ROOT_DIR / "apps" / "api"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


DEFAULT_TEST_CASES = [
    {
        "name": "niveau_1_page_simple",
        "url": "https://www.form-dev.fr/",
        "expected_keywords": ["Formdev", "formation"],
    },
    {
        "name": "niveau_2_tableaux_tarifs",
        "url": "https://www.form-dev.fr/tarifs/",
        "expected_keywords": ["Multi société", "80", "Tarif"],
    },
    {
        "name": "niveau_3_documentation_markdown",
        "url": "https://docs.crawl4ai.com/",
        "expected_keywords": ["Crawl4AI", "Markdown"],
    },
    {
        "name": "niveau_4_page_javascript",
        "url": "https://quotes.toscrape.com/js/",
        "expected_keywords": ["Albert Einstein", "Quotes"],
    },
    {
        "name": "niveau_5_scroll_javascript",
        "url": "https://quotes.toscrape.com/scroll",
        "expected_keywords": ["Albert Einstein"],
    },
]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    for attr in ["raw_markdown", "fit_markdown", "markdown"]:
        attr_value = getattr(value, attr, None)
        if isinstance(attr_value, str):
            return attr_value

    return str(value)


def analyze_text(text: str, expected_keywords: list[str]) -> dict[str, Any]:
    text = text or ""
    lower_text = text.lower()

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    money_matches = re.findall(
        r"(?<!\w)(\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?)\s*(€|\$|£|EUR|USD|GBP|euros?|dollars?)",
        text,
        flags=re.IGNORECASE,
    )

    percent_matches = re.findall(
        r"(?<!\w)(\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?)\s*%",
        text,
        flags=re.IGNORECASE,
    )

    email_matches = re.findall(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        text,
    )

    url_matches = re.findall(
        r"https?://[^\s)>\"]+",
        text,
        flags=re.IGNORECASE,
    )

    markdown_heading_count = sum(
        1 for line in lines
        if line.startswith("#")
    )

    table_like_line_count = sum(
        1 for line in lines
        if line.startswith("|") or " | " in line or "Ligne " in line or "Colonne " in line
    )

    expected_found = {
        keyword: keyword.lower() in lower_text
        for keyword in expected_keywords
    }

    expected_found_count = sum(1 for found in expected_found.values() if found)

    return {
        "char_length": len(text),
        "word_count": len(re.findall(r"\w+", text)),
        "line_count": len(lines),
        "markdown_heading_count": markdown_heading_count,
        "table_like_line_count": table_like_line_count,
        "money_match_count": len(money_matches),
        "percent_match_count": len(percent_matches),
        "email_match_count": len(email_matches),
        "url_match_count": len(url_matches),
        "expected_found_count": expected_found_count,
        "expected_total_count": len(expected_keywords),
        "expected_found": expected_found,
    }


def run_basic_parser(url: str, expected_keywords: list[str]) -> dict[str, Any]:
    from services.rag.ingestion.parsers.url_parser import UrlParser

    started = time.perf_counter()

    try:
        document = UrlParser().parse_url(url)
        elapsed = time.perf_counter() - started

        text = document.text or ""
        metrics = analyze_text(text, expected_keywords)

        return {
            "extractor": "basic_url_parser",
            "success": True,
            "status_code": document.metadata.get("status_code"),
            "elapsed_seconds": round(elapsed, 3),
            "metadata": document.metadata,
            "metrics": metrics,
            "excerpt": text[:2500],
            "error": None,
        }

    except Exception as exc:
        elapsed = time.perf_counter() - started

        return {
            "extractor": "basic_url_parser",
            "success": False,
            "status_code": None,
            "elapsed_seconds": round(elapsed, 3),
            "metadata": {},
            "metrics": analyze_text("", expected_keywords),
            "excerpt": "",
            "error": str(exc),
        }


async def run_crawl4ai_parser(url: str, expected_keywords: list[str]) -> dict[str, Any]:
    started = time.perf_counter()

    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)

        elapsed = time.perf_counter() - started

        markdown = normalize_text(getattr(result, "markdown", ""))
        cleaned_html = normalize_text(getattr(result, "cleaned_html", ""))

        text = markdown or cleaned_html
        metrics = analyze_text(text, expected_keywords)

        return {
            "extractor": "crawl4ai",
            "success": bool(getattr(result, "success", True)) and bool(text.strip()),
            "status_code": getattr(result, "status_code", None),
            "elapsed_seconds": round(elapsed, 3),
            "metadata": {
                "url": url,
                "final_url": str(getattr(result, "url", "") or url),
                "has_markdown": bool(markdown.strip()),
                "has_cleaned_html": bool(cleaned_html.strip()),
                "markdown_char_length": len(markdown),
                "cleaned_html_char_length": len(cleaned_html),
            },
            "metrics": metrics,
            "excerpt": text[:2500],
            "error": getattr(result, "error_message", None),
        }

    except Exception as exc:
        elapsed = time.perf_counter() - started

        return {
            "extractor": "crawl4ai",
            "success": False,
            "status_code": None,
            "elapsed_seconds": round(elapsed, 3),
            "metadata": {},
            "metrics": analyze_text("", expected_keywords),
            "excerpt": "",
            "error": str(exc),
        }


def score_result(result: dict[str, Any]) -> int:
    metrics = result.get("metrics", {})
    score = 0

    if result.get("success"):
        score += 3

    score += int(metrics.get("expected_found_count", 0)) * 2

    if metrics.get("char_length", 0) >= 500:
        score += 1

    if metrics.get("markdown_heading_count", 0) > 0:
        score += 1

    if metrics.get("table_like_line_count", 0) > 0:
        score += 1

    if metrics.get("money_match_count", 0) > 0:
        score += 1

    return score


def flatten_for_csv(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics", {})

    return {
        "case_name": case["name"],
        "url": case["url"],
        "extractor": result["extractor"],
        "success": result["success"],
        "status_code": result["status_code"],
        "elapsed_seconds": result["elapsed_seconds"],
        "score": score_result(result),
        "char_length": metrics.get("char_length"),
        "word_count": metrics.get("word_count"),
        "line_count": metrics.get("line_count"),
        "markdown_heading_count": metrics.get("markdown_heading_count"),
        "table_like_line_count": metrics.get("table_like_line_count"),
        "money_match_count": metrics.get("money_match_count"),
        "percent_match_count": metrics.get("percent_match_count"),
        "email_match_count": metrics.get("email_match_count"),
        "url_match_count": metrics.get("url_match_count"),
        "expected_found_count": metrics.get("expected_found_count"),
        "expected_total_count": metrics.get("expected_total_count"),
        "error": result.get("error"),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument(
        "--only",
        choices=["basic", "crawl4ai", "both"],
        default="both",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="URL additionnelle à tester. Peut être répété.",
    )
    parser.add_argument(
        "--cases-file",
        default=None,
        help="Fichier JSON contenant une liste de cas de test avec name, url et expected_keywords.",
    )
    args = parser.parse_args()

    if args.cases_file:
        with Path(args.cases_file).open("r", encoding="utf-8") as file:
            test_cases = json.load(file)
    else:
        test_cases = list(DEFAULT_TEST_CASES)

    for index, url in enumerate(args.url, start=1):
        test_cases.append(
            {
                "name": f"url_custom_{index}",
                "url": url,
                "expected_keywords": [],
            }
        )

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []

    for case in test_cases:
        print(f"\n=== {case['name']} ===")
        print(case["url"])

        case_results = []

        if args.only in {"basic", "both"}:
            basic_result = run_basic_parser(
                case["url"],
                case["expected_keywords"],
            )
            case_results.append(basic_result)

        if args.only in {"crawl4ai", "both"}:
            crawl4ai_result = await run_crawl4ai_parser(
                case["url"],
                case["expected_keywords"],
            )
            case_results.append(crawl4ai_result)

        for result in case_results:
            metrics = result["metrics"]
            quality_score = score_result(result)

            print(
                f"- {result['extractor']}: "
                f"success={result['success']} "
                f"score={quality_score} "
                f"chars={metrics['char_length']} "
                f"expected={metrics['expected_found_count']}/{metrics['expected_total_count']} "
                f"tables={metrics['table_like_line_count']} "
                f"money={metrics['money_match_count']} "
                f"time={result['elapsed_seconds']}s"
            )

            if result.get("error"):
                print(f"  error={result['error']}")

            csv_rows.append(flatten_for_csv(case, result))

        all_results.append(
            {
                "case": case,
                "results": case_results,
            }
        )

    json_path = output_dir / f"crawl4ai_compare_{run_id}.json"
    csv_path = output_dir / f"crawl4ai_compare_{run_id}.csv"
    md_path = output_dir / f"crawl4ai_compare_{run_id}_excerpts.md"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "run_id": run_id,
                "results": all_results,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    if csv_rows:
        with csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)

    with md_path.open("w", encoding="utf-8") as file:
        file.write(f"# Comparatif extracteurs URL — {run_id}\n\n")

        for item in all_results:
            case = item["case"]
            file.write(f"## {case['name']}\n\n")
            file.write(f"URL : {case['url']}\n\n")

            for result in item["results"]:
                file.write(f"### {result['extractor']}\n\n")
                file.write(f"- Success : {result['success']}\n")
                file.write(f"- Score : {score_result(result)}\n")
                file.write(f"- Temps : {result['elapsed_seconds']}s\n")
                file.write(f"- Erreur : {result.get('error')}\n\n")
                file.write("```text\n")
                file.write((result.get("excerpt") or "").replace("```", "'''"))
                file.write("\n```\n\n")

    print("\n=== Rapports générés ===")
    print(json_path)
    print(csv_path)
    print(md_path)


if __name__ == "__main__":
    asyncio.run(main())
