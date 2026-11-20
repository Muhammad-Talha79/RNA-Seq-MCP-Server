import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from tools.web_search import _search_tavily, register_web_search_tool


class ToolRegistry:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class WebSearchTests(unittest.TestCase):
    def test_search_sends_key_in_body_and_bounds_public_results(self) -> None:
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Bioinformatics study",
                            "url": "https://example.org/study",
                            "content": "Relevant result.",
                        },
                        {
                            "title": "Unsupported",
                            "url": "javascript:alert(1)",
                            "content": "Should not be returned.",
                        },
                    ]
                },
            )

        async def run():
            return await _search_tavily(
                "RNA-seq methods",
                5,
                transport=httpx.MockTransport(respond),
            )

        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            results = asyncio.run(run())

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.org/study")
        self.assertEqual(requests[0].url.host, "api.tavily.com")
        self.assertEqual(requests[0].headers["content-type"], "application/json")
        self.assertIn(b'"api_key":"test-key"', requests[0].content)
        self.assertNotIn("test-key", requests[0].url.query.decode("utf-8"))

    def test_requires_api_key_without_network_request(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TAVILY_API_KEY"):
                asyncio.run(_search_tavily("public query", 2))

    def test_mcp_tool_validates_query_and_result_limit(self) -> None:
        registry = ToolRegistry()
        register_web_search_tool(registry)

        empty_query = asyncio.run(registry.tools["web_search"]("  "))
        invalid_limit = asyncio.run(registry.tools["web_search"]("gene", 99))

        self.assertIn("Validation Error", empty_query)
        self.assertIn("Validation Error", invalid_limit)
