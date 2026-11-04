import pandas as pd
from pathlib import Path
from typing import Any
from config import config
from utils import run_async_command, validate_paths

def register_analysis_tools(mcp: Any):

    @mcp.tool()
    async def run_deseq2_tximport(
        sample_sheet_csv: str,
        tx2gene_csv: str,
        output_dir: str = str(config.OUTPUT_DIR / "deseq2"),
        reference_level: str = "",
    ) -> str:
        """Runs tximport and DESeq2 for two conditions with at least two biological replicates each.

        The sample sheet must contain sample_id, condition, and quant_dir columns. Each
        quant_dir must contain a Salmon quant.sf file. The mapping CSV must contain
        transcript_id and gene_id columns.

        Args:
            sample_sheet_csv: CSV describing samples, conditions, and Salmon output directories.
            tx2gene_csv: CSV mapping transcript IDs to gene IDs.
            output_dir: Folder for the DESeq2 results and normalized counts.
            reference_level: Condition used as the control/reference in the comparison.
        """
        missing = validate_paths([sample_sheet_csv, tx2gene_csv])
        if missing:
            return f"❌ File Error: {missing[0]} does not exist."
        if not reference_level.strip():
            return "❌ Validation Error: reference_level must name the control condition."

        try:
            samples = pd.read_csv(sample_sheet_csv, dtype=str)
            tx2gene = pd.read_csv(tx2gene_csv, dtype=str)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError) as error:
            return f"❌ Input CSV could not be read: {error}"

        required_sample_columns = {"sample_id", "condition", "quant_dir"}
        missing_columns = required_sample_columns.difference(samples.columns)
        if missing_columns:
            return f"❌ Sample sheet is missing columns: {', '.join(sorted(missing_columns))}"
        required_mapping_columns = {"transcript_id", "gene_id"}
        missing_columns = required_mapping_columns.difference(tx2gene.columns)
        if missing_columns:
            return f"❌ Transcript mapping is missing columns: {', '.join(sorted(missing_columns))}"
        if samples.empty or samples[list(required_sample_columns)].isna().any().any():
            return "❌ Sample sheet must contain rows with non-empty sample_id, condition, and quant_dir values."
        if tx2gene.empty or tx2gene[list(required_mapping_columns)].isna().any().any():
            return "❌ Transcript mapping must contain rows with non-empty transcript_id and gene_id values."
        if samples[list(required_sample_columns)].apply(
            lambda column: column.str.strip().eq("").any()
        ).any():
            return "❌ Sample sheet must contain rows with non-empty sample_id, condition, and quant_dir values."
        if tx2gene[list(required_mapping_columns)].apply(
            lambda column: column.str.strip().eq("").any()
        ).any():
            return "❌ Transcript mapping must contain rows with non-empty transcript_id and gene_id values."
        if samples["sample_id"].duplicated().any():
            return "❌ Sample IDs must be unique."
        if tx2gene["transcript_id"].duplicated().any():
            return "❌ Each transcript_id must appear only once in the transcript mapping."

        conditions = samples["condition"].unique().tolist()
        if len(conditions) != 2:
            return "❌ This wrapper currently supports exactly two conditions per comparison."
        if reference_level not in conditions:
            return f"❌ Reference condition '{reference_level}' is not present in the sample sheet."
        replicate_counts = samples.groupby("condition")["sample_id"].count()
        under_replicated = replicate_counts[replicate_counts < 2].index.tolist()
        if under_replicated:
            return f"❌ At least two biological replicates per condition are required; insufficient: {', '.join(under_replicated)}."

        invalid_quant_dirs = [
            str(Path(quant_dir))
            for quant_dir in samples["quant_dir"]
            if not (Path(quant_dir).is_dir() and (Path(quant_dir) / "quant.sf").is_file())
        ]
        if invalid_quant_dirs:
            return f"❌ Each quant_dir must be a directory containing quant.sf. Invalid: {invalid_quant_dirs[0]}"

        script_path = Path(__file__).with_name("deseq2_tximport.R")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        cmd = [
            "Rscript",
            str(script_path),
            str(Path(sample_sheet_csv).resolve()),
            str(Path(tx2gene_csv).resolve()),
            str(output_path.resolve()),
            reference_level,
        ]
        try:
            code, stdout, stderr = await run_async_command(cmd)
        except FileNotFoundError:
            return "❌ Rscript is not installed or is not available on PATH. Install R and the Bioconductor dependencies listed in the README."
        if code == 0:
            result_path = output_path / "deseq2_results.csv"
            counts_path = output_path / "normalized_counts.csv"
            if not result_path.is_file() or not counts_path.is_file():
                return "❌ DESeq2 exited successfully but expected output CSV files were not created."
            comparison_level = next(condition for condition in conditions if condition != reference_level)
            return (
                f"✅ DESeq2 analysis completed. Comparison: {comparison_level} vs {reference_level}\n"
                f"- Results: {result_path}\n"
                f"- Normalized counts: {counts_path}\n"
                f"{stdout[-500:]}"
            )
        return f"❌ DESeq2 analysis failed:\n{stderr[-1000:]}"

    @mcp.tool()
    def summarize_salmon_quant(quant_sf_path: str, top_n: int = 10) -> str:
        """Parses a Salmon quant.sf file and returns a concise, token-efficient table summary.
        
        Args:
            quant_sf_path: Path to the quant.sf file.
            top_n: Number of top expressed transcripts to retrieve by TPM.
        """
        missing = validate_paths([quant_sf_path])
        if missing:
            return f"❌ File Error: {missing[0]} does not exist."

        try:
            df = pd.read_csv(quant_sf_path, sep="\t")
            total_transcripts = len(df)
            expressed_transcripts = len(df[df["NumReads"] > 0])
            top_transcripts = df.sort_values(by="TPM", ascending=False).head(top_n)

            markdown_table = top_transcripts[["Name", "Length", "TPM", "NumReads"]].to_markdown(index=False)
            
            return (
                f"📊 **Quantification Metrics:**\n"
                f"- **Total Reference Transcripts:** {total_transcripts:,}\n"
                f"- **Transcripts Detected (>0 reads):** {expressed_transcripts:,}\n\n"
                f"🔝 **Top {top_n} Expressed Transcripts (by TPM):**\n"
                f"{markdown_table}"
            )
        except Exception as e:
            return f"❌ Error processing quant file: {str(e)}"

    @mcp.tool()
    def filter_differential_expression(
        deseq2_csv_path: str, 
        padj_cutoff: float = 0.05, 
        lfc_cutoff: float = 1.0, 
        top_n: int = 15
    ) -> str:
        """Filters DEG results (DESeq2 CSV) by significance and log2 fold-change.
        
        Args:
            deseq2_csv_path: CSV output from DESeq2 analysis.
            padj_cutoff: Adjusted p-value significance threshold.
            lfc_cutoff: Minimum absolute log2 fold-change threshold.
            top_n: Max rows returned to keep LLM context bounded.
        """
        missing = validate_paths([deseq2_csv_path])
        if missing:
            return f"❌ File Error: {missing[0]} does not exist."

        try:
            df = pd.read_csv(deseq2_csv_path)
            
            # Filter rows
            sig_df = df[
                (df['padj'] < padj_cutoff) & 
                (df['log2FoldChange'].abs() >= lfc_cutoff)
            ].sort_values(by='padj', ascending=True)

            upregulated = len(sig_df[sig_df['log2FoldChange'] > 0])
            downregulated = len(sig_df[sig_df['log2FoldChange'] < 0])

            top_results = sig_df.head(top_n)[['gene_id', 'log2FoldChange', 'padj', 'pvalue']]
            
            return (
                f"🧬 **Differential Expression Summary:**\n"
                f"- **Total Significant DEGs:** {len(sig_df)}\n"
                f"- **Upregulated:** {upregulated}\n"
                f"- **Downregulated:** {downregulated}\n\n"
                f"🔥 **Top {min(top_n, len(sig_df))} Significant Genes:**\n"
                f"{top_results.to_markdown(index=False)}"
            )
        except Exception as e:
            return f"❌ Error analyzing DEG results: {str(e)}"