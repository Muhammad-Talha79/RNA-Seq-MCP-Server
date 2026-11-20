import asyncio
import logging
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlsplit, urlunsplit


class _RedactHttpxQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name.startswith("httpx")
            and isinstance(record.msg, str)
            and record.msg.startswith("HTTP Request:")
            and isinstance(record.args, tuple)
            and len(record.args) > 1
        ):
            request_url = urlsplit(str(record.args[1]))
            safe_url = urlunsplit(
                (request_url.scheme, request_url.netloc, request_url.path, "", "")
            )
            record.args = (*record.args[:1], safe_url, *record.args[2:])
        return True


def configure_httpx_log_redaction() -> None:
    logger = logging.getLogger("httpx")
    if not any(
        isinstance(log_filter, _RedactHttpxQueryFilter)
        for log_filter in logger.filters
    ):
        logger.addFilter(_RedactHttpxQueryFilter())

async def run_async_command(cmd: List[str]) -> Tuple[int, str, str]:
    """Helper to run shell commands asynchronously without blocking the event loop."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return (
        process.returncode or 0,
        stdout.decode('utf-8', errors='replace'),
        stderr.decode('utf-8', errors='replace')
    )

def validate_paths(paths: List[str]) -> List[str]:
    """Validates if input files/folders exist before running CLI tools."""
    missing = []
    for p in paths:
        if not Path(p).exists():
            missing.append(p)
    return missing