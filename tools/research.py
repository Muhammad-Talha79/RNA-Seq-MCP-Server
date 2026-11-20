import asyncio
import json
import os
import re
import time
from typing import Any

import httpx

from utils import configure_httpx_log_redaction


_EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_GENE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_ORGANISM = re.compile(r"[A-Za-z][A-Za-z0-9 ._-]{0,79}\Z")
_SEQUENCE_ACCESSION = re.compile(r"[A-Za-z]{1,6}_?\d{3,12}(?:\.\d{1,4})?\Z")
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_SEQUENCE_BASES = 20_000


class NCBIResponseError(ValueError):
    """Raised when NCBI returns a response that cannot be safely used."""


class NCBIClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        configure_httpx_log_redaction()
        self._owns_client = http_client is None
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._minimum_request_interval = (
            0.11 if os.environ.get("NCBI_API_KEY", "").strip() else 0.34
        )
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={"User-Agent": "RNASeq-MCP-Server/1.0 (NCBI E-utilities client)"},
        )

    async def __aenter__(self) -> "NCBIClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._http.aclose()

    def _with_api_credentials(self, params: dict[str, str]) -> dict[str, str]:
        email = os.environ.get("NCBI_EMAIL", "").strip()
        api_key = os.environ.get("NCBI_API_KEY", "").strip()
        if email:
            params["email"] = email
        if api_key:
            params["api_key"] = api_key
        return params

    async def _get_text(self, endpoint: str, params: dict[str, str]) -> str:
        url = f"{_EUTILS_URL}/{endpoint}"
        async with self._request_lock:
            delay = self._minimum_request_interval - (
                time.monotonic() - self._last_request_at
            )
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_at = time.monotonic()
            async with self._http.stream(
                "GET", url, params=self._with_api_credentials(params)
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_RESPONSE_BYTES:
                        raise NCBIResponseError("NCBI response exceeded the size limit.")
                try:
                    return bytes(body).decode(response.encoding or "utf-8")
                except UnicodeDecodeError as error:
                    raise NCBIResponseError("NCBI returned invalid text encoding.") from error

    async def get_json(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        text = await self._get_text(endpoint, params)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise NCBIResponseError("NCBI returned invalid JSON.") from error
        if not isinstance(payload, dict):
            raise NCBIResponseError("NCBI returned an unexpected response.")
        return payload

    async def find_gene(self, identifier: str, organism: str) -> dict[str, Any] | None:
        search_field = (
            "GeneID"
            if identifier.isdigit()
            else "All Fields"
            if identifier.upper().startswith("ENS")
            else "Gene Name"
        )
        query = f'"{identifier}"[{search_field}] AND "{organism}"[Organism]'
        search = await self.get_json(
            "esearch.fcgi",
            {"db": "gene", "term": query, "retmode": "json", "retmax": "1"},
        )
        result = search.get("esearchresult")
        identifiers = result.get("idlist") if isinstance(result, dict) else None
        if not isinstance(identifiers, list) or not identifiers:
            return None
        if not isinstance(identifiers[0], str) or not identifiers[0].isdigit():
            raise NCBIResponseError("NCBI returned an invalid gene identifier.")

        summary = await self.get_json(
            "esummary.fcgi",
            {
                "db": "gene",
                "id": identifiers[0],
                "retmode": "json",
            },
        )
        records = summary.get("result")
        if not isinstance(records, dict):
            raise NCBIResponseError("NCBI returned an unexpected gene summary.")
        record = records.get(identifiers[0])
        if not isinstance(record, dict):
            raise NCBIResponseError("NCBI returned no summary for the matching gene.")
        return record

    async def find_papers(
        self, identifier: str, organism: str, max_papers: int
    ) -> list[dict[str, str]]:
        query = f'"{identifier}" AND "{organism}"[Organism]'
        search = await self.get_json(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": str(max_papers),
                "sort": "relevance",
            },
        )
        result = search.get("esearchresult")
        identifiers = result.get("idlist") if isinstance(result, dict) else None
        if not isinstance(identifiers, list) or not identifiers:
            return []
        if any(
            not isinstance(item, str) or not item.isdigit()
            for item in identifiers[:max_papers]
        ):
            raise NCBIResponseError("NCBI returned an invalid publication identifier.")

        summary = await self.get_json(
            "esummary.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(str(item) for item in identifiers[:max_papers]),
                "retmode": "json",
            },
        )
        records = summary.get("result")
        if not isinstance(records, dict):
            raise NCBIResponseError("NCBI returned an unexpected publication summary.")

        papers: list[dict[str, str]] = []
        for pmid in identifiers[:max_papers]:
            record = records.get(pmid)
            if not isinstance(record, dict):
                continue
            title = record.get("title")
            papers.append(
                {
                    "pmid": pmid,
                    "title": (
                        title.strip()[:500]
                        if isinstance(title, str)
                        else "Title unavailable"
                    ),
                    "journal": str(record.get("fulljournalname", "Journal unavailable"))[:200],
                    "date": str(record.get("pubdate", "Date unavailable"))[:40],
                }
            )
        return papers

    async def fetch_fasta(self, accession: str, max_bases: int) -> str:
        return await self._get_text(
            "efetch.fcgi",
            {
                "db": "nuccore",
                "id": accession,
                "rettype": "fasta",
                "retmode": "text",
                "seq_start": "1",
                "seq_stop": str(max_bases),
            },
        )


