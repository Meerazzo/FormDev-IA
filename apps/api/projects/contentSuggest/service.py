from __future__ import annotations

import re
import time
from typing import Tuple, Optional

from schemas.content import ContentEnrichRequest
from services.vllm_client import VLLMClient
from projects.contentSuggest.prompts import build_system_prompt


def _sanitize_output(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```.*?\n", "", t, flags=re.DOTALL)
    t = re.sub(r"\n```$", "", t)
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _max_tokens_for_options(length: str) -> int:
    if length == "short":
        return 220
    if length == "long":
        return 500
    return 320


async def enrich_content(req: ContentEnrichRequest, client: VLLMClient) -> Tuple[str, Optional[str], float]:
    options = req.options
    length = (options.length if options else "medium") or "medium"
    max_tokens = _max_tokens_for_options(length)

    system_prompt = build_system_prompt(req.context, req.options)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.text.strip()},
    ]

    t0 = time.perf_counter()
    resp = await client.chat(
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.4,
        top_p=0.9,
        timeout_s=120,
    )
    dt_ms = (time.perf_counter() - t0) * 1000.0

    enriched = _sanitize_output(resp.text or "")
    if not enriched:
        raise RuntimeError("Empty model output")

    return enriched, resp.model, dt_ms