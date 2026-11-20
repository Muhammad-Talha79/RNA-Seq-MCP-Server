import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.analysis import register_analysis_tools


class ToolRegistry:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class FakeNCBIClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


class DifferentialExpressionResearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        register_analysis_tools(self.registry)

    def test_researches_top_significant_genes_in_padj_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_path = Path(temp_dir) / "deseq2.csv"
            results_path.write_text(
                "gene_id,log2FoldChange,padj\n"
                "GENE_B,-2.0,0.02\n"
                "GENE_A,1.5,0.01\n"
                "GENE_C,4.0,0.2\n",
                encoding="utf-8",
            )
            requested_genes = []

            async def report(ncbi, gene_id, organism, max_papers):
                del ncbi, organism
                requested_genes.append((gene_id, max_papers))
                return f"Research for {gene_id}"

            with (
                patch("tools.analysis.NCBIClient", FakeNCBIClient),
                patch("tools.analysis.gene_research_report", side_effect=report),
            ):
                result = asyncio.run(
                    self.registry.tools["research_differential_expression_results"](
                        str(results_path),
                        top_n=2,
                    )
                )

        self.assertEqual(requested_genes, [("GENE_A", 2), ("GENE_B", 2)])
        self.assertIn("padj=0.01", result)
        self.assertIn("Research for GENE_A", result)
        self.assertNotIn("GENE_C", result)

    def test_rejects_missing_result_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_path = Path(temp_dir) / "invalid.csv"
            results_path.write_text("gene_id,log2FoldChange\nGENE_A,2\n", encoding="utf-8")

            result = asyncio.run(
                self.registry.tools["research_differential_expression_results"](
                    str(results_path)
                )
            )

        self.assertIn("missing columns", result)
