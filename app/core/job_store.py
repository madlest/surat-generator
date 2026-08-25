import threading
import uuid
from typing import Any


class JobStore:
    """
    Penyimpanan status job in-memory (bukan database), cukup untuk
    melacak progress batch generation selama proses aplikasi berjalan.
    Thread-safe karena diakses dari banyak background task sekaligus.
    """

    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(self, job_id: str, total: int) -> None:
        with self._lock:
            self._jobs[job_id] = {
                "status": "processing",  # processing | done | error
                "current": 0,
                "total": total,
                "zip_path": None,
                "error": None,
            }

    def update_progress(self, job_id: str, current: int) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["current"] = current

    def mark_done(self, job_id: str, zip_path: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "done"
                self._jobs[job_id]["zip_path"] = zip_path

    def mark_error(self, job_id: str, error_message: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "error"
                self._jobs[job_id]["error"] = error_message

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


job_store = JobStore()