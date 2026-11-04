import asyncio
from pathlib import Path
from typing import List, Tuple

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