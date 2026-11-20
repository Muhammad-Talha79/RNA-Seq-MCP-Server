import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from tools.research import NCBIClient, NCBIResponseError, register_research_tools


class ToolRegistry:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class ResearchToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        register_research_tools(self.registry)

    def test_rejects_malformed_gene_and_sequence_identifiers(self) -> None:
        gene_result = asyncio.run(
            self.registry.tools["research_gene"]("TP53\" OR *", "Homo sapiens")
        )
        sequence_result = asyncio.run(
            self.registry.tools["fetch_sequence_fasta"]("../../secret")
        )

        self.assertIn("Validation Error", gene_result)
        self.assertIn("Validation Error", sequence_result)

    def test_gene_and_literature_queries_use_bounded_ncbi_searches(self) -> None:
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            endpoint = request.url.path.rsplit("/", 1)[-1]
            params = request.url.params
            if endpoint == "esearch.fcgi" and params["db"] == "gene":
                payload = {"esearchresult": {"idlist": ["7157"]}}
            elif endpoint == "esummary.fcgi" and params["db"] == "gene":
                payload = {
                    "result": {
                        "7157": {
                            "uid": "7157",
                            "name": "TP53",
                            "description": "tumor protein p53",
                            "summary": "A tumor suppressor gene.",
                        }
                    }
                }
            elif endpoint == "esearch.fcgi":
                payload = {"esearchresult": {"idlist": ["12345678"]}}
            else:
                payload = {
                    "result": {
                        "12345678": {
                            "title": "TP53 research",
                            "fulljournalname": "Example Journal",
                            "pubdate": "2025",
                        }
                    }
                }
            return httpx.Response(200, json=payload)

        async def run() -> tuple[dict, list[dict[str, str]]]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
                async with NCBIClient(http) as ncbi:
                    gene = await ncbi.find_gene("TP53", "Homo sapiens")
                    papers = await ncbi.find_papers("TP53", "Homo sapiens", 2)
                    assert gene is not None
                    return gene, papers

        with patch.dict(os.environ, {"NCBI_API_KEY": "unit-test-key"}):
            with self.assertLogs("httpx", level="INFO") as request_logs:
                gene, papers = asyncio.run(run())
        self.assertEqual(gene["uid"], "7157")
        self.assertEqual(papers[0]["pmid"], "12345678")
        self.assertTrue(all(request.url.host == "eutils.ncbi.nlm.nih.gov" for request in requests))
        self.assertTrue(all(request.url.params["retmode"] == "json" for request in requests))
        self.assertEqual(requests[0].url.params["api_key"], "unit-test-key")
        self.assertNotIn("unit-test-key", "\n".join(request_logs.output))

    def test_sequence_fetch_is_limited_to_requested_bases(self) -> None:
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, text=">NM_000546.6\nACGT")

        async def run() -> str:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
                async with NCBIClient(http) as ncbi:
                    return await ncbi.fetch_fasta("NM_000546.6", 4)

        self.assertIn("ACGT", asyncio.run(run()))
        self.assertEqual(requests[0].url.params["seq_stop"], "4")
        self.assertEqual(requests[0].url.params["db"], "nuccore")

    def test_ncbi_response_size_is_bounded(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(200, text="x" * 2_000_001)

        async def run() -> None:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
                async with NCBIClient(http) as ncbi:
                    await ncbi.get_json("esearch.fcgi", {"db": "gene"})

        with self.assertRaises(NCBIResponseError):
            asyncio.run(run())
