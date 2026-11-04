import os
import subprocess
from mcp.server.fastmcp import FastMCP  # type: ignore[reportAttributeAccessIssue]
from config import config
from tools.pipeline import register_pipeline_tools
from tools.analysis import register_analysis_tools
from resources.metadata import register_resources

# Initialize FastMCP application instance
mcp = FastMCP(
    name=config.PROJECT_NAME,
    instructions="MCP Server providing RNA-Seq pipeline orchestration, quality control, DEG analysis, and SRA data retrieval capabilities."
)

# Register existing modular components
register_pipeline_tools(mcp)
register_analysis_tools(mcp)
register_resources(mcp)

# Register new SRA download tool
@mcp.tool()
def download_sra_data(sra_accession: str, output_dir: str = "data") -> str:
    """
    Downloads FASTQ files from NCBI SRA using an accession number (e.g., SRR12345678, PRJNA12345).
    
    Args:
        sra_accession: The SRA accession number to download (e.g., SRR12345678).
        output_dir: Target directory where downloaded FASTQ files will be saved.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Execute fasterq-dump from sra-tools inside WSL
    command = [
        "fasterq-dump",
        "--outdir", output_dir,
        "--split-files",
        "--progress",
        sra_accession
    ]
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return (
            f"Successfully downloaded FASTQ dataset for '{sra_accession}' into '{output_dir}'.\n"
            f"Output log:\n{result.stdout}"
        )
    except subprocess.CalledProcessError as e:
        return f"Error executing fasterq-dump for {sra_accession}:\n{e.stderr}"
    except FileNotFoundError:
        return (
            "Error: 'fasterq-dump' executable not found in system PATH. "
            "Please ensure 'sra-tools' is installed in your micromamba environment."
        )

    # Truncate long terminal logs to save tokens
def sanitize_output(output_text: str, max_lines: int = 20) -> str:
    lines = output_text.strip().split("\n")
    if len(lines) > max_lines:
        return "\n".join(lines[:10] + [f"\n... [Truncated {len(lines) - max_lines} lines of log output] ...\n"] + lines[-10:])
    return output_text

if __name__ == "__main__":
    # Default execution uses stdio transport (compatible with Claude Desktop / Cursor / custom AI agents)
    mcp.run(transport="stdio")