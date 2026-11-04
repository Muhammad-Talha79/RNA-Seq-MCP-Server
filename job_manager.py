import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

class JobManager:
    """In-memory task manager for tracking long-running bioinformatics pipelines."""
    
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create_job(self, task_name: str, params: Dict[str, Any]) -> str:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        self._jobs[job_id] = {
            "job_id": job_id,
            "task_name": task_name,
            "status": "RUNNING",  # RUNNING, COMPLETED, FAILED
            "submitted_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "parameters": params,
            "result_files": [],
            "logs": "",
            "error": None
        }
        return job_id

    def update_job_success(self, job_id: str, result_files: List[str], logs: str):
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "COMPLETED"
            self._jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
            self._jobs[job_id]["result_files"] = result_files
            self._jobs[job_id]["logs"] = logs

    def update_job_failure(self, job_id: str, error_msg: str, logs: str = ""):
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "FAILED"
            self._jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
            self._jobs[job_id]["error"] = error_msg
            self._jobs[job_id]["logs"] = logs

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(job_id)

job_manager = JobManager()