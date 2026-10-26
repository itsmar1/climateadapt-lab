from datetime import date

import pytest

from climateadapt.data.coverage import (
    CHIRPS_V3_NOMINAL_BBOX,
    check_month_available,
    check_point_in_nominal_coverage,
    validate_coordinates,
)
from climateadapt.data.errors import DataNotAvailableError, OutsideCoverageError
from climateadapt.data.periods import YearMonth, iter_months

TODAY = date(2026, 10, 24)


def test_yearmonth_str_and_ordering():
    assert str(YearMonth(2024, 3)) == "2024-03"
    assert YearMonth(2023, 12) < YearMonth(2024, 1)


@pytest.mark.parametrize(("year", "month"), [(2024, 0), (2024, 13), (0, 1), (10000, 1)])
def test_yearmonth_out_of_range(year, month):
    with pytest.raises(ValueError):
        YearMonth(year, month)


@pytest.mark.parametrize(("year", "month"), [(2024.0, 3), (2024, True), ("2024", 3)])
def test_yearmonth_rejects_non_int(year, month):
    with pytest.raises(ValueError):
        YearMonth(year, month)  # type: ignore[arg-type]


def test_parse():
    assert YearMonth.parse("2024-03") == YearMonth(2024, 3)


@pytest.mark.parametrize("text", ["2024-3", "202403", "abc", "2024-13", "", "2024-03-01"])
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        YearMonth.parse(text)


def test_next_rolls_year():
    assert YearMonth(2023, 12).next() == YearMonth(2024, 1)
    assert YearMonth(2024, 5).next() == YearMonth(2024, 6)


def test_last_day_handles_leap_year():
    assert YearMonth(2024, 2).last_day() == date(2024, 2, 29)
    assert YearMonth(2023, 2).last_day() == date(2023, 2, 28)


def test_iter_months_inclusive_across_year_boundary():
    months = list(iter_months(YearMonth(2023, 11), YearMonth(2024, 2)))
    assert [str(m) for m in months] == ["2023-11", "2023-12", "2024-01", "2024-02"]


def test_iter_months_single():
    assert list(iter_months(YearMonth(2024, 5), YearMonth(2024, 5))) == [YearMonth(2024, 5)]


def test_iter_months_reversed_raises_immediately():
    with pytest.raises(ValueError):
        iter_months(YearMonth(2024, 5), YearMonth(2024, 4))


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (30.4, -9.6, True),
        (0.0, 0.0, True),
        (60.0, 0.0, True),  # north edge inclusive
        (-60.0, 0.0, False),  # south edge exclusive
        (-59.99, 0.0, True),
        (0.0, -180.0, True),  # west edge inclusive
        (0.0, 180.0, False),  # east edge exclusive
        (0.0, 179.99, True),
        (60.01, 0.0, False),
        (-61.0, 0.0, False),
        (75.0, 0.0, False),
    ],
)
def test_bbox_contains(lat, lon, expected):
    assert CHIRPS_V3_NOMINAL_BBOX.contains(lat, lon) is expected


def test_point_outside_coverage_raises_with_bounds_in_message():
    with pytest.raises(OutsideCoverageError, match="60"):
        check_point_in_nominal_coverage(70.0, 10.0)


def test_point_inside_coverage_returns_floats():
    assert check_point_in_nominal_coverage(30, -9) == (30.0, -9.0)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (float("nan"), 0.0),
        (0.0, float("inf")),
        ("30", 0.0),
        (None, 0.0),
        (True, 0.0),
        (91.0, 0.0),
        (0.0, 181.0),
    ],
)
def test_validate_coordinates_rejects(lat, lon):
    with pytest.raises(ValueError):
        validate_coordinates(lat, lon)


def test_month_before_record_start():
    with pytest.raises(OutsideCoverageError):
        check_month_available(YearMonth(1980, 12), today=TODAY)


def test_first_month_and_last_complete_month_ok():
    check_month_available(YearMonth(1981, 1), today=TODAY)
    check_month_available(YearMonth(2026, 9), today=TODAY)


@pytest.mark.parametrize("month", [YearMonth(2026, 10), YearMonth(2026, 11), YearMonth(2030, 1)])
def test_unfinished_or_future_month_unavailable(month):
    with pytest.raises(DataNotAvailableError):
        check_month_available(month, today=TODAY)


def test_month_is_unavailable_on_its_last_day():
    with pytest.raises(DataNotAvailableError):
        check_month_available(YearMonth(2026, 10), today=date(2026, 10, 31))