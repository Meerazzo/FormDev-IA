#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class TestResult:
    name: str
    status: str  # PASS / WARN / FAIL
    message: str


class RagEvalClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        expected_status: int | None = None,
    ) -> tuple[int, dict[str, Any] | list[Any] | str]:
        url = f"{self.base_url}{path}"

        if query:
            url = f"{url}?{urlencode(query)}"

        body = None
        headers = {
            "X-API-Key": self.api_key,
        }

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(req, timeout=self.timeout) as response:
                status = response.status
                raw = response.read().decode("utf-8")

        except HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8") or ""

        except URLError as exc:
            raise RuntimeError(f"Erreur réseau vers {url}: {exc}") from exc

        if expected_status is not None and status != expected_status:
            raise RuntimeError(
                f"{method} {path} a retourné {status}, attendu {expected_status}. Réponse: {raw[:500]}"
            )

        if not raw:
            return status, ""

        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw

    def get(self, path: str, *, query: dict[str, Any] | None = None) -> tuple[int, Any]:
        return self.request("GET", path, query=query)

    def post(self, path: str, *, payload: dict[str, Any]) -> tuple[int, Any]:
        return self.request("POST", path, payload=payload)


class RagEvaluator:
    def __init__(
        self,
        *,
        client: RagEvalClient,
        client_id: str,
        corpus_id: str,
        other_client_id: str,
    ) -> None:
        self.client = client
        self.client_id = client_id
        self.corpus_id = corpus_id
        self.other_client_id = other_client_id
        self.results: list[TestResult] = []
        self.last_conversation_id: str | None = None

    def add_result(self, name: str, status: str, message: str) -> None:
        self.results.append(TestResult(name=name, status=status, message=message))

    def run_test(self, name: str, fn) -> None:
        try:
            fn()
        except Exception as exc:
            self.add_result(name, "FAIL", str(exc))

    def run(self) -> int:
        tests = [
            ("Health RAG", self.test_health),
            ("Liste des corpus", self.test_corpora),
            ("Liste des sources du corpus", self.test_sources),
            ("Recherche vectorielle", self.test_search),
            ("Chat RAG sourcé", self.test_chat_grounded),
            ("Historique conversationnel", self.test_conversation_followup),
            ("Isolation client/conversation", self.test_conversation_isolation),
            ("Fallback hors contexte", self.test_fallback),
        ]

        for name, fn in tests:
            self.run_test(name, fn)

        return self.print_report()

    def test_health(self) -> None:
        status, payload = self.client.get("/rag/health")

        if status != 200:
            raise RuntimeError(f"Status HTTP inattendu: {status}")

        if not isinstance(payload, dict):
            raise RuntimeError("Réponse health invalide")

        self.add_result(
            "Health RAG",
            "PASS",
            f"Module disponible. Réponse: {payload}",
        )

    def test_corpora(self) -> None:
        status, payload = self.client.get(
            "/rag/corpora",
            query={"client_id": self.client_id},
        )

        if status != 200:
            raise RuntimeError(f"Status HTTP inattendu: {status}")

        corpora = payload.get("corpora", []) if isinstance(payload, dict) else []

        if not corpora:
            raise RuntimeError("Aucun corpus trouvé pour ce client")

        corpus_ids = [corpus.get("corpus_id") for corpus in corpora]

        if self.corpus_id not in corpus_ids:
            raise RuntimeError(
                f"Corpus attendu introuvable: {self.corpus_id}. Corpus disponibles: {corpus_ids}"
            )

        self.add_result(
            "Liste des corpus",
            "PASS",
            f"{len(corpora)} corpus trouvé(s): {corpus_ids}",
        )

    def test_sources(self) -> None:
        status, payload = self.client.get(
            f"/rag/corpora/{self.corpus_id}/sources",
            query={"client_id": self.client_id},
        )

        if status != 200:
            raise RuntimeError(f"Status HTTP inattendu: {status}")

        if not isinstance(payload, list):
            raise RuntimeError("La liste des sources n'est pas une liste JSON")

        indexed = [source for source in payload if source.get("status") == "indexed"]

        if not indexed:
            raise RuntimeError("Aucune source indexée trouvée dans le corpus")

        self.add_result(
            "Liste des sources du corpus",
            "PASS",
            f"{len(payload)} source(s), dont {len(indexed)} indexée(s)",
        )

    def test_search(self) -> None:
        status, payload = self.client.post(
            "/rag/search",
            payload={
                "client_id": self.client_id,
                "corpus_id": self.corpus_id,
                "query": "Que doit faire le module RAG documentaire pour les réponses ?",
                "top_k": 5,
                "score_threshold": 0.3,
            },
        )

        if status != 200:
            raise RuntimeError(f"Status HTTP inattendu: {status}")

        results = payload.get("results", []) if isinstance(payload, dict) else []

        if not results:
            raise RuntimeError("Aucun résultat de recherche vectorielle")

        best = results[0]

        self.add_result(
            "Recherche vectorielle",
            "PASS",
            f"{len(results)} résultat(s). Meilleur score: {best.get('score')}, source: {best.get('source_name')}",
        )

    def test_chat_grounded(self) -> None:
        status, payload = self.client.post(
            "/rag/chat",
            payload={
                "client_id": self.client_id,
                "corpus_id": self.corpus_id,
                "question": "Que doit faire le module RAG documentaire pour les réponses ?",
            },
        )

        if status != 200:
            raise RuntimeError(f"Status HTTP inattendu: {status}")

        if not isinstance(payload, dict):
            raise RuntimeError("Réponse chat invalide")

        answer = payload.get("answer") or ""
        sources = payload.get("sources") or []
        conversation_id = payload.get("conversation_id")

        if not answer:
            raise RuntimeError("Réponse vide")

        if not conversation_id:
            raise RuntimeError("conversation_id absent de la réponse")

        self.last_conversation_id = conversation_id

        if not sources:
            self.add_result(
                "Chat RAG sourcé",
                "WARN",
                "Réponse générée mais aucune source retournée",
            )
            return

        self.add_result(
            "Chat RAG sourcé",
            "PASS",
            f"Réponse générée avec {len(sources)} source(s), conversation_id={conversation_id}",
        )

    def test_conversation_followup(self) -> None:
        if not self.last_conversation_id:
            raise RuntimeError("Aucun conversation_id disponible depuis le test précédent")

        status, payload = self.client.post(
            "/rag/chat",
            payload={
                "client_id": self.client_id,
                "corpus_id": self.corpus_id,
                "conversation_id": self.last_conversation_id,
                "question": "Et comment doit-il éviter de mélanger les données ?",
            },
        )

        if status != 200:
            raise RuntimeError(f"Status HTTP inattendu: {status}")

        answer = payload.get("answer") or ""
        sources = payload.get("sources") or []
        returned_conversation_id = payload.get("conversation_id")

        if returned_conversation_id != self.last_conversation_id:
            raise RuntimeError(
                f"conversation_id différent: {returned_conversation_id} != {self.last_conversation_id}"
            )

        if not answer:
            raise RuntimeError("Réponse vide sur question de suivi")

        if not sources:
            self.add_result(
                "Historique conversationnel",
                "WARN",
                "La question de suivi répond, mais sans source",
            )
            return

        self.add_result(
            "Historique conversationnel",
            "PASS",
            f"Question de suivi traitée avec {len(sources)} source(s)",
        )

    def test_conversation_isolation(self) -> None:
        if not self.last_conversation_id:
            raise RuntimeError("Aucun conversation_id disponible pour tester l'isolation")

        status, payload = self.client.get(
            f"/rag/conversations/{self.last_conversation_id}",
            query={
                "client_id": self.other_client_id,
                "corpus_id": self.corpus_id,
            },
        )

        if status == 404:
            self.add_result(
                "Isolation client/conversation",
                "PASS",
                "Conversation inaccessible depuis un autre client",
            )
            return

        if status == 200:
            raise RuntimeError(
                "La conversation est accessible depuis un autre client, isolation incorrecte"
            )

        raise RuntimeError(f"Status inattendu pour isolation: {status}, payload={payload}")

    def test_fallback(self) -> None:
        status, payload = self.client.post(
            "/rag/chat",
            payload={
                "client_id": self.client_id,
                "corpus_id": self.corpus_id,
                "question": "Quelle est la recette exacte du kouign-amann selon les documents importés ?",
            },
        )

        if status != 200:
            raise RuntimeError(f"Status HTTP inattendu: {status}")

        answer = (payload.get("answer") or "").lower()
        sources = payload.get("sources") or []

        fallback_markers = [
            "je ne sais",
            "je n'ai pas",
            "documents fournis",
            "documents disponibles",
            "pas d'information",
            "aucune information",
            "ne permettent pas",
        ]

        has_fallback = any(marker in answer for marker in fallback_markers)

        if has_fallback:
            self.add_result(
                "Fallback hors contexte",
                "PASS",
                "Le modèle refuse correctement de répondre hors documents",
            )
            return

        if not sources:
            self.add_result(
                "Fallback hors contexte",
                "PASS",
                "Réponse sans source sur question hors contexte",
            )
            return

        self.add_result(
            "Fallback hors contexte",
            "WARN",
            "Le modèle a répondu avec des sources sur une question probablement hors contexte. À surveiller.",
        )

    def print_report(self) -> int:
        print("\n=== Rapport d'évaluation RAG ===\n")

        for result in self.results:
            icon = {
                "PASS": "✅",
                "WARN": "⚠️",
                "FAIL": "❌",
            }.get(result.status, "•")

            print(f"{icon} {result.status} — {result.name}")
            print(f"   {result.message}\n")

        fails = [result for result in self.results if result.status == "FAIL"]
        warns = [result for result in self.results if result.status == "WARN"]

        print("=== Résumé ===")
        print(f"PASS: {len([r for r in self.results if r.status == 'PASS'])}")
        print(f"WARN: {len(warns)}")
        print(f"FAIL: {len(fails)}")

        if fails:
            return 1

        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Évaluation qualité du module RAG")
    parser.add_argument("--base-url", default="http://localhost:8081")
    parser.add_argument("--api-key", default=os.getenv("API_KEY"))
    parser.add_argument("--client-id", default="client_demo")
    parser.add_argument("--corpus-id", default="default")
    parser.add_argument("--other-client-id", default="client_inconnu")
    args = parser.parse_args()

    if not args.api_key:
        print("Erreur: API key manquante. Définis API_KEY ou passe --api-key.", file=sys.stderr)
        return 2

    client = RagEvalClient(
        base_url=args.base_url,
        api_key=args.api_key,
    )

    evaluator = RagEvaluator(
        client=client,
        client_id=args.client_id,
        corpus_id=args.corpus_id,
        other_client_id=args.other_client_id,
    )

    started_at = time.time()
    exit_code = evaluator.run()
    duration = time.time() - started_at

    print(f"\nDurée: {duration:.2f}s")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
