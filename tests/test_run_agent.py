import asyncio
import io
import json
import os
import unittest
from unittest.mock import patch

import run_agent


class CloudModelTests(unittest.TestCase):
    def test_local_is_default_and_requires_no_cloud_secret(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(os.environ.get("MODEL_MODE", "local"), "local")
            with self.assertRaisesRegex(ValueError, "Cloud mode needs"):
                run_agent.cloud_model_settings()

    def test_groq_settings_are_selected_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "test-key", "CLOUD_PROVIDER": "groq"},
            clear=True,
        ):
            settings = run_agent.cloud_model_settings()

        self.assertEqual(settings.provider, "groq")
        self.assertEqual(settings.api_key, "test-key")
        self.assertTrue(settings.base_url.startswith("https://"))

    def test_compatible_provider_requires_https(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLOUD_PROVIDER": "compatible",
                "CLOUD_API_KEY": "test-key",
                "CLOUD_BASE_URL": "http://example.org/v1",
                "CLOUD_MODEL": "model",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                run_agent.cloud_model_settings()

    def test_hybrid_detects_live_search_and_current_information(self) -> None:
        self.assertTrue(run_agent.is_cloud_request("Please search the web for current papers"))
        self.assertTrue(run_agent.is_cloud_request("What are the latest developments?"))
        self.assertFalse(run_agent.is_cloud_request("Summarize this local DESeq2 file"))

    def test_only_tavily_key_is_forwarded_to_wsl_server(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PATH": "C:\\Windows\\System32",
                "TAVILY_API_KEY": "search-key",
                "GROQ_API_KEY": "cloud-model-key",
                "CLOUD_API_KEY": "compatible-model-key",
                "WSLENV": "EXISTING_FLAG/u",
            },
            clear=True,
        ):
            environment = run_agent._wsl_server_environment()

        self.assertEqual(environment["PATH"], "C:\\Windows\\System32")
        self.assertEqual(environment["TAVILY_API_KEY"], "search-key")
        self.assertEqual(environment["WSLENV"], "EXISTING_FLAG/u:TAVILY_API_KEY/u")
        self.assertNotIn("GROQ_API_KEY", environment)
        self.assertNotIn("CLOUD_API_KEY", environment)

    def test_openai_messages_preserve_tool_links_without_private_context_injection(self) -> None:
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "search public gene literature"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "web_search",
                            "arguments": {"query": "TP53 literature"},
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_name": "web_search",
                "tool_call_id": "call_1",
                "content": "public snippet",
            },
        ]

        converted = run_agent._cloud_messages(messages)

        self.assertEqual(converted[2]["tool_calls"][0]["function"]["arguments"],
                         '{"query": "TP53 literature"}')
        self.assertEqual(converted[3]["tool_call_id"], "call_1")
        self.assertNotIn("private file contents", json.dumps(converted))

    def test_cloud_chat_uses_secure_endpoint_and_normalizes_tool_calls(self) -> None:
        request_payloads = []

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 60)
            self.assertEqual(request.full_url, "https://api.example.test/v1/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer secret")
            request_payloads.append(json.loads(request.data))
            return FakeResponse(
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "function": {
                                                "name": "web_search",
                                                "arguments": '{"query":"gene"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ).encode("utf-8")
            )

        settings = run_agent.CloudModelSettings(
            "compatible", "secret", "https://api.example.test/v1", "test-model"
        )
        with patch("run_agent.urlopen", side_effect=fake_urlopen):
            result = run_agent.chat_with_cloud(
                [{"role": "user", "content": "search public gene information"}],
                [],
                settings,
            )

        self.assertEqual(
            result["message"]["tool_calls"][0]["function"]["arguments"],
            {"query": "gene"},
        )
        self.assertEqual(request_payloads[0]["model"], "test-model")
