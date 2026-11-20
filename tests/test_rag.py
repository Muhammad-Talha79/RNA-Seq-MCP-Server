import sys
import asyncio
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from tools.rag import (
    DocumentImportError,
    _fetch_url_document,
    _get_collection,
    _read_local_document,
    _split_text,
    _validate_public_url,
    register_rag_tools,
)


class ToolRegistry:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class FakeCollection:
    def __init__(self) -> None:
        self.documents = {}
        self.deleted = []

    def get(self, where, include):
        del include
        ids = [
            item_id
            for item_id, item in self.documents.items()
            if item["metadata"]["source"] == where["source"]
        ]
        return {"ids": ids}

    def upsert(self, ids, documents, metadatas):
        for item_id, document, metadata in zip(ids, documents, metadatas):
            self.documents[item_id] = {"document": document, "metadata": metadata}

    def delete(self, ids):
        self.deleted.extend(ids)
        for item_id in ids:
            self.documents.pop(item_id, None)

    def query(self, query_texts, n_results, include):
        del query_texts, include
        items = list(self.documents.values())[:n_results]
        return {
            "documents": [[item["document"] for item in items]],
            "metadatas": [[item["metadata"] for item in items]],
        }


class RAGToolTests(unittest.TestCase):
    def test_collection_uses_persistent_local_chroma_without_telemetry(self) -> None:
        collection = Mock()
        client = Mock()
        client.get_or_create_collection.return_value = collection
        chromadb = types.ModuleType("chromadb")
        chromadb.__path__ = []
        setattr(chromadb, "PersistentClient", Mock(return_value=client))
        settings_module = types.ModuleType("chromadb.config")
        setattr(settings_module, "Settings", Mock(return_value="local-settings"))
        utils_module = types.ModuleType("chromadb.utils")
        utils_module.__path__ = []
        embedding_module = types.ModuleType("chromadb.utils.embedding_functions")
        setattr(
            embedding_module,
            "DefaultEmbeddingFunction",
            Mock(return_value="local-embeddings"),
        )
        modules = {
            "chromadb": chromadb,
            "chromadb.config": settings_module,
            "chromadb.utils": utils_module,
            "chromadb.utils.embedding_functions": embedding_module,
        }

        with patch.dict(sys.modules, modules):
            result = _get_collection()

        self.assertIs(result, collection)
        chromadb.PersistentClient.assert_called_once()
        self.assertFalse(settings_module.Settings.call_args.kwargs["anonymized_telemetry"])
        client.get_or_create_collection.assert_called_once_with(
            name="bioinformatics_knowledge",
            metadata={"hnsw:space": "cosine"},
            embedding_function="local-embeddings",
        )

    def test_reads_supported_local_document_and_rejects_raw_fastq(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            text_path = Path(temp_dir) / "notes.md"
            text_path.write_text("# TP53\nTumor suppressor.", encoding="utf-8")
            fastq_path = Path(temp_dir) / "reads.fastq"
            fastq_path.write_text("@read\nACGT\n+\n!!!!\n", encoding="utf-8")

            content, source = _read_local_document(str(text_path))
            self.assertEqual(source, "notes.md")
            self.assertIn("Tumor suppressor.", content)
            with self.assertRaises(DocumentImportError):
                _read_local_document(str(fastq_path))

    def test_public_url_import_extracts_html_and_strips_tracking_parameters(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><script>ignore this</script><p>TP53 is studied.</p></html>",
            )

        async def run() -> tuple[str, str]:
            with patch("tools.rag._validate_public_url", side_effect=lambda url: url):
                return await _fetch_url_document(
                    "https://example.org/paper?access_key=hidden",
                    transport=httpx.MockTransport(respond),
                )

        with self.assertLogs("httpx", level="INFO") as request_logs:
            content, source = asyncio.run(run())
        self.assertIn("TP53 is studied.", content)
        self.assertNotIn("ignore this", content)
        self.assertNotIn("access_key=hidden", "\n".join(request_logs.output))
        self.assertEqual(source, "https://example.org/paper")

    def test_public_url_guard_rejects_local_and_non_http_targets(self) -> None:
        for url in (
            "file:///etc/passwd",
            "http://127.0.0.1/private",
            "http://localhost/private",
            "https://user:pass@example.org/document",
        ):
            with self.subTest(url=url):
                with self.assertRaises(DocumentImportError):
                    _validate_public_url(url)

    def test_redirect_to_private_address_is_rejected(self) -> None:
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                302,
                headers={"location": "http://127.0.0.1/private"},
            )

        def validate(url: str) -> str:
            if "example.org" in url:
                return url
            return _validate_public_url(url)

        async def run() -> None:
            with patch("tools.rag._validate_public_url", side_effect=validate):
                await _fetch_url_document(
                    "https://example.org/redirect",
                    transport=httpx.MockTransport(respond),
                )

        with self.assertRaises(DocumentImportError):
            asyncio.run(run())
        self.assertEqual(len(requests), 1)

    def test_remote_document_size_is_bounded(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="x" * 2_000_001,
            )

        async def run() -> None:
            with patch("tools.rag._validate_public_url", side_effect=lambda url: url):
                await _fetch_url_document(
                    "https://example.org/large.txt",
                    transport=httpx.MockTransport(respond),
                )

        with self.assertRaises(DocumentImportError):
            asyncio.run(run())

    def test_document_import_requires_exactly_one_location(self) -> None:
        registry = ToolRegistry()
        register_rag_tools(registry)

        result = asyncio.run(registry.tools["import_bioinformatics_document"]())

        self.assertIn("exactly one", result)

    def test_split_text_bounds_chunks_and_overlaps(self) -> None:
        text = "x" * 3000
        chunks = _split_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1200 for chunk in chunks))
        self.assertEqual(chunks[0][-150:], chunks[1][:150])

    def test_empty_or_oversized_documents_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _split_text(" \n ")
        with self.assertRaises(ValueError):
            _split_text("a" * 100_001)

    def test_index_replaces_stale_chunks_and_search_returns_citations(self) -> None:
        registry = ToolRegistry()
        register_rag_tools(registry)
        collection = FakeCollection()
        with patch("tools.rag._get_collection", return_value=collection):
            first = registry.tools["index_bioinformatics_document"](
                "TP53 is a tumor suppressor. " * 100, "PMID:123"
            )
            second = registry.tools["index_bioinformatics_document"](
                "TP53 regulates cell growth.", "PMID:123"
            )
            result = registry.tools["search_bioinformatics_knowledge"]("TP53", 1)

        self.assertIn("Indexed", first)
        self.assertIn("Indexed 1 passage", second)
        self.assertTrue(collection.deleted)
        self.assertIn("PMID:123", result)
        self.assertIn("TP53 regulates cell growth.", result)

    def test_search_rejects_invalid_limits_without_accessing_store(self) -> None:
        registry = ToolRegistry()
        register_rag_tools(registry)
        with patch("tools.rag._get_collection") as get_collection:
            result = registry.tools["search_bioinformatics_knowledge"]("gene", 99)

        self.assertIn("Validation Error", result)
        get_collection.assert_not_called()
