"""Shared API error vocabulary (single source of truth).

Domain error -> (HTTP status, machine-readable code). All HTTP error bodies share one
shape: ``{"detail": [{"loc": [...], "msg": "...", "type": "<code>"}]}``.

Job/bundle error records reuse the domain codes below. Three deliberate additions exist
for the P05 job surface (documented in README):

* ``job_not_found`` (HTTP 404): unknown or expired job id.
* ``timeout`` (job/bundle record): the job exceeded its configured time budget.
* ``internal`` (job/bundle record): unexpected failure; the message is generic and the
  original error is logged server-side only.
* ``server_busy`` (HTTP 503): the job store is at capacity; retry shortly.

Two deliberate additions exist for the P11 scenario surface:

* ``scenario_not_found`` (HTTP 404): unknown or deleted scenario id.
* ``request_too_large`` (HTTP 413): the request body exceeded the configured cap.

Two deliberate additions exist for the P14 demo surface:

* ``demo_mode_disabled`` (HTTP 404): demo endpoints called with demo mode off.
* ``demo_snapshot_not_found`` (HTTP 404): unknown demo snapshot key.
"""

from __future__ import annotations

from climateadapt.data.errors import (
    DataIntegrityError,
    DataNotAvailableError,
    DownloadError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.indicators.spi import InsufficientReferenceError
from climateadapt.pipelines.rainfall_anomaly import InsufficientBaselineError

SERVER_BUSY = "server_busy"


class JobStoreFullError(Exception):
    """The job store is at capacity; the submission was rejected (backpressure)."""


DOMAIN_ERRORS: tuple[tuple[type[Exception], int, str], ...] = (
    (OutsideCoverageError, 422, "outside_coverage"),
    (DataNotAvailableError, 404, "data_not_available"),
    (MissingDataError, 422, "missing_data"),
    (InsufficientBaselineError, 422, "insufficient_baseline"),
    (InsufficientReferenceError, 422, "insufficient_reference"),
    (DownloadError, 502, "download_error"),
    (DataIntegrityError, 502, "data_integrity_error"),
    (JobStoreFullError, 503, SERVER_BUSY),
)

JOB_NOT_FOUND = "job_not_found"
JOB_TIMEOUT = "timeout"
JOB_INTERNAL = "internal"
SCENARIO_NOT_FOUND = "scenario_not_found"
REQUEST_TOO_LARGE = "request_too_large"
DEMO_MODE_DISABLED = "demo_mode_disabled"
DEMO_SNAPSHOT_NOT_FOUND = "demo_snapshot_not_found"


def domain_error_status(exc: Exception) -> tuple[int, str] | None:
    """Return (HTTP status, code) for a known domain error, else None."""
    for exc_type, status_code, code in DOMAIN_ERRORS:
        if isinstance(exc, exc_type):
            return status_code, code
    return None
