"""
Utilitaires de parsing JSON tolérant.

Permet de récupérer un objet JSON même si le modèle retourne :
- du texte avant/après le JSON,
- un bloc markdown ```json ... ```,
- un tableau ou un objet JSON imbriqué.
"""

import json
import re
from typing import Any, Dict, Tuple


CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_first_json_block(text: str) -> str | None:
    if not text:
        return None

    candidate = text.strip()

    fence_match = CODE_FENCE_RE.search(candidate)
    if fence_match:
        candidate = fence_match.group(1).strip()

    starts = []
    obj_start = candidate.find("{")
    arr_start = candidate.find("[")

    if obj_start != -1:
        starts.append((obj_start, "{", "}"))
    if arr_start != -1:
        starts.append((arr_start, "[", "]"))

    if not starts:
        return None

    start_idx, opening, closing = min(starts, key=lambda x: x[0])

    depth = 0
    in_string = False
    escape = False

    for i in range(start_idx, len(candidate)):
        ch = candidate[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return candidate[start_idx : i + 1]

    return None


def parse_json_lenient(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Retourne:
    - le dict parsé
    - le mode de parsing: direct / extracted / failed
    """
    raw = (text or "").strip()
    if not raw:
        return {}, "failed"

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"_": parsed}, "direct"
    except Exception:
        pass

    extracted = extract_first_json_block(raw)
    if not extracted:
        return {}, "failed"

    try:
        parsed = json.loads(extracted)
        return parsed if isinstance(parsed, dict) else {"_": parsed}, "extracted"
    except Exception:
        return {}, "failed"