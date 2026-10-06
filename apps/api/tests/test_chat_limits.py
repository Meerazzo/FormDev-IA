"""Regression Chat : vLLM simule, SQLite en memoire, aucune ecriture DB."""
import importlib
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

# Variables limitees a ce processus de test ; aucun .env n'est modifie.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["API_KEYS"] = "chat-test:chat-test-key"
os.environ["GRAYLOG_ENABLED"] = "false"

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

routes = importlib.import_module("routers.chat.routes")
from schemas.chat import CHAT_MAX_MESSAGES, CHAT_MAX_TEXT_CHARS
from services.vllm_client import VLLMClient, VLLMConnectionError, VLLMUpstreamError

CONTEXT_MESSAGE = (
    "You passed 7193 input tokens and requested 1000 output tokens. "
    "However, the model's context length is only 8192 tokens, "
    "resulting in a maximum input length of 7192 tokens. "
    "Please reduce the length of the input prompt."
)


def error_body(message=CONTEXT_MESSAGE):
    return json.dumps({"error": {
        "message": message, "type": "BadRequestError",
        "param": "input_tokens", "code": 400,
    }})


def completion(text="Bonjour", finish="stop"):
    return {
        "model": "test-model",
        "choices": [{"message": {"role": "assistant", "content": text},
                     "finish_reason": finish}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


class ChatLimitsTests(unittest.TestCase):
    def setUp(self):
        def patched(target, name, **kwargs):
            patcher = patch.object(target, name, **kwargs)
            value = patcher.start()
            self.addCleanup(patcher.stop)
            return value

        patched(routes.limiter, "enabled", new=False)
        self.upstream = patched(
            routes.vllm, "chat_completions", new_callable=AsyncMock,
        )
        self.upstream.return_value = completion()
        self.success = patched(routes, "log_ai_interaction_success")
        self.error = patched(routes, "log_ai_interaction_error")
        app = FastAPI()
        app.state.limiter = routes.limiter
        app.include_router(routes.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def request(self, **changes):
        payload = {"messages": [{"role": "user", "content": "Bonjour"}]}
        payload.update(changes)
        return self.client.post(
            "/v1/chat", json=payload, headers={"X-API-Key": "chat-test-key"},
        )

    def test_normal_request(self):
        response = self.request()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["content"], "Bonjour")
        self.assertEqual(response.json()["usage"]["total_tokens"], 12)
        self.upstream.assert_awaited_once()
        sent = self.upstream.await_args.args[0]
        self.assertEqual(set(sent), {"messages", "max_tokens", "temperature", "top_p"})
        self.assertEqual(sent["messages"][0]["role"], "system")

    def test_long_prompts_and_whitelist_on_all_three_calls(self):
        system = "s" * 5001
        correction = "c" * 5001
        self.upstream.side_effect = [
            completion("Debut", "length"), completion("fin"), completion("Corrige"),
        ]
        response = self.request(
            model="test-model", system_prompt=system,
            post_correction_prompt=correction, post_correction=True,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["content"], "Corrige")
        calls = [call.args[0] for call in self.upstream.await_args_list]
        self.assertEqual(len(calls), 3)
        for sent in calls:
            self.assertEqual(set(sent), {
                "model", "messages", "max_tokens", "temperature", "top_p",
            })
            for key in ("system_prompt", "post_correction_prompt", "post_correction"):
                self.assertNotIn(key, sent)
        self.assertEqual(calls[0]["messages"][0]["content"], system)
        self.assertEqual(calls[1]["messages"][0]["content"], system)
        self.assertEqual(calls[1]["max_tokens"], 150)
        self.assertEqual(calls[2]["messages"][0]["content"], correction)
        self.assertIn("Debut fin", calls[2]["messages"][1]["content"])

    def test_long_unused_correction_prompt_is_accepted(self):
        response = self.request(post_correction_prompt="c" * 5001)
        self.assertEqual(response.status_code, 200, response.text)
        self.upstream.assert_awaited_once()
        self.assertNotIn("post_correction_prompt", self.upstream.await_args.args[0])

    def test_safety_limit_boundary(self):
        response = self.request(
            messages=[{"role": "user", "content": "x" * CHAT_MAX_TEXT_CHARS}],
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_excessive_payloads_do_not_call_vllm(self):
        cases = [
            {"messages": [{"role": "user", "content": "x" * 60000}] * 2},
            {"messages": [{"role": "user", "content": "x"}] * (CHAT_MAX_MESSAGES + 1)},
            {"system_prompt": "x" * (CHAT_MAX_TEXT_CHARS + 1)},
            {"post_correction_prompt": "x" * (CHAT_MAX_TEXT_CHARS + 1)},
            {"system_prompt": "s" * 50000, "post_correction_prompt": "c" * 50000},
            {"max_tokens": 0},
            {"max_tokens": 1025},
        ]
        for changes in cases:
            with self.subTest(changes=list(changes)):
                self.assertEqual(self.request(**changes).status_code, 422)
        self.upstream.assert_not_awaited()

    def test_context_overflow_at_every_phase(self):
        cases = [
            ("generation", [], False),
            ("continuation", [completion("Debut", "length")], False),
            ("correction", [completion()], True),
            ("correction_after_continuation",
             [completion("Debut", "length"), completion("fin")], True),
        ]
        for phase, previous, correction in cases:
            with self.subTest(phase=phase):
                self.upstream.reset_mock()
                self.success.reset_mock()
                self.error.reset_mock()
                self.upstream.side_effect = previous + [
                    VLLMUpstreamError(400, error_body()),
                ]
                response = self.request(post_correction=correction)
                self.assertEqual(response.status_code, 422, response.text)
                detail = response.json()["detail"]
                self.assertEqual(detail["code"], "context_too_long")
                self.assertIn("max_tokens", detail["message"])
                self.assertIn("historique", detail["message"])
                self.assertNotIn("7193", response.text)
                self.assertNotIn("Traceback", response.text)
                self.assertEqual(self.upstream.await_count, len(previous) + 1)
                self.success.assert_not_called()
                self.error.assert_called_once()
                self.assertEqual(self.error.call_args.kwargs["status_code"], 422)
                self.assertEqual(
                    self.error.call_args.kwargs["error_type"], "context_too_long",
                )

    def test_other_vllm_context_messages(self):
        messages = [
            "You passed 99999 input characters and requested 1000 output tokens. "
            "However, the model's context length is only 8192 tokens, "
            "resulting in a maximum input length of 7192 tokens "
            "(at most 50000 characters).",
            "This model's maximum context length is 8192 tokens. "
            "However, your request has 8193 input tokens.",
            "'max_tokens' or 'max_completion_tokens' is too large: 1000. "
            "This model's maximum context length is 8192 tokens "
            "and your request has 7193 input tokens (1000 > 8192 - 7193).",
        ]
        for message in messages:
            with self.subTest(message=message):
                self.upstream.side_effect = VLLMUpstreamError(400, error_body(message))
                response = self.request()
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"]["code"], "context_too_long")

    def test_other_upstream_errors_remain_502(self):
        cases = [
            (400, error_body("temperature must be between 0 and 2")),
            (400, error_body("invalid context length configuration")),
            (400, "not JSON"),
            (400, "[]"),
            (400, '{"error": null}'),
            (400, '{"error": {"message": 42}}'),
            (400, json.dumps({"messages": [{"content": CONTEXT_MESSAGE}]})),
            (404, error_body()),
            (500, error_body()),
        ]
        for status, body in cases:
            with self.subTest(status=status, body=body):
                self.upstream.side_effect = VLLMUpstreamError(status, body)
                response = self.request()
                self.assertEqual(response.status_code, 502, response.text)
                self.assertEqual(
                    response.json()["detail"], f"vLLM upstream error ({status})",
                )
                self.assertEqual(self.error.call_args.kwargs["status_code"], 502)

    def test_network_failures_remain_502(self):
        for exception in (VLLMConnectionError("offline"), TimeoutError("timeout")):
            with self.subTest(exception=type(exception).__name__):
                self.upstream.side_effect = exception
                self.assertEqual(self.request().status_code, 502)


class VLLMTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_error_preserves_status_and_body(self):
        for status in (400, 500):
            with self.subTest(status=status):
                body = error_body()
                with patch("services.vllm_client.httpx.AsyncClient") as factory:
                    client = factory.return_value.__aenter__.return_value
                    client.post = AsyncMock(return_value=httpx.Response(status, text=body))
                    with self.assertRaises(VLLMUpstreamError) as caught:
                        await VLLMClient().chat_completions({"messages": []})
                    self.assertEqual(caught.exception.status_code, status)
                    self.assertEqual(caught.exception.body, body)

    async def test_transport_exception_types(self):
        for original, expected in (
            (httpx.ConnectError("offline"), VLLMConnectionError),
            (httpx.ReadTimeout("timeout"), TimeoutError),
        ):
            with self.subTest(expected=expected.__name__):
                with patch("services.vllm_client.httpx.AsyncClient") as factory:
                    client = factory.return_value.__aenter__.return_value
                    client.post = AsyncMock(side_effect=original)
                    with self.assertRaises(expected):
                        await VLLMClient().chat_completions({"messages": []})


if __name__ == "__main__":
    unittest.main()
