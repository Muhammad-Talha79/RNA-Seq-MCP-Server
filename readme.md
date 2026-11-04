# RNA-Seq Bioinformatic MCP Server

This project is an MCP (Model Context Protocol) server. It provides RNA-seq
quality-control, quantification, and result-analysis tools to an MCP-compatible
AI client; it is not a standalone desktop application.

## Recommended setup on Windows with WSL

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

## Continue model API keys

The Continue agent configuration at `.continue/agents/new-config.yaml` reads
provider keys from secret references rather than storing credentials in YAML.
To configure them:

1. Revoke and replace any provider keys that were previously exposed.
2. Copy `.continue/.env.example` to `.continue/.env`.
3. Replace the example values with the new Groq and Gemini API keys. Do not
   add quotes around the values.
4. Restart VS Code so Continue reloads the secrets.

The `.continue/.env` file is ignored by Git. Never share or commit it.

## Available tools

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

Put files wherever you prefer and pass their full paths to the tool. When
running through WSL, Windows drives are available under `/mnt` (for example,
`C:\data\reads.fastq.gz` is `/mnt/c/data/reads.fastq.gz`). By default, the
project creates `outputs` and `logs` folders in the server's working directory.
It does not include FASTQ data or a Salmon index.
# rna-seq-mcp
