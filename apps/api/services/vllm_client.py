"""
Client HTTP vers le serveur d'inférence vLLM.

Ce module centralise les appels au serveur vLLM afin de :
- isoler la logique réseau du reste de l'application,
- uniformiser la gestion des erreurs,
- simplifier l'utilisation côté services métier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from core.config import settings
from utils.json import parse_json_lenient


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
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=300.0,
            write=300.0,
            pool=10.0,
        )

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Envoie une requête brute au endpoint OpenAI-compatible de vLLM.

        Args:
            payload: payload JSON complet transmis à l'API vLLM.

        Returns:
            La réponse JSON brute renvoyée par vLLM.

        Raises:
            VLLMConnectionError: si le serveur d'inférence est injoignable.
            TimeoutError: si la requête dépasse le délai autorisé.
            VLLMUpstreamError: si vLLM retourne un statut HTTP >= 400.
        """
        url = f"{self.base_url}/v1/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
        except httpx.ConnectError as e:
            raise VLLMConnectionError("Cannot reach inference server (vLLM)") from e
        except httpx.ReadTimeout as e:
            raise TimeoutError("vLLM read timeout") from e

        if response.status_code >= 400:
            raise VLLMUpstreamError(response.status_code, response.text)

        return response.json()

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 400,
        temperature: float = 0.2,
        top_p: float = 0.9,
        timeout_s: int = 120,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Effectue un appel de génération puis tente de parser la sortie en JSON.

        Cette méthode repose sur un parsing tolérant afin de récupérer un objet JSON
        même si le modèle entoure le contenu de texte parasite ou de balises markdown.
        """
        result = await self.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            timeout_s=timeout_s,
            model=model,
        )

        parsed, _ = parse_json_lenient((result.text or "").strip())
        return parsed

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 0.9,
        timeout_s: int = 120,
        model: Optional[str] = None,
    ) -> VLLMChatResult:
        """
        Effectue un appel de génération de texte via vLLM à partir d'une liste de messages.

        Cette méthode encapsule la requête réseau et extrait le texte principal
        retourné par le modèle.

        Returns:
            Un objet VLLMChatResult contenant :
            - le texte généré,
            - le modèle utilisé,
            - la réponse brute complète.
        """
        timeout = httpx.Timeout(
            connect=10.0,
            read=float(timeout_s),
            write=float(timeout_s),
            pool=10.0,
        )

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
                response = await client.post(url, json=payload)
        except httpx.ConnectError as e:
            raise VLLMConnectionError("Cannot reach inference server (vLLM)") from e
        except httpx.ReadTimeout as e:
            raise TimeoutError("vLLM read timeout") from e

        if response.status_code >= 400:
            raise VLLMUpstreamError(response.status_code, response.text)

        data = response.json()

        text = ""
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception:
            text = ""

        return VLLMChatResult(
            text=text,
            model=data.get("model"),
            raw=data,
        )


def get_vllm_client() -> VLLMClient:
    return VLLMClient()