import asyncio
from pathlib import Path
from typing import Any
from config import config
from job_manager import job_manager
from utils import run_async_command, validate_paths

def register_pipeline_tools(mcp: Any):

    @mcp.tool()
    async def run_multiqc(
        input_paths: list[str],
        output_dir: str = str(config.OUTPUT_DIR / "multiqc"),
        report_name: str = "multiqc_report.html",
    ) -> str:
        """Generates a combined MultiQC report from FastQC, Salmon, or other supported outputs.

        Args:
            input_paths: One or more files or directories containing analysis outputs.
            output_dir: Folder for the generated MultiQC report and data.
            report_name: HTML report filename.
        """
        if not input_paths:
            return "❌ Validation Error: Provide at least one input file or directory."
        missing = validate_paths(input_paths)
        if missing:
            return f"❌ Validation Error: Input path not found: {missing[0]}"
        if not report_name.lower().endswith(".html") or Path(report_name).name != report_name:
            return "❌ Validation Error: report_name must be an HTML filename without a directory path."

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        cmd = [
            "multiqc",
            "--force",
            "--outdir",
            output_dir,
            "--filename",
            report_name,
            *input_paths,
        ]
        try:
            code, stdout, stderr = await run_async_command(cmd)
        except FileNotFoundError:
            return "❌ MultiQC is not installed or is not available on PATH. Install it in the server environment as described in the README."
        if code == 0:
            report_path = Path(output_dir) / report_name
            if not report_path.is_file():
                return f"❌ MultiQC exited successfully but did not create the expected report: {report_path}"
            return f"✅ MultiQC report generated: {report_path}\n{stdout[-500:]}"
        return f"❌ MultiQC failed:\n{stderr[-800:]}"

    @mcp.tool()
    async def run_fastqc(fastq_path: str, output_dir: str = str(config.OUTPUT_DIR / "qc")) -> str:
        """Executes FastQC on a raw FASTQ file asynchronously.
        
        Args:
            fastq_path: Path to input FASTQ file.
            output_dir: Folder to store HTML and zip QC reports.
        """
        missing = validate_paths([fastq_path])
        if missing:
            return f"❌ Validation Error: Input file not found: {missing[0]}"

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        cmd = ["fastqc", fastq_path, "-o", output_dir]
        
        code, stdout, stderr = await run_async_command(cmd)
        if code == 0:
            return f"✅ FastQC complete for {fastq_path}.\nReport generated in: {output_dir}"
        return f"❌ FastQC failed:\n{stderr[-500:]}"

    @mcp.tool()
    async def start_salmon_quant(
        index_dir: str, 
        fastq_1: str, 
        fastq_2: str, 
        output_dir: str, 
        threads: int = config.DEFAULT_THREADS
    ) -> str:
        """Submits a long-running Salmon transcript quantification job to background.
        
        Args:
            index_dir: Path to prepared Salmon index directory.
            fastq_1: Read 1 FASTQ file path.
            fastq_2: Read 2 FASTQ file path.
            output_dir: Target directory for quantification output.
            threads: Number of CPU threads allocated.
        """
        missing = validate_paths([index_dir, fastq_1, fastq_2])
        if missing:
            return f"❌ Validation Error: Missing input paths: {', '.join(missing)}"

        job_id = job_manager.create_job("Salmon Quantification", {
            "index_dir": index_dir, "fastq_1": fastq_1, "fastq_2": fastq_2, "output_dir": output_dir
        })

        asyncio.create_task(_execute_salmon_job(job_id, index_dir, fastq_1, fastq_2, output_dir, threads))

        return (
            f"🚀 Salmon quantification background job submitted!\n"
            f"Job ID: {job_id}\n"
            f"Track progress via tool: check_job_status(job_id='{job_id}')"
        )

    @mcp.tool()
    def check_job_status(job_id: str) -> str:
        """Inspects status of a background pipeline job."""
        job = job_manager.get_job_status(job_id)
        if not job:
            return f"❌ Error: Job ID '{job_id}' not found."

        status = job["status"]
        if status == "RUNNING":
            return f"⏳ Job '{job_id}' ({job['task_name']}) is currently RUNNING."
        elif status == "COMPLETED":
            artifacts = "\n".join([f"- {f}" for f in job["result_files"]])
            return (
                f"✅ Job '{job_id}' COMPLETED successfully!\n\n"
                f"📁 Produced Files:\n{artifacts}\n\n"
                f"📋 Log Snippet:\n{job['logs'][-300:]}"
            )
        else:
            return f"❌ Job '{job_id}' FAILED.\nError message: {job['error']}\nLogs:\n{job['logs'][-400:]}"

async def _execute_salmon_job(job_id: str, index: str, f1: str, f2: str, out: str, threads: int):
    Path(out).mkdir(parents=True, exist_ok=True)
    cmd = [
        "salmon", "quant",
        "-i", index,
        "-l", "A",
        "-1", f1,
        "-2", f2,
        "-o", out,
        "-p", str(threads),
        "--validateMappings"
    ]
    code, stdout, stderr = await run_async_command(cmd)
    
    if code == 0:
        result_files = [str(Path(out) / "quant.sf"), str(Path(out) / "cmd_info.json")]
        job_manager.update_job_success(job_id, result_files, stderr[-500:])
    else:
        job_manager.update_job_failure(job_id, f"Salmon process exited with code {code}", stderr[-800:])