"""Calendar-month helpers."""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}")


@dataclass(frozen=True, order=True)
class YearMonth:
    """A calendar month. Orders chronologically."""

    year: int
    month: int

    def __post_init__(self) -> None:
        for name, value in (("year", self.year), ("month", self.month)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an int, got {type(value).__name__}.")
        if not 1 <= self.month <= 12:
            raise ValueError(f"month must be 1-12, got {self.month}.")
        if not 1 <= self.year <= 9999:
            raise ValueError(f"year must be 1-9999, got {self.year}.")

    def next(self) -> YearMonth:
        if self.month == 12:
            return YearMonth(self.year + 1, 1)
        return YearMonth(self.year, self.month + 1)

    def last_day(self) -> date:
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @classmethod
    def parse(cls, text: str) -> YearMonth:
        """Parse a strict ``YYYY-MM`` string."""
        if not isinstance(text, str) or _PATTERN.fullmatch(text) is None:
            raise ValueError(f"Expected a month in YYYY-MM format, got {text!r}.")
        return cls(int(text[:4]), int(text[5:]))


def iter_months(start: YearMonth, end: YearMonth) -> Iterator[YearMonth]:
    """Return an iterator over months from ``start`` to ``end`` inclusive.

    Raises ValueError immediately (not lazily) if ``end`` is before ``start``.
    """
    if end < start:
        raise ValueError(f"end month {end} is earlier than start month {start}.")

    def _generate() -> Iterator[YearMonth]:
        current = start
        while current <= end:
            yield current
            current = current.next()

    return _generate()