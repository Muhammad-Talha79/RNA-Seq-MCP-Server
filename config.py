import os
from pathlib import Path
from pydantic import BaseModel


class ServerConfig(BaseModel):
    PROJECT_NAME: str = os.environ.get("RNASEQ_PROJECT_NAME", "RNASeq-Agent-Server")
    VERSION: str = "1.0.0"

    BASE_DIR: Path = Path(
        os.environ.get("RNASEQ_BASE_DIR", str(Path(__file__).resolve().parent))
    )
    DATA_DIR: Path = Path(os.environ.get("RNASEQ_DATA_DIR", str(BASE_DIR / "data")))
    OUTPUT_DIR: Path = Path(
        os.environ.get("RNASEQ_OUTPUT_DIR", str(BASE_DIR / "outputs"))
    )
    LOGS_DIR: Path = Path(os.environ.get("RNASEQ_LOGS_DIR", str(BASE_DIR / "logs")))
    RAG_DIR: Path = Path(
        os.environ.get("RNASEQ_RAG_DIR", str(OUTPUT_DIR / "knowledge_base"))
    )
    DEFAULT_THREADS: int = int(os.environ.get("RNASEQ_DEFAULT_THREADS", "8"))

config = ServerConfig()

for folder in [config.DATA_DIR, config.OUTPUT_DIR, config.LOGS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)