from pathlib import Path
from typing import Any
from config import config

def register_resources(mcp: Any):

    @mcp.resource("rnaseq://metadata/sample_sheet")
    def get_sample_sheet() -> str:
        """Exposes the project sample sheet directly as an MCP context resource."""
        sample_sheet_file = config.DATA_DIR / "samples.csv"
        if not sample_sheet_file.exists():
            return "Sample_ID,Condition,Replicate\nS1,Control,1\nS2,Control,2\nS3,Treated,1\nS4,Treated,2"
        return sample_sheet_file.read_text()

    @mcp.resource("rnaseq://config/pipeline_params")
    def get_pipeline_config() -> str:
        """Returns runtime parameters configured on this MCP server instance."""
        return (
            f"Project Output Directory: {config.OUTPUT_DIR}\n"
            f"Logs Directory: {config.LOGS_DIR}\n"
            f"Default Thread Allocation: {config.DEFAULT_THREADS}\n"
        )