from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from core.config import settings


class VLLMConnectionError(RuntimeError):
    pass


class VLLMUpstreamError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"vLLM error {status_code}")
        self.status_code = status_code
        self.body = body


@dataclass
class VLLMChatResult:
    text: str
    model: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class VLLMClient:
    base_url: str = settings.VLLM_BASE_URL

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._timeout = httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=10.0)

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(url, json=payload)
        except httpx.ConnectError as e:
            raise VLLMConnectionError("Cannot reach inference server (vLLM)") from e
        except httpx.ReadTimeout as e:
            raise TimeoutError("vLLM read timeout") from e

        if r.status_code >= 400:
            raise VLLMUpstreamError(r.status_code, r.text)

        return r.json()

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 0.9,
        timeout_s: int = 120,
        model: Optional[str] = None,
    ) -> VLLMChatResult:
        # timeout par requête (sans modifier self._timeout global)
        timeout = httpx.Timeout(connect=10.0, read=float(timeout_s), write=float(timeout_s), pool=10.0)

        payload: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if model:
            payload["model"] = model

        url = f"{self.base_url}/v1/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=payload)
        except httpx.ConnectError as e:
            raise VLLMConnectionError("Cannot reach inference server (vLLM)") from e
        except httpx.ReadTimeout as e:
            raise TimeoutError("vLLM read timeout") from e

        if r.status_code >= 400:
            raise VLLMUpstreamError(r.status_code, r.text)

        data = r.json()
        text = ""
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception:
            text = ""

        return VLLMChatResult(text=text, model=data.get("model"), raw=data)


def get_vllm_client() -> VLLMClient:
    return VLLMClient()