from pathlib import Path
from pydantic import BaseModel

class ServerConfig(BaseModel):
    PROJECT_NAME: str = "RNASeq-Agent-Server"
    VERSION: str = "1.0.0"
    
    # Base working directories
    BASE_DIR: Path = Path.cwd()
    DATA_DIR: Path = BASE_DIR / "data"
    OUTPUT_DIR: Path = BASE_DIR / "outputs"
    LOGS_DIR: Path = BASE_DIR / "logs"
    
    # Tool execution defaults
    DEFAULT_THREADS: int = 8

config = ServerConfig()

# Ensure standard operational folders exist
for folder in [config.DATA_DIR, config.OUTPUT_DIR, config.LOGS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)