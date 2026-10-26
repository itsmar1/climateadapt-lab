"""Exceptions raised by data connectors.

Callers (the API, later the agent) can handle each case distinctly.
"""

from __future__ import annotations


class DataAccessError(Exception):
    """Base class for data-connector failures."""


class OutsideCoverageError(DataAccessError):
    """The requested location or time is outside the dataset's documented coverage."""


class DataNotAvailableError(DataAccessError):
    """Data inside the documented coverage is not available (not published, not cached)."""


class DownloadError(DataAccessError):
    """A network or HTTP failure while downloading."""


class DataIntegrityError(DataAccessError):
    """A downloaded or cached file is corrupt, inconsistent, or has unexpected content."""


class MissingDataError(DataAccessError):
    """One or more required values are missing (nodata) and no total can be computed."""