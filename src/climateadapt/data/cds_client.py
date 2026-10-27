"""Bounded-retry construction of the official ``cdsapi`` client.

cdsapi's own log shows retries up to 500 attempts with sleeps up to 120 s, which could block a
call for many hours. This module passes tighter limits, but only for options that the INSTALLED
``cdsapi.Client.__init__`` really exposes (checked by inspecting its signature at runtime), so
a wrong or renamed option can never crash client creation. Unsupported options are reported in
a warning and cdsapi's defaults then apply.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from climateadapt.data.errors import DataAccessError

logger = logging.getLogger(__name__)

_KEYWORD_KINDS = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)


def supported_options(
    client_class: Any, desired: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Split ``desired`` into options the class's __init__ names explicitly, and the rest.

    A bare ``**kwargs`` does not count: we cannot know whether such an option is honoured.
    """
    try:
        parameters = inspect.signature(client_class.__init__).parameters
    except (TypeError, ValueError):
        return {}, sorted(desired)
    supported = {
        name: value
        for name, value in desired.items()
        if name in parameters and parameters[name].kind in _KEYWORD_KINDS
    }
    return supported, sorted(set(desired) - set(supported))


def make_cds_client_factory(
    *, retry_max: int, sleep_max_seconds: float, timeout_seconds: float
) -> Callable[[], Any]:
    """Return a zero-argument factory that builds a bounded ``cdsapi.Client`` lazily."""

    def factory() -> Any:
        try:
            import cdsapi
        except ImportError as exc:
            raise DataAccessError(
                "The 'cdsapi' package is not installed. Run `uv sync --extra dev`."
            ) from exc
        options, unsupported = supported_options(
            cdsapi.Client,
            {
                "retry_max": retry_max,
                "sleep_max": int(sleep_max_seconds),
                "timeout": timeout_seconds,
            },
        )
        if unsupported:
            logger.warning(
                "The installed cdsapi does not expose the option(s) %s; its own defaults apply "
                "and a failing request may retry for a long time.",
                ", ".join(unsupported),
            )
        return cdsapi.Client(**options)

    return factory