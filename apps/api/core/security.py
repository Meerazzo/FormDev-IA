from __future__ import annotations
from fastapi import HTTPException
from config import API_KEYS_RAW

VALID_KEYS: set[str] = set()
KEY_TO_CLIENT: dict[str, str] = {}

for chunk in [c.strip() for c in API_KEYS_RAW.split(",") if c.strip()]:
    if ":" in chunk:
        client_id, key = chunk.split(":", 1)
        client_id = client_id.strip()
        key = key.strip()
        if key:
            VALID_KEYS.add(key)
            KEY_TO_CLIENT[key] = client_id
    else:
        key = chunk.strip()
        if key:
            VALID_KEYS.add(key)


def authenticate(x_api_key: str | None) -> tuple[str, str | None]:
    if not VALID_KEYS:
        raise HTTPException(status_code=500, detail="API_KEYS not configured")

    if not x_api_key or x_api_key not in VALID_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_api_key, KEY_TO_CLIENT.get(x_api_key)