# RNA-Seq Bioinformatic MCP Server

This project is an MCP (Model Context Protocol) server. It provides RNA-seq
quality-control, quantification, and result-analysis tools to an MCP-compatible
AI client; it is not a standalone desktop application.

It also provides cited gene and literature research, bounded NCBI nucleotide
FASTA retrieval, and local retrieval-augmented generation (RAG) over documents
you choose to index.

## Setup on Windows with WSL

The pipeline tools are installed in Ubuntu on WSL, so the MCP server must also
run there. This keeps Python, FastQC, Salmon, and Java in one environment.

1. In PowerShell, open Ubuntu:

   ```powershell
   wsl -d Ubuntu
   ```

2. In the Ubuntu terminal, create the environment once. If it already exists,
   skip the `create` command and run the `install` command instead:

   Replace the placeholder on the `cd` line with this repository's WSL path.

   ```bash
   mkdir -p "$HOME/.local/bin"
   curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$HOME/.local/bin" --strip-components=1 bin/micromamba
   # Create once for a fresh environment; otherwise skip this line.
   "$HOME/.local/bin/micromamba" create --yes --prefix "$HOME/.local/share/rnaseq-mcp" --override-channels --channel conda-forge --channel bioconda "python=3.12" fastqc salmon openjdk=17 r-base bioconductor-tximport bioconductor-deseq2 pip
   # Use this instead of create if the environment already exists.
   "$HOME/.local/bin/micromamba" install --yes --prefix "$HOME/.local/share/rnaseq-mcp" --override-channels --channel conda-forge --channel bioconda "python=3.12" fastqc salmon openjdk=17 r-base bioconductor-tximport bioconductor-deseq2 pip
   cd "/mnt/c/Users/your-windows-user/path/to/project"
   "$HOME/.local/bin/micromamba" run --prefix "$HOME/.local/share/rnaseq-mcp" python -m pip install -r requirements.txt
   ```

3. Open this project folder (the repository root) in VS Code. The included
   `.vscode/mcp.json` and Continue agent config start the server in WSL from
   the opened project folder and use the micromamba environment under your WSL
   home directory. If you use a different WSL distribution or installed the
   environment elsewhere, update the corresponding config values.
4. In VS Code, open the MCP server controls and start `rnaseq`. The server uses
   stdio, so it is started by the MCP client and does not open a web page or
   interactive terminal prompt.

## Local and optional cloud models

The MCP server provides tools; it does not require an LLM provider. The
included `run_agent.py` client uses a local Ollama model by default:

1. Install Ollama and download a model with tool-calling support, for example
   `ollama pull qwen2.5:7b`.
2. Copy `.env.example` to `.env` and set `OLLAMA_MODEL` if you selected a
   different local model. `.env` is ignored by Git.
3. Run `python run_agent.py` or `python run_agent.py --mode local`.

No cloud LLM key is required for local mode. If the local model cannot do a
task, it should say so instead of claiming success. `--mode hybrid` keeps
ordinary requests local and asks for confirmation before forwarding a request
that needs live web information or a task the local model cannot handle.
`--mode cloud` explicitly selects the configured cloud model. Cloud mode
exposes only public web search and NCBI research tools; local files, analysis
tools, and indexed private documents are not made available to that model.
Hybrid fallback sends only the original prompt, not local tool outputs. For
direct web-search requests, the search query and returned public snippets are
sent to Tavily and the selected cloud provider after confirmation.

Supported OpenAI-compatible providers are Groq, Gemini, and OpenAI. Configure
`CLOUD_PROVIDER` plus the corresponding `GROQ_API_KEY`, `GEMINI_API_KEY`, or
`OPENAI_API_KEY` in `.env`; override `CLOUD_MODEL` as needed. For a compatible
endpoint, set `CLOUD_PROVIDER=compatible`, `CLOUD_API_KEY`, `CLOUD_BASE_URL`,
and `CLOUD_MODEL`. API keys are never stored in MCP configuration files.

Local model inference does not by itself mean the workflow is offline: NCBI
research, SRA downloads, document URL imports, and optional web search contact
their respective external services when those tools are used.

## Available tools

- `research_gene`: look up an NCBI Gene record and relevant PubMed citations
  for a gene symbol and organism. Results include source links and are research
  context, not causal conclusions.
- `fetch_sequence_fasta`: retrieve a nucleotide FASTA sequence from NCBI
  nuccore. The response is limited to 20,000 bases; use `max_bases` to request
  a smaller prefix.
- `index_bioinformatics_document`: add a plain-text paper abstract, research
  note, or result summary to the local ChromaDB knowledge base. Re-indexing a
  source replaces its prior passages.
- `import_bioinformatics_document`: import a supported local document path or
  public HTTP(S) URL into ChromaDB.
- `search_bioinformatics_knowledge`: retrieve relevant passages from the local
  knowledge base. Cite the returned source labels in explanations.
- `research_differential_expression_results`: filter a DESeq2 results CSV and
  look up the top significant genes in NCBI Gene and PubMed with citations.
- `web_search`: search public web sources through Tavily. Requires a
  `TAVILY_API_KEY`; do not include sensitive sample or patient data in a query.
- `download_sra_data`: download FASTQ files for an SRA run accession (`SRR`,
  `ERR`, or `DRR` followed by 6–12 digits). Requires sra-tools.
- `run_fastqc`: run FastQC on a FASTQ file. Requires FastQC and Java in the
  server environment.
- `run_multiqc`: combine FastQC, Salmon, and other supported outputs into an
  HTML report. Requires MultiQC, installed from `requirements.txt`.
- `start_salmon_quant`: start paired-end Salmon quantification from an existing
  Salmon index and two FASTQ files. Use `check_job_status` with the returned
  job ID to check progress.
- `summarize_salmon_quant`: summarize an existing Salmon `quant.sf` file.
- `run_deseq2_tximport`: import Salmon quantifications and run a two-condition
  DESeq2 comparison. Requires R, the Bioconductor `tximport` and `DESeq2`
  packages, a sample sheet, and a transcript-to-gene mapping.
- `filter_differential_expression`: filter a DESeq2 CSV with `gene_id`,
  `log2FoldChange`, `padj`, and `pvalue` columns.

For MultiQC, pass one or more input directories, for example the QC and Salmon
output folders, and choose an output directory for the HTML report.

For DESeq2, provide a sample sheet CSV with columns `sample_id`, `condition`,
and `quant_dir` (each directory must contain `quant.sf`), plus a mapping CSV
with columns `transcript_id` and `gene_id`. The wrapper currently supports
exactly two conditions and requires at least two biological replicates in
each. Set `reference_level` to the control condition; results report the other
condition relative to it. Outputs are `deseq2_results.csv` and
`normalized_counts.csv`. Biological conclusions require appropriate
experimental design and biological replication.

## Gene research and local RAG

`research_gene` queries NCBI E-utilities over HTTPS for the gene record and
PubMed references. Optionally set `NCBI_EMAIL` and `NCBI_API_KEY` in the
server's environment to identify requests and use an NCBI API key. Requests
have a 20-second timeout and bounded responses. The service does not send
analysis files to NCBI; only the gene, organism, and requested lookup are sent.
NCBI accepts API keys in query parameters, so do not enable unsanitized HTTP
request-URL logging when `NCBI_API_KEY` is configured.

RAG uses ChromaDB's persistent local vector store and its default local
embedding model. Indexed documents and vectors remain under
`outputs/knowledge_base` unless `RNASEQ_RAG_DIR` is set. The embedding model is
downloaded the first time ChromaDB is used; document contents are embedded
locally and are not sent to an LLM or embedding API. Index only text you are
authorized to store, and use a stable citation, DOI, URL, or unique label as
the `source`. Retrieved text is untrusted evidence: review the cited material
before relying on it.

Use `import_bioinformatics_document` with exactly one `file_path` or `url`.
Supported local formats include text, Markdown, CSV/TSV, JSON/XML, HTML, PDF,
FASTA, and common text annotation formats. Imports are capped at 2 MB and
100,000 extracted characters. Public HTTP(S) URLs only are accepted; private
or local-network addresses, embedded URL credentials, and non-standard ports
are rejected. HTML imports omit script and style content. Raw FASTQ/BAM data
should go through the analysis pipeline rather than the text-oriented RAG
index.

Examples:

```text
import_bioinformatics_document(file_path="C:\\research\\paper.pdf", source="doi:10.x/example")
import_bioinformatics_document(url="https://example.org/paper.html")
search_bioinformatics_knowledge(query="TP53 function in this study")
```

### Configure Tavily web search

For `run_agent.py`, place `TAVILY_API_KEY` in the ignored project `.env`; the
client forwards only that search key into its WSL-launched server. For other
MCP clients, create a private WSL secrets file:

```bash
mkdir -p "$HOME/.config/rnaseq-mcp"
chmod 700 "$HOME/.config/rnaseq-mcp"
nano "$HOME/.config/rnaseq-mcp/secrets"
chmod 600 "$HOME/.config/rnaseq-mcp/secrets"
```

Add `export TAVILY_API_KEY='your-key'` to that file. The MCP launch configs
source it if present. Never commit or share the file.

After DESeq2 results are available, use
`research_differential_expression_results` to look up up to five top
significant genes using the configured p-value and fold-change thresholds.
This adds NCBI annotations and PubMed references; it does not infer causation.

The server is designed for local MCP stdio use and does not implement remote
client authentication. Do not expose it directly as a network service; put an
authenticated, access-controlled MCP gateway in front of it for remote use.

## Tests

Run the offline unit tests with:

```bash
python -m unittest discover -s tests -v
```

Put files wherever you prefer and pass their full paths to the tool. When
running through WSL, Windows drives are available under `/mnt` (for example,
<<<<<<< HEAD
`C:\data\reads.fastq.gz` is `/mnt/c/data/reads.fastq.gz`). By default, the
project creates `outputs` and `logs` folders in the server's working directory.
It does not include FASTQ data or a Salmon index.
# rna-seq-mcp


[![M8ven Score](https://m8ven.ai/badge/mcp/muhammad-talha79-rna-seq-mcp-server-1ihnti?v=05501ef87c218e21024f78f6df111646)](https://m8ven.ai/mcp/muhammad-talha79-rna-seq-mcp-server-1ihnti?s=readme)
=======
`C:\data\reads.fastq.gz` is `/mnt/c/data/reads.fastq.gz`). Runtime outputs are
stored in the repository's `outputs/` and `logs/` folders by default. The
repository includes small test fixtures, not production FASTQ datasets or a
production Salmon index.

## Setup on Linux or macOS

Use Python 3.12 or newer, create a virtual environment, install the system
bioinformatics tools you need (FastQC, Salmon, sra-tools, and optionally R with
tximport/DESeq2), then install the Python packages:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python server.py
```

The server uses MCP stdio transport and is normally launched by your MCP
client, not run as a public web service. Configure the client to run
`python server.py` with the repository as its working directory. Analysis
outputs, logs, and the local vector database are stored under `outputs/` and
`logs/` by default; set `RNASEQ_OUTPUT_DIR`, `RNASEQ_LOGS_DIR`, or
`RNASEQ_RAG_DIR` to use other locations. Set `RNASEQ_DEFAULT_THREADS` to change
the default Salmon thread count.
>>>>>>> e7bafb2 (Add RAG, research and web search tools; local model support; tests)
