#!/usr/bin/env python3
"""
Benchmark réel du module RAG FormDev.

Ce script teste :
- healthcheck RAG ;
- fallback avant ingestion ;
- ingestion fichier async ;
- suivi de job ;
- liste des sources ;
- recherche vectorielle ;
- chat RAG ;
- historique conversationnel ;
- streaming SSE ;
- fallback stream ;
- isolation entre corpus ;
- ingestion URL optionnelle.

Aucune dépendance externe requise.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class BenchmarkCase:
    name: str
    status: str
    details: str
    latency_ms: int | None = None
    corpus_id: str | None = None
    question: str | None = None
    answer: str | None = None
    sources_count: int | None = None
    top_score: float | None = None
    retrieval_confidence: str | None = None
    fallback: bool | None = None
    conversation_id: str | None = None
    job_id: str | None = None
    source_id: str | None = None
    raw: dict[str, Any] | list[Any] | str | None = None


class RagBenchmark:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client_id: str,
        run_id: str,
        timeout: int,
        job_timeout: int,
        poll_interval: float,
        url: str | None = None,
        url_question: str | None = None,
        url_expected: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client_id = client_id
        self.run_id = run_id
        self.timeout = timeout
        self.job_timeout = job_timeout
        self.poll_interval = poll_interval

        self.url = url
        self.url_question = url_question
        self.url_expected = url_expected

        self.premium_corpus_id = f"bench_premium_{run_id}"
        self.empty_corpus_id = f"bench_empty_{run_id}"
        self.url_corpus_id = f"bench_url_{run_id}"

        self.cases: list[BenchmarkCase] = []

    def run(self) -> dict[str, Any]:
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        self.test_health()
        self.test_fallback_before_ingestion()
        self.test_file_ingestion_and_chat()
        self.test_isolation_empty_corpus()
        self.test_streaming()
        self.test_optional_url_ingestion()

        finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        summary = {
            "PASS": sum(1 for case in self.cases if case.status == "PASS"),
            "WARN": sum(1 for case in self.cases if case.status == "WARN"),
            "FAIL": sum(1 for case in self.cases if case.status == "FAIL"),
        }

        return {
            "run_id": self.run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "base_url": self.base_url,
            "client_id": self.client_id,
            "corpora": {
                "premium": self.premium_corpus_id,
                "empty": self.empty_corpus_id,
                "url": self.url_corpus_id if self.url else None,
            },
            "summary": summary,
            "cases": [asdict(case) for case in self.cases],
        }

    def add_case(self, case: BenchmarkCase) -> None:
        self.cases.append(case)

        icon = {
            "PASS": "✅",
            "WARN": "⚠️",
            "FAIL": "❌",
        }.get(case.status, "•")

        print(f"{icon} {case.status} — {case.name}")
        print(f"   {case.details}")

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, Any] | list[Any] | str]:
        url = f"{self.base_url}{path}"

        headers = {
            "X-API-Key": self.api_key,
        }

        data = None

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(
            url,
            data=data,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urlopen(req, timeout=self.timeout) as response:
                status = response.status
                payload_raw = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            payload_raw = exc.read().decode("utf-8")
        except URLError as exc:
            raise RuntimeError(f"Erreur réseau vers {url}: {exc}") from exc

        try:
            payload: dict[str, Any] | list[Any] | str = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = payload_raw

        if status not in expected_statuses:
            raise RuntimeError(
                f"{method} {path} a retourné HTTP {status}, attendu {expected_statuses}. "
                f"Réponse: {payload}"
            )

        return status, payload

    def post_multipart_file(
        self,
        path: str,
        *,
        file_path: Path,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, Any] | list[Any] | str]:
        url = f"{self.base_url}{path}"

        boundary = f"----FormDevRagBenchmark{uuid.uuid4().hex}"
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

        file_bytes = file_path.read_bytes()

        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="file"; '
                    f'filename="{file_path.name}"\r\n'
                ).encode(),
                f"Content-Type: {mime_type}\r\n\r\n".encode(),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )

        req = Request(
            url,
            data=body,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as response:
                status = response.status
                payload_raw = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            payload_raw = exc.read().decode("utf-8")

        try:
            payload: dict[str, Any] | list[Any] | str = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = payload_raw

        if status not in expected_statuses:
            raise RuntimeError(
                f"POST multipart {path} a retourné HTTP {status}, attendu {expected_statuses}. "
                f"Réponse: {payload}"
            )

        return status, payload

    def parse_sse(self, raw: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        for block in raw.strip().split("\n\n"):
            if not block.strip():
                continue

            event_name = None
            data_value = None

            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line.replace("event:", "", 1).strip()

                if line.startswith("data:"):
                    raw_data = line.replace("data:", "", 1).strip()
                    try:
                        data_value = json.loads(raw_data)
                    except json.JSONDecodeError:
                        data_value = raw_data

            if event_name:
                events.append(
                    {
                        "event": event_name,
                        "data": data_value,
                    }
                )

        return events

    def post_stream(self, body: dict[str, Any]) -> tuple[int, str, list[dict[str, Any]]]:
        url = f"{self.base_url}/rag/chat/stream"

        req = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as response:
                status = response.status
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")

        events = self.parse_sse(raw)
        return status, raw, events

    def wait_job(self, job_id: str) -> dict[str, Any]:
        deadline = time.time() + self.job_timeout
        last_payload: dict[str, Any] | None = None

        while time.time() < deadline:
            _, payload = self.request_json("GET", f"/rag/jobs/{job_id}")

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse job invalide: {payload}")

            last_payload = payload
            status = payload.get("status")

            if status in {"succeeded", "failed"}:
                return payload

            time.sleep(self.poll_interval)

        raise TimeoutError(
            f"Timeout en attendant le job {job_id}. Dernière réponse: {last_payload}"
        )

    def test_health(self) -> None:
        start = time.time()

        try:
            _, payload = self.request_json("GET", "/rag/health")

            ok = isinstance(payload, dict) and payload.get("status") in {"ok", "degraded"}
            qdrant_ok = isinstance(payload, dict) and payload.get("qdrant_available") is True

            self.add_case(
                BenchmarkCase(
                    name="Health RAG",
                    status="PASS" if ok and qdrant_ok else "WARN",
                    details=f"Module={payload.get('status') if isinstance(payload, dict) else 'unknown'}, Qdrant={payload.get('qdrant_available') if isinstance(payload, dict) else 'unknown'}",
                    latency_ms=self.elapsed_ms(start),
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Health RAG",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                )
            )

    def test_fallback_before_ingestion(self) -> None:
        question = "Quel est le tarif annuel de l'offre Premium FormDev RAG ?"

        body = {
            "client_id": self.client_id,
            "corpus_id": self.premium_corpus_id,
            "conversation_id": None,
            "question": question,
            "top_k": 5,
            "score_threshold": None,
            "temperature": 0.2,
            "max_tokens": 512,
        }

        start = time.time()

        try:
            _, payload = self.request_json("POST", "/rag/chat", body=body)

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse invalide: {payload}")

            sources = payload.get("sources") or []
            answer = payload.get("answer") or ""
            fallback = self.is_fallback_response(payload)

            self.add_case(
                BenchmarkCase(
                    name="Fallback avant ingestion",
                    status="PASS" if fallback else "WARN",
                    details=(
                        "Le RAG refuse correctement avant ingestion."
                        if fallback
                        else "Le RAG a répondu alors que le corpus ne contient pas encore l'information."
                    ),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                    answer=answer,
                    sources_count=len(sources),
                    top_score=payload.get("top_score"),
                    retrieval_confidence=payload.get("retrieval_confidence"),
                    fallback=fallback,
                    conversation_id=payload.get("conversation_id"),
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Fallback avant ingestion",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                )
            )

    def test_file_ingestion_and_chat(self) -> None:
        doc_path = self.create_premium_demo_file()

        job_id = None
        source_id = None

        start = time.time()

        try:
            params = urlencode(
                {
                    "client_id": self.client_id,
                    "corpus_id": self.premium_corpus_id,
                }
            )

            _, upload_payload = self.post_multipart_file(
                f"/rag/sources/upload-async?{params}",
                file_path=doc_path,
            )

            if not isinstance(upload_payload, dict):
                raise RuntimeError(f"Réponse upload invalide: {upload_payload}")

            job_id = upload_payload.get("job_id")
            source_id = upload_payload.get("source_id")

            if not job_id:
                raise RuntimeError(f"job_id absent dans la réponse: {upload_payload}")

            self.add_case(
                BenchmarkCase(
                    name="Upload fichier async",
                    status="PASS",
                    details=f"Job créé: {job_id}, source: {source_id}",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    job_id=job_id,
                    source_id=source_id,
                    raw=upload_payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Upload fichier async",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                )
            )
            return

        start = time.time()

        try:
            job_payload = self.wait_job(job_id)

            succeeded = job_payload.get("status") == "succeeded"

            self.add_case(
                BenchmarkCase(
                    name="Job ingestion fichier",
                    status="PASS" if succeeded else "FAIL",
                    details=f"Status job: {job_payload.get('status')}",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    job_id=job_id,
                    source_id=source_id,
                    raw=job_payload,
                )
            )

            if not succeeded:
                return
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Job ingestion fichier",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    job_id=job_id,
                    source_id=source_id,
                )
            )
            return

        self.test_sources_list()
        self.test_search_after_ingestion()
        conversation_id = self.test_chat_after_ingestion()
        self.test_history_follow_up(conversation_id)

    def test_sources_list(self) -> None:
        start = time.time()

        try:
            params = urlencode({"client_id": self.client_id})
            _, payload = self.request_json(
                "GET",
                f"/rag/corpora/{self.premium_corpus_id}/sources?{params}",
            )

            if isinstance(payload, dict):
                sources = payload.get("sources") or []
            elif isinstance(payload, list):
                sources = payload
            else:
                sources = []

            indexed_sources = [
                source for source in sources
                if isinstance(source, dict) and source.get("status") == "indexed"
            ]

            self.add_case(
                BenchmarkCase(
                    name="Sources du corpus après ingestion",
                    status="PASS" if indexed_sources else "WARN",
                    details=f"{len(sources)} source(s), {len(indexed_sources)} indexée(s)",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    sources_count=len(sources),
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Sources du corpus après ingestion",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                )
            )

    def test_search_after_ingestion(self) -> None:
        question = "tarif annuel offre Premium FormDev RAG"

        body = {
            "client_id": self.client_id,
            "corpus_id": self.premium_corpus_id,
            "query": question,
            "top_k": 5,
            "score_threshold": 0.0,
        }

        start = time.time()

        try:
            _, payload = self.request_json("POST", "/rag/search", body=body)

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse search invalide: {payload}")

            results = payload.get("results") or []
            top_result = results[0] if results else {}
            text = (top_result.get("text") or "").lower() if isinstance(top_result, dict) else ""

            has_expected = "1290" in text or "premium" in text

            self.add_case(
                BenchmarkCase(
                    name="Recherche vectorielle après ingestion",
                    status="PASS" if results and has_expected else "WARN",
                    details=f"{len(results)} résultat(s). Top score: {top_result.get('score') if isinstance(top_result, dict) else None}",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                    sources_count=len(results),
                    top_score=top_result.get("score") if isinstance(top_result, dict) else None,
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Recherche vectorielle après ingestion",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                )
            )

    def test_chat_after_ingestion(self) -> str | None:
        question = "Quel est le tarif annuel de l'offre Premium FormDev RAG ?"

        body = {
            "client_id": self.client_id,
            "corpus_id": self.premium_corpus_id,
            "conversation_id": None,
            "question": question,
            "top_k": 5,
            "score_threshold": None,
            "temperature": 0.2,
            "max_tokens": 512,
        }

        start = time.time()

        try:
            _, payload = self.request_json("POST", "/rag/chat", body=body)

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse chat invalide: {payload}")

            answer = payload.get("answer") or ""
            sources = payload.get("sources") or []
            answer_lower = answer.lower()

            has_price = (
                "1290" in answer_lower
                or "1 290" in answer_lower
                or "mille deux cent quatre-vingt-dix" in answer_lower
            )

            ok = has_price and len(sources) >= 1

            self.add_case(
                BenchmarkCase(
                    name="Chat après ingestion fichier",
                    status="PASS" if ok else "WARN",
                    details=(
                        "Le RAG répond avec le tarif et au moins une source."
                        if ok
                        else "Le RAG ne retrouve pas clairement le tarif ou ne renvoie pas de source."
                    ),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                    answer=answer,
                    sources_count=len(sources),
                    top_score=payload.get("top_score"),
                    retrieval_confidence=payload.get("retrieval_confidence"),
                    fallback=len(sources) == 0,
                    conversation_id=payload.get("conversation_id"),
                    raw=payload,
                )
            )

            return payload.get("conversation_id")
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Chat après ingestion fichier",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                )
            )
            return None

    def test_history_follow_up(self, conversation_id: str | None) -> None:
        if not conversation_id:
            self.add_case(
                BenchmarkCase(
                    name="Historique conversationnel",
                    status="FAIL",
                    details="conversation_id absent, test impossible.",
                    corpus_id=self.premium_corpus_id,
                )
            )
            return

        question = "Et qu'est-ce qui est inclus dans cette offre ?"

        body = {
            "client_id": self.client_id,
            "corpus_id": self.premium_corpus_id,
            "conversation_id": conversation_id,
            "question": question,
            "top_k": 5,
            "score_threshold": None,
            "temperature": 0.2,
            "max_tokens": 700,
        }

        start = time.time()

        try:
            _, payload = self.request_json("POST", "/rag/chat", body=body)

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse suivi invalide: {payload}")

            answer = payload.get("answer") or ""
            answer_lower = answer.lower()
            sources = payload.get("sources") or []

            expected_terms = [
                "chatbot",
                "pdf",
                "docx",
                "txt",
                "url",
                "vectorielle",
                "historique",
                "streaming",
            ]

            matched_terms = [term for term in expected_terms if term in answer_lower]

            ok = len(matched_terms) >= 2 and len(sources) >= 1

            self.add_case(
                BenchmarkCase(
                    name="Historique conversationnel — question de suivi",
                    status="PASS" if ok else "WARN",
                    details=(
                        f"Termes retrouvés: {matched_terms}"
                        if matched_terms
                        else "La question de suivi semble mal comprise ou pas assez reliée à l'historique."
                    ),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                    answer=answer,
                    sources_count=len(sources),
                    top_score=payload.get("top_score"),
                    retrieval_confidence=payload.get("retrieval_confidence"),
                    fallback=len(sources) == 0,
                    conversation_id=conversation_id,
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Historique conversationnel — question de suivi",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                    conversation_id=conversation_id,
                )
            )

    def test_isolation_empty_corpus(self) -> None:
        question = "Quel est le tarif annuel de l'offre Premium FormDev RAG ?"

        body = {
            "client_id": self.client_id,
            "corpus_id": self.empty_corpus_id,
            "conversation_id": None,
            "question": question,
            "top_k": 5,
            "score_threshold": None,
            "temperature": 0.2,
            "max_tokens": 512,
        }

        start = time.time()

        try:
            _, payload = self.request_json("POST", "/rag/chat", body=body)

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse isolation invalide: {payload}")

            sources = payload.get("sources") or []
            answer = payload.get("answer") or ""
            fallback = self.is_fallback_response(payload)

            self.add_case(
                BenchmarkCase(
                    name="Isolation corpus vide",
                    status="PASS" if fallback else "WARN",
                    details=(
                        "Le corpus vide ne récupère pas les informations du corpus premium."
                        if fallback
                        else "Risque d'isolation: réponse trouvée dans un corpus qui devrait être vide."
                    ),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.empty_corpus_id,
                    question=question,
                    answer=answer,
                    sources_count=len(sources),
                    top_score=payload.get("top_score"),
                    retrieval_confidence=payload.get("retrieval_confidence"),
                    fallback=fallback,
                    conversation_id=payload.get("conversation_id"),
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Isolation corpus vide",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.empty_corpus_id,
                    question=question,
                )
            )

    def test_streaming(self) -> None:
        self.test_streaming_normal()
        self.test_streaming_fallback()

    def test_streaming_normal(self) -> None:
        question = "Quel est le tarif annuel de l'offre Premium FormDev RAG ?"

        body = {
            "client_id": self.client_id,
            "corpus_id": self.premium_corpus_id,
            "conversation_id": None,
            "question": question,
            "top_k": 5,
            "temperature": 0.2,
            "max_tokens": 512,
        }

        start = time.time()

        try:
            status, raw, events = self.post_stream(body)

            event_names = [event["event"] for event in events]
            token_text = "".join(
                (event.get("data") or {}).get("content", "")
                for event in events
                if event.get("event") == "token" and isinstance(event.get("data"), dict)
            )

            sources_event = next((event for event in events if event["event"] == "sources"), None)
            done_event = next((event for event in events if event["event"] == "done"), None)

            sources = []
            if sources_event and isinstance(sources_event.get("data"), dict):
                sources = sources_event["data"].get("sources") or []

            done_data = done_event.get("data") if done_event else {}
            fallback = done_data.get("fallback") if isinstance(done_data, dict) else None

            ok = (
                status == 200
                and "metadata" in event_names
                and "token" in event_names
                and "sources" in event_names
                and "done" in event_names
                and len(sources) >= 1
                and fallback is False
            )

            self.add_case(
                BenchmarkCase(
                    name="Streaming SSE — réponse normale",
                    status="PASS" if ok else "WARN",
                    details=f"Events: {event_names}, sources={len(sources)}, fallback={fallback}",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                    answer=token_text,
                    sources_count=len(sources),
                    fallback=fallback,
                    raw={
                        "events": events,
                        "raw_preview": raw[:1000],
                    },
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Streaming SSE — réponse normale",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                )
            )

    def test_streaming_fallback(self) -> None:
        question = "Quelle est la recette exacte du kouign-amann selon les documents importés ?"

        body = {
            "client_id": self.client_id,
            "corpus_id": self.premium_corpus_id,
            "conversation_id": None,
            "question": question,
            "top_k": 5,
            "temperature": 0.2,
            "max_tokens": 512,
        }

        start = time.time()

        try:
            status, raw, events = self.post_stream(body)

            event_names = [event["event"] for event in events]

            sources_event = next((event for event in events if event["event"] == "sources"), None)
            done_event = next((event for event in events if event["event"] == "done"), None)

            sources = []
            if sources_event and isinstance(sources_event.get("data"), dict):
                sources = sources_event["data"].get("sources") or []

            done_data = done_event.get("data") if done_event else {}
            fallback = done_data.get("fallback") if isinstance(done_data, dict) else None

            ok = (
                status == 200
                and "metadata" in event_names
                and "token" in event_names
                and "sources" in event_names
                and "done" in event_names
                and len(sources) == 0
                and fallback is True
            )

            self.add_case(
                BenchmarkCase(
                    name="Streaming SSE — fallback hors contexte",
                    status="PASS" if ok else "WARN",
                    details=f"Events: {event_names}, sources={len(sources)}, fallback={fallback}",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                    sources_count=len(sources),
                    fallback=fallback,
                    raw={
                        "events": events,
                        "raw_preview": raw[:1000],
                    },
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Streaming SSE — fallback hors contexte",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.premium_corpus_id,
                    question=question,
                )
            )

    def test_optional_url_ingestion(self) -> None:
        if not self.url:
            self.add_case(
                BenchmarkCase(
                    name="Ingestion URL optionnelle",
                    status="WARN",
                    details="Aucune URL fournie. Test URL ignoré. Utiliser --url pour l'activer.",
                    corpus_id=self.url_corpus_id,
                )
            )
            return

        if not self.url_question:
            self.add_case(
                BenchmarkCase(
                    name="Ingestion URL optionnelle",
                    status="WARN",
                    details="URL fournie mais aucune --url-question. Test URL ignoré.",
                    corpus_id=self.url_corpus_id,
                )
            )
            return

        job_id = None
        source_id = None

        body = {
            "client_id": self.client_id,
            "corpus_id": self.url_corpus_id,
            "url": self.url,
            "source_name": f"URL benchmark {self.run_id}",
            "metadata": {
                "origin": "rag_benchmark",
                "run_id": self.run_id,
            },
        }

        start = time.time()

        try:
            _, payload = self.request_json(
                "POST",
                "/rag/sources/url/ingest-async",
                body=body,
            )

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse URL ingest invalide: {payload}")

            job_id = payload.get("job_id")
            source_id = payload.get("source_id")

            if not job_id:
                raise RuntimeError(f"job_id absent dans la réponse: {payload}")

            self.add_case(
                BenchmarkCase(
                    name="Création job ingestion URL",
                    status="PASS",
                    details=f"Job créé: {job_id}, source: {source_id}",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.url_corpus_id,
                    job_id=job_id,
                    source_id=source_id,
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Création job ingestion URL",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.url_corpus_id,
                )
            )
            return

        start = time.time()

        try:
            job_payload = self.wait_job(job_id)
            succeeded = job_payload.get("status") == "succeeded"

            self.add_case(
                BenchmarkCase(
                    name="Job ingestion URL",
                    status="PASS" if succeeded else "FAIL",
                    details=f"Status job: {job_payload.get('status')}",
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.url_corpus_id,
                    job_id=job_id,
                    source_id=source_id,
                    raw=job_payload,
                )
            )

            if not succeeded:
                return
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Job ingestion URL",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.url_corpus_id,
                    job_id=job_id,
                    source_id=source_id,
                )
            )
            return

        question = self.url_question

        body = {
            "client_id": self.client_id,
            "corpus_id": self.url_corpus_id,
            "conversation_id": None,
            "question": question,
            "top_k": 5,
            "score_threshold": None,
            "temperature": 0.2,
            "max_tokens": 700,
        }

        start = time.time()

        try:
            _, payload = self.request_json("POST", "/rag/chat", body=body)

            if not isinstance(payload, dict):
                raise RuntimeError(f"Réponse chat URL invalide: {payload}")

            answer = payload.get("answer") or ""
            sources = payload.get("sources") or []

            expected_ok = True
            if self.url_expected:
                expected_ok = self.url_expected.lower() in answer.lower()

            ok = len(sources) >= 1 and expected_ok

            self.add_case(
                BenchmarkCase(
                    name="Chat après ingestion URL",
                    status="PASS" if ok else "WARN",
                    details=(
                        "Le RAG répond avec source depuis l'URL."
                        if ok
                        else "Réponse URL incertaine: source absente ou contenu attendu non retrouvé."
                    ),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.url_corpus_id,
                    question=question,
                    answer=answer,
                    sources_count=len(sources),
                    top_score=payload.get("top_score"),
                    retrieval_confidence=payload.get("retrieval_confidence"),
                    fallback=len(sources) == 0,
                    conversation_id=payload.get("conversation_id"),
                    source_id=source_id,
                    raw=payload,
                )
            )
        except Exception as exc:
            self.add_case(
                BenchmarkCase(
                    name="Chat après ingestion URL",
                    status="FAIL",
                    details=str(exc),
                    latency_ms=self.elapsed_ms(start),
                    corpus_id=self.url_corpus_id,
                    question=question,
                    source_id=source_id,
                )
            )

    def create_premium_demo_file(self) -> Path:
        content = """Documentation commerciale FormDev — Offre Premium RAG

L'offre Premium FormDev RAG coûte 1290 euros par an.

Elle inclut :
- l'accès au chatbot documentaire RAG ;
- l'ingestion de documents PDF, DOCX et TXT ;
- l'ingestion de pages web par URL ;
- la recherche vectorielle dans les corpus documentaires ;
- les réponses sourcées ;
- l'historique conversationnel ;
- le streaming des réponses en temps réel.

Cette offre est destinée aux clients qui souhaitent intégrer un assistant documentaire dans leur CRM.
"""

        path = Path(tempfile.gettempdir()) / f"formdev_rag_premium_demo_{self.run_id}.txt"
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def is_fallback_response(payload: dict[str, Any]) -> bool:
        sources = payload.get("sources") or []
        answer = (payload.get("answer") or "").lower()
        used_chunks_count = payload.get("used_chunks_count", 0)
        retrieval_confidence = payload.get("retrieval_confidence")
        filtered_chunks_count = payload.get("filtered_chunks_count", 0)

        fallback_markers = [
            "information suffisante",
            "pas trouvé d'information suffisamment pertinente",
            "documents indexés",
            "documents fournis",
        ]

        has_fallback_text = any(marker in answer for marker in fallback_markers)

        return (
            len(sources) == 0
            and used_chunks_count == 0
            and filtered_chunks_count == 0
            and retrieval_confidence in {"none", "low"}
            and has_fallback_text
        )
    @staticmethod
    def elapsed_ms(start: float) -> int:
        return int((time.time() - start) * 1000)


def write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = report["run_id"]

    json_path = output_dir / f"rag_benchmark_{run_id}.json"
    csv_path = output_dir / f"rag_benchmark_{run_id}.csv"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fieldnames = [
        "name",
        "status",
        "details",
        "latency_ms",
        "corpus_id",
        "question",
        "answer",
        "sources_count",
        "top_score",
        "retrieval_confidence",
        "fallback",
        "conversation_id",
        "job_id",
        "source_id",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for case in report["cases"]:
            row = {field: case.get(field) for field in fieldnames}
            writer.writerow(row)

    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark réel du module RAG FormDev")

    parser.add_argument("--base-url", default="http://localhost:8081")
    parser.add_argument("--api-key", default=os.environ.get("API_KEY"))
    parser.add_argument("--client-id", default="client_demo")
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--job-timeout", type=int, default=90)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--output-dir", default="reports")

    parser.add_argument("--url", default=None, help="URL optionnelle à ingérer et tester")
    parser.add_argument("--url-question", default=None, help="Question à poser sur l'URL ingérée")
    parser.add_argument("--url-expected", default=None, help="Texte attendu dans la réponse URL")

    args = parser.parse_args()

    if not args.api_key:
        parser.error("--api-key est requis ou variable API_KEY absente")

    return args


def main() -> int:
    args = parse_args()

    print("=== Benchmark RAG FormDev ===")
    print(f"Base URL  : {args.base_url}")
    print(f"Client ID : {args.client_id}")
    print(f"Run ID    : {args.run_id}")
    print()

    benchmark = RagBenchmark(
        base_url=args.base_url,
        api_key=args.api_key,
        client_id=args.client_id,
        run_id=args.run_id,
        timeout=args.timeout,
        job_timeout=args.job_timeout,
        poll_interval=args.poll_interval,
        url=args.url,
        url_question=args.url_question,
        url_expected=args.url_expected,
    )

    report = benchmark.run()
    json_path, csv_path = write_reports(report, Path(args.output_dir))

    print()
    print("=== Résumé ===")
    print(f"PASS: {report['summary']['PASS']}")
    print(f"WARN: {report['summary']['WARN']}")
    print(f"FAIL: {report['summary']['FAIL']}")
    print()
    print(f"Rapport JSON: {json_path}")
    print(f"Rapport CSV : {csv_path}")

    return 1 if report["summary"]["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
