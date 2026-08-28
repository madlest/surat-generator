import threading
import time
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

    def create_job(self, job_id: str, total: int, unit_id: int) -> None:
        with self._lock:
            self._jobs[job_id] = {
                "status": "processing",  # processing | done | error
                "current": 0,
                "total": total,
                "zip_path": None,
                "error": None,
                "created_at": time.time(),
                # Unit pemilik LetterType yang di-generate, BUKAN user yang
                # memicunya. Dipakai untuk isolasi antar unit di endpoint
                # status/download: admin di-scope ke unit, bukan ke akun
                # pribadi, jadi sesama admin unit yang sama boleh saling cek
                # job satu sama lain.
                "unit_id": unit_id,
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

    def sweep_stale(self, max_age_seconds: float) -> list[str]:
        """
        Buang job yang sudah lewat umur maksimal dan kembalikan zip_path-nya
        (kalau ada) supaya pemanggil bisa ikut membersihkan working dir-nya.

        Job yang gagal tidak pernah diunduh, jadi tanpa ini entry-nya menumpuk
        di memori selama proses hidup. Job sukses yang tidak jadi diunduh user
        (tab ditutup) juga ikut tersapu di sini.
        """
        cutoff = time.time() - max_age_seconds
        stale_zip_paths: list[str] = []
        with self._lock:
            for job_id in [jid for jid, job in self._jobs.items() if job["created_at"] < cutoff]:
                job = self._jobs.pop(job_id)
                if job.get("zip_path"):
                    stale_zip_paths.append(job["zip_path"])
        return stale_zip_paths


job_store = JobStore()