"""In-memory background jobs for long-running analyses (P05).

Design: a bounded ``ThreadPoolExecutor`` runs pipeline callables off the request path;
``POST`` endpoints return 202 + job id immediately and clients poll ``GET /v1/jobs/{id}``.
No HTTP call blocks past the request/response round trip itself.

* Per-job wall-clock timeout: a job still unfinished after ``timeout_seconds`` reads as
  ``timed_out``. Worker threads cannot be killed, so a late finish is discarded and the
  terminal state never changes once set.
* Hard capacity: ``submit`` first evicts TTL-expired jobs and evictable finished jobs,
  then rejects with ``JobStoreFullError`` while ``max_jobs`` live (queued/running) jobs
  remain. Queued/running jobs are never evicted, so the store holds at most ``max_jobs``
  jobs and submission floods get backpressure instead of unbounded growth.
* Progress: the worker reports ``(completed_steps, total_steps)`` through the callback
  handed to it; polling surfaces the latest counts.
* Shutdown: queued futures are cancelled and shared clients closed by the app lifespan.
  A genuinely stuck worker thread is abandoned, never awaited forever.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from climateadapt.api.errors import (
    JOB_INTERNAL,
    JOB_TIMEOUT,
    JobStoreFullError,
    domain_error_status,
)

logger = logging.getLogger(__name__)

JobStatusName = Literal["queued", "running", "succeeded", "failed", "timed_out"]
TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "timed_out"})


class JobSubmitted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatusName
    status_url: str


class JobProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed_steps: int
    total_steps: int


class JobError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    message: str


class JobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    label: str
    status: JobStatusName
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    progress: JobProgress
    result: dict[str, Any] | None
    error: JobError | None


@dataclass
class _Job:
    job_id: str
    label: str
    total_steps: int
    future: Future
    submitted_at: datetime
    deadline_monotonic: float
    started_at: datetime | None = None
    finished_at: datetime | None = None
    finished_monotonic: float | None = None
    completed_steps: int = 0
    status: JobStatusName = "queued"
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None


class JobStore:
    """Thread-safe registry of background jobs with timeout and TTL eviction."""

    def __init__(
        self,
        *,
        max_workers: int = 4,
        timeout_seconds: float = 900.0,
        ttl_seconds: float = 3600.0,
        max_jobs: int = 1000,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._ttl_seconds = ttl_seconds
        self._max_jobs = max(1, max_jobs)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="climateadapt-job"
        )
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._shutdown = False

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    def submit(
        self,
        label: str,
        total_steps: int,
        fn: Callable[[Callable[[int, int], None]], dict[str, Any]],
    ) -> str:
        """Queue ``fn`` and return its job id. ``fn`` gets a progress callback.

        Raises:
            RuntimeError: the store is shut down.
            JobStoreFullError: ``max_jobs`` live jobs already occupy the store.
        """
        job_id = uuid.uuid4().hex
        now = time.monotonic()

        def report(completed: int, total: int) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None and job.status not in TERMINAL_STATUSES:
                    job.completed_steps = completed
                    job.total_steps = total

        def run() -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None and job.status == "queued":
                    job.status = "running"
                    job.started_at = datetime.now(UTC)
            try:
                outcome = fn(report)
            except Exception as exc:
                self._record_failure(job_id, exc)
            else:
                self._record_success(job_id, outcome)

        with self._lock:
            if self._shutdown:
                raise RuntimeError("JobStore is shut down; refusing new jobs.")
            # Evict first so finished jobs make room; then enforce the hard cap.
            # The check and the insertion below are one atomic critical section,
            # so concurrent submissions can never overshoot max_jobs.
            self._evict_locked(now, target_size=self._max_jobs - 1)
            if len(self._jobs) >= self._max_jobs:
                raise JobStoreFullError(
                    f"Job store is at capacity ({self._max_jobs} jobs); retry shortly."
                )
            future = self._executor.submit(run)
            self._jobs[job_id] = _Job(
                job_id=job_id,
                label=label,
                total_steps=total_steps,
                future=future,
                submitted_at=datetime.now(UTC),
                deadline_monotonic=now + self._timeout_seconds,
            )
        return job_id

    def _record_success(self, job_id: str, outcome: dict[str, Any]) -> None:
        """Record a finished job unless it already reached a terminal state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                return
            job.finished_at = datetime.now(UTC)
            job.finished_monotonic = time.monotonic()
            job.status = "succeeded"
            job.result = outcome
            job.completed_steps = job.total_steps

    def _record_failure(self, job_id: str, exc: Exception) -> None:
        """Record a failed job unless it already reached a terminal state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                return
            job.finished_at = datetime.now(UTC)
            job.finished_monotonic = time.monotonic()
            job.status = "failed"
            mapped = domain_error_status(exc)
            if mapped is not None:
                _, code = mapped
                job.error = {"type": code, "message": str(exc)}
            else:
                logger.exception("Background job %s (%s) failed", job_id, job.label)
                job.error = {"type": JOB_INTERNAL, "message": "Internal job error."}

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Return a status snapshot, or None if unknown/expired. Marks timeouts."""
        now = time.monotonic()
        with self._lock:
            self._evict_locked(now)
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status not in TERMINAL_STATUSES and now >= job.deadline_monotonic:
                job.status = "timed_out"
                job.finished_at = datetime.now(UTC)
                job.finished_monotonic = now
                job.error = {
                    "type": JOB_TIMEOUT,
                    "message": (
                        f"Job exceeded its {self._timeout_seconds:g} s time budget; "
                        "retry with a warm cache or a smaller request."
                    ),
                }
            return {
                "job_id": job.job_id,
                "label": job.label,
                "status": job.status,
                "submitted_at": job.submitted_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "progress": {
                    "completed_steps": job.completed_steps,
                    "total_steps": job.total_steps,
                },
                "result": job.result,
                "error": job.error,
            }

    def _evict_locked(self, now: float, target_size: int | None = None) -> None:
        """Drop TTL-expired finished jobs; trim finished jobs past ``target_size``.

        Only terminal jobs are ever evicted; queued/running jobs are left alone.
        Caller holds the lock.
        """
        cutoff = now - self._ttl_seconds
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in TERMINAL_STATUSES
            and job.finished_monotonic is not None
            and job.finished_monotonic < cutoff
        ]
        for job_id in expired:
            del self._jobs[job_id]
        cap = self._max_jobs if target_size is None else target_size
        while len(self._jobs) > cap:
            oldest = min(self._jobs.values(), key=lambda job: job.submitted_at)
            if oldest.status not in TERMINAL_STATUSES:
                break
            del self._jobs[oldest.job_id]

    def shutdown(self) -> None:
        """Cancel queued work and stop accepting jobs. Never blocks on workers."""
        with self._lock:
            self._shutdown = True
        self._executor.shutdown(wait=False, cancel_futures=True)
