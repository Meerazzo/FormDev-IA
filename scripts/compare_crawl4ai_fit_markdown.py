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


def get_markdown_variants(markdown_obj: Any) -> tuple[str, str]:
    raw = getattr(markdown_obj, "raw_markdown", None)
    fit = getattr(markdown_obj, "fit_markdown", None)

    internal = getattr(markdown_obj, "_markdown_result", None)

    if raw is None and internal is not None:
        raw = getattr(internal, "raw_markdown", None)

    if fit is None and internal is not None:
        fit = getattr(internal, "fit_markdown", None)

    raw = raw or str(markdown_obj or "")
    fit = fit or ""

    return raw, fit


def analyze_text(text: str, expected_keywords: list[str]) -> dict[str, Any]:
    text = text or ""
    lower_text = text.lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    expected_found = {
        keyword: keyword.lower() in lower_text
        for keyword in expected_keywords
    }

    return {
        "char_length": len(text),
        "word_count": len(re.findall(r"\w+", text)),
        "line_count": len(lines),
        "url_count": len(re.findall(r"https?://[^\s)>\"]+", text)),
        "heading_count": sum(1 for line in lines if line.startswith("#")),
        "table_like_line_count": sum(
            1 for line in lines
            if line.startswith("|") or " | " in line
        ),
        "money_match_count": len(
            re.findall(
                r"(?<!\w)(\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?)\s*(€|\$|£|EUR|USD|GBP|euros?|dollars?)",
                text,
                flags=re.IGNORECASE,
            )
        ),
        "percent_match_count": len(
            re.findall(
                r"(?<!\w)(\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?)\s*%",
                text,
                flags=re.IGNORECASE,
            )
        ),
        "expected_found_count": sum(1 for value in expected_found.values() if value),
        "expected_total_count": len(expected_keywords),
        "expected_found": expected_found,
    }


def score(metrics: dict[str, Any]) -> int:
    value = 0

    value += metrics["expected_found_count"] * 3

    if metrics["char_length"] >= 800:
        value += 2

    if metrics["heading_count"] > 0:
        value += 1

    if metrics["table_like_line_count"] > 0:
        value += 1

    if metrics["money_match_count"] > 0:
        value += 1

    if metrics["url_count"] > 100:
        value -= 3
    elif metrics["url_count"] > 30:
        value -= 1

    return value


def reduction(before: int, after: int) -> float:
    if before <= 0:
        return 0.0

    return round(1 - (after / before), 4)


async def crawl_with_fit(url: str, threshold: float):
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from crawl4ai.content_filter_strategy import PruningContentFilter

    config = CrawlerRunConfig(
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=threshold,
                threshold_type="dynamic",
                min_word_threshold=25,
            ),
            options={
                "ignore_links": True,
                "ignore_images": True,
                "skip_internal_links": True,
                "body_width": 0,
            },
        )
    )

    started = time.perf_counter()

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)

    elapsed = time.perf_counter() - started

    raw, fit = get_markdown_variants(result.markdown)

    return {
        "success": bool(result.success),
        "status_code": getattr(result, "status_code", None),
        "elapsed_seconds": round(elapsed, 3),
        "raw": raw,
        "fit": fit,
        "error": getattr(result, "error_message", None),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-file", required=True)
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    with Path(args.cases_file).open("r", encoding="utf-8") as file:
        cases = json.load(file)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_results = []
    csv_rows = []

    md_path = output_dir / f"crawl4ai_fit_markdown_{run_id}_excerpts.md"

    with md_path.open("w", encoding="utf-8") as md_file:
        md_file.write(f"# Comparatif Crawl4AI raw_markdown vs fit_markdown — {run_id}\n\n")

        for case in cases:
            name = case["name"]
            url = case["url"]
            expected_keywords = case.get("expected_keywords") or []

            print(f"\n=== {name} ===")
            print(url)

            crawled = await crawl_with_fit(url, args.threshold)

            raw = crawled["raw"]
            fit = crawled["fit"]

            # En prod, si fit est vide, on revient sur raw.
            fit_or_raw = fit or raw

            raw_metrics = analyze_text(raw, expected_keywords)
            fit_metrics = analyze_text(fit_or_raw, expected_keywords)

            raw_score = score(raw_metrics)
            fit_score = score(fit_metrics)

            print(
                f"- raw: score={raw_score} "
                f"chars={raw_metrics['char_length']} "
                f"urls={raw_metrics['url_count']} "
                f"expected={raw_metrics['expected_found_count']}/{raw_metrics['expected_total_count']}"
            )

            print(
                f"- fit: score={fit_score} "
                f"chars={fit_metrics['char_length']} "
                f"urls={fit_metrics['url_count']} "
                f"expected={fit_metrics['expected_found_count']}/{fit_metrics['expected_total_count']} "
                f"reduction={reduction(raw_metrics['char_length'], fit_metrics['char_length'])}"
            )

            csv_rows.append(
                {
                    "case_name": name,
                    "url": url,
                    "success": crawled["success"],
                    "status_code": crawled["status_code"],
                    "elapsed_seconds": crawled["elapsed_seconds"],
                    "raw_score": raw_score,
                    "fit_score": fit_score,
                    "raw_chars": raw_metrics["char_length"],
                    "fit_chars": fit_metrics["char_length"],
                    "char_reduction_ratio": reduction(raw_metrics["char_length"], fit_metrics["char_length"]),
                    "raw_urls": raw_metrics["url_count"],
                    "fit_urls": fit_metrics["url_count"],
                    "url_reduction_ratio": reduction(raw_metrics["url_count"], fit_metrics["url_count"]),
                    "raw_expected_found": raw_metrics["expected_found_count"],
                    "fit_expected_found": fit_metrics["expected_found_count"],
                    "expected_total": fit_metrics["expected_total_count"],
                    "raw_money": raw_metrics["money_match_count"],
                    "fit_money": fit_metrics["money_match_count"],
                    "raw_percent": raw_metrics["percent_match_count"],
                    "fit_percent": fit_metrics["percent_match_count"],
                    "fit_empty": not bool(fit.strip()),
                    "error": crawled["error"],
                }
            )

            json_results.append(
                {
                    "case": case,
                    "crawl": {
                        "success": crawled["success"],
                        "status_code": crawled["status_code"],
                        "elapsed_seconds": crawled["elapsed_seconds"],
                        "error": crawled["error"],
                    },
                    "raw_metrics": raw_metrics,
                    "fit_metrics": fit_metrics,
                    "raw_score": raw_score,
                    "fit_score": fit_score,
                    "fit_empty": not bool(fit.strip()),
                }
            )

            md_file.write(f"## {name}\n\n")
            md_file.write(f"URL : {url}\n\n")

            md_file.write("### RAW\n\n")
            md_file.write(f"- Score : {raw_score}\n")
            md_file.write(f"- Caractères : {raw_metrics['char_length']}\n")
            md_file.write(f"- URLs : {raw_metrics['url_count']}\n")
            md_file.write(f"- Mots attendus : {raw_metrics['expected_found_count']}/{raw_metrics['expected_total_count']}\n\n")
            md_file.write("```text\n")
            md_file.write(raw[:2500].replace("```", "'''"))
            md_file.write("\n```\n\n")

            md_file.write("### FIT\n\n")
            md_file.write(f"- Score : {fit_score}\n")
            md_file.write(f"- Caractères : {fit_metrics['char_length']}\n")
            md_file.write(f"- URLs : {fit_metrics['url_count']}\n")
            md_file.write(f"- Réduction : {reduction(raw_metrics['char_length'], fit_metrics['char_length'])}\n")
            md_file.write(f"- Mots attendus : {fit_metrics['expected_found_count']}/{fit_metrics['expected_total_count']}\n\n")
            md_file.write("```text\n")
            md_file.write(fit_or_raw[:2500].replace("```", "'''"))
            md_file.write("\n```\n\n")

    json_path = output_dir / f"crawl4ai_fit_markdown_{run_id}.json"
    csv_path = output_dir / f"crawl4ai_fit_markdown_{run_id}.csv"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "run_id": run_id,
                "threshold": args.threshold,
                "results": json_results,
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

    print("\n=== Rapports générés ===")
    print(json_path)
    print(csv_path)
    print(md_path)


if __name__ == "__main__":
    asyncio.run(main())