async def gene_research_report(
    ncbi: NCBIClient,
    identifier: str,
    organism: str,
    max_papers: int = 5,
) -> str:
    gene = await ncbi.find_gene(identifier, organism)
    if gene is None:
        return f"No NCBI Gene record found for {identifier} in {organism}."
    papers = await ncbi.find_papers(identifier, organism, max_papers)

    gene_id = str(gene.get("uid", ""))
    name = str(gene.get("name", identifier))[:200]
    description = str(gene.get("description", "Description unavailable"))[:500]
    summary = str(gene.get("summary", "")).strip() or "No curated summary is available."
    lines = [
        f"## {name} ({organism})",
        f"- NCBI Gene ID: {gene_id or 'Unavailable'}",
        f"- Description: {description}",
        f"- Summary: {summary[:1500]}",
    ]
    if gene_id:
        lines.append(f"- NCBI source: https://www.ncbi.nlm.nih.gov/gene/{gene_id}")
    lines.append("\n### PubMed references")
    if papers:
        for paper in papers:
            lines.append(
                f"- {paper['title']} ({paper['journal']}, {paper['date']}; "
                f"PMID: {paper['pmid']}) https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/"
            )
    else:
        lines.append("No matching PubMed references were returned.")
    lines.append(
        "\nThese database annotations and citations provide research context; "
        "they do not establish causality or explain a specific experiment."
    )
    return "\n".join(lines)


def register_research_tools(mcp: Any) -> None:
    @mcp.tool()
    async def research_gene(
        gene_identifier: str,
        organism: str = "Homo sapiens",
        max_papers: int = 5,
    ) -> str:
        """Find an NCBI Gene record and relevant PubMed citations.

        Use this after a differential-expression summary to provide sourced
        context for a gene. Results describe database annotations and papers;
        they do not establish that a gene caused an observed phenotype.

        Args:
            gene_identifier: Gene symbol such as TP53 or a NCBI Gene symbol.
            organism: Scientific organism name, defaulting to Homo sapiens.
            max_papers: Maximum number of PubMed citations to return (1–10).
        """
        identifier = gene_identifier.strip()
        organism_name = organism.strip()
        if not _GENE_IDENTIFIER.fullmatch(identifier):
            return "❌ Validation Error: gene_identifier must be 1–64 letters, digits, dots, underscores, or hyphens."
        if not _ORGANISM.fullmatch(organism_name):
            return "❌ Validation Error: organism must be a plain scientific name of at most 80 characters."
        if not 1 <= max_papers <= 10:
            return "❌ Validation Error: max_papers must be between 1 and 10."

        try:
            async with NCBIClient() as ncbi:
                return await gene_research_report(
                    ncbi, identifier, organism_name, max_papers
                )
        except httpx.HTTPStatusError as error:
            return f"❌ NCBI returned HTTP {error.response.status_code}; retry later."
        except httpx.TimeoutException:
            return "❌ NCBI request timed out; retry later."
        except (httpx.RequestError, NCBIResponseError):
            return "❌ NCBI could not be reached or returned an invalid response; retry later."

    @mcp.tool()
    async def fetch_sequence_fasta(
        accession: str,
        max_bases: int = 5000,
    ) -> str:
        """Retrieve a bounded nucleotide FASTA sequence from NCBI nuccore.

        Args:
            accession: NCBI nucleotide accession, optionally with a version (for example NM_000546.6).
            max_bases: Maximum number of bases to return (1–20,000).
        """
        sequence_accession = accession.strip()
        if not _SEQUENCE_ACCESSION.fullmatch(sequence_accession):
            return "❌ Validation Error: provide a valid NCBI nucleotide accession, optionally with a version."
        if not 1 <= max_bases <= _MAX_SEQUENCE_BASES:
            return f"❌ Validation Error: max_bases must be between 1 and {_MAX_SEQUENCE_BASES}."
        try:
            async with NCBIClient() as ncbi:
                fasta = await ncbi.fetch_fasta(sequence_accession, max_bases)
        except httpx.HTTPStatusError as error:
            return f"❌ NCBI returned HTTP {error.response.status_code}; retry later."
        except httpx.TimeoutException:
            return "❌ NCBI request timed out; retry later."
        except (httpx.RequestError, NCBIResponseError):
            return "❌ NCBI could not be reached or returned an invalid response; retry later."

        fasta = fasta.strip()
        if not fasta.startswith(">"):
            return f"No nucleotide FASTA record found for accession {sequence_accession}."
        return fasta
