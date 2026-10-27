import numpy as np
import pytest

from climateadapt.data.chirps import BOUNDARY_LIMITATION, ChirpsV3Client
from climateadapt.data.errors import DataNotAvailableError, MissingDataError, OutsideCoverageError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import InsufficientReferenceError, compute_spi
from climateadapt.pipelines.spi import chirps_spi


def synthetic(year, month):
    return float(np.random.default_rng(year * 100 + month).gamma(2.5, 12.0))


def pairs_for(end_month, timescale, years, extra=()):
    """All (year, month) pairs in windows ending at end_month in the given years."""
    pairs = set(extra)
    for year in years:
        index = year * 12 + end_month - 1
        for offset in range(timescale):
            y, m0 = divmod(index - offset, 12)
            pairs.add((y, m0 + 1))
    return pairs


@pytest.fixture
def env(make_store, http_mock, cell_center):
    def build(routes, **overrides):
        http, calls = http_mock(routes)
        client = ChirpsV3Client(make_store(http))
        lat, lon = cell_center(5, 7)
        params = {
            "latitude": lat,
            "longitude": lon,
            "target_end_month": YearMonth(2024, 3),
            "timescale_months": 1,
            "reference_start_year": 1991,
            "reference_end_year": 2020,
        }
        params.update(overrides)
        return client, calls, params

    return build


@pytest.fixture
def one_month_routes(season_routes):
    pairs = pairs_for(3, 1, [*range(1991, 2021), 2024])
    return season_routes(pairs, synthetic)


def test_single_month_spi_matches_the_pure_calculation(env, one_month_routes):
    client, calls, params = env(one_month_routes)

    result = chirps_spi(client, **params)

    monthly = {YearMonth(y, 3): synthetic(y, 3) for y in [*range(1991, 2021), 2024]}
    expected = compute_spi(monthly, YearMonth(2024, 3), 1, 1991, 2020)
    assert result.status == "ok"
    assert result.spi == pytest.approx(expected.spi, abs=1e-3)
    assert result.cumulative_probability == pytest.approx(expected.cumulative_probability, abs=1e-3)
    assert result.window_total_mm == pytest.approx(synthetic(2024, 3), abs=1e-3)
    assert result.reference_years_used == 30
    assert result.reference_years_included == list(range(1991, 2021))
    assert result.reference_years_excluded == []
    assert result.target_in_reference_period is False
    assert result.point_on_cell_boundary is False
    assert result.target_window_start == result.target_window_end == "2024-03"
    assert len(result.source_files) == 31
    assert len(calls) == 31
    assert "G2JQ0P" in result.doi
    assert result.reference_spi_std > 0
    assert any("not a measure of agricultural drought damage" in t for t in result.limitations)
    dumped = result.model_dump()
    assert "severity" not in dumped and "category" not in dumped


def test_three_month_spi_uses_the_whole_window(env, season_routes):
    pairs = pairs_for(3, 3, [*range(1991, 2021), 2024])
    client, calls, params = env(season_routes(pairs, synthetic), timescale_months=3)

    result = chirps_spi(client, **params)

    assert result.target_window_start == "2024-01"
    assert result.target_window_end == "2024-03"
    expected_total = sum(synthetic(2024, m) for m in (1, 2, 3))
    assert result.window_total_mm == pytest.approx(expected_total, abs=1e-2)
    assert len(calls) == 93


def test_years_whose_window_starts_before_the_record_are_excluded(env, season_routes):
    # SPI-2 ending in January: the 1981 window needs December 1980, before the record.
    pairs = pairs_for(1, 2, [*range(1982, 2021), 2024])
    client, _, params = env(
        season_routes(pairs, synthetic),
        target_end_month=YearMonth(2024, 1),
        timescale_months=2,
        reference_start_year=1981,
    )

    result = chirps_spi(client, min_reference_years=30, **params)

    assert result.reference_years_used == 39
    assert [e.year for e in result.reference_years_excluded] == [1981]
    assert "before the CHIRPS v3 Final record begins" in result.reference_years_excluded[0].reason
    assert any("excluded" in text for text in result.limitations)


def test_short_reference_period_is_flagged(env, season_routes):
    pairs = pairs_for(3, 1, [*range(2001, 2021), 2024])
    client, _, params = env(
        season_routes(pairs, synthetic), reference_start_year=2001, min_reference_years=20
    )

    result = chirps_spi(client, **params)

    assert result.reference_years_used == 20
    assert any("only 20 usable years" in text for text in result.limitations)


def test_target_inside_the_reference_period_is_flagged(env, season_routes):
    pairs = pairs_for(3, 1, range(1991, 2021))
    client, _, params = env(
        season_routes(pairs, synthetic), target_end_month=YearMonth(2020, 3)
    )

    result = chirps_spi(client, **params)

    assert result.target_in_reference_period is True
    assert any("contributed to its own calibration" in text for text in result.limitations)


def test_too_many_missing_reference_years_raise(env, season_routes):
    pairs = pairs_for(3, 1, [*range(1991, 2021), 2024])
    routes = season_routes(pairs, synthetic, missing={(y, 3) for y in (1995, 1996, 1997, 1998)})
    client, _, params = env(routes)

    with pytest.raises(InsufficientReferenceError, match="Only 26 of 30"):
        chirps_spi(client, **params)


def test_missing_reference_years_are_reported_when_the_minimum_allows(env, season_routes):
    pairs = pairs_for(3, 1, [*range(1991, 2021), 2024])
    routes = season_routes(pairs, synthetic, missing={(y, 3) for y in (1995, 1996)})
    client, _, params = env(routes)

    result = chirps_spi(client, min_reference_years=20, **params)

    assert result.reference_years_used == 28
    assert [e.year for e in result.reference_years_excluded] == [1995, 1996]
    assert "missing data" in result.reference_years_excluded[0].reason


def test_missing_target_value_stops_before_reading_the_reference(env, season_routes):
    pairs = pairs_for(3, 1, [*range(1991, 2021), 2024])
    routes = season_routes(pairs, synthetic, missing={(2024, 3)})
    client, calls, params = env(routes)

    with pytest.raises(MissingDataError, match="2024-03"):
        chirps_spi(client, **params)
    assert len(calls) == 1


def test_all_zero_reference_totals_are_an_insufficient_reference(env, season_routes):
    pairs = pairs_for(3, 1, [*range(1991, 2021), 2024])
    client, _, params = env(season_routes(pairs, lambda y, m: 0.0 if y < 2024 else 10.0))

    with pytest.raises(InsufficientReferenceError, match="non-zero"):
        chirps_spi(client, **params)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"target_end_month": YearMonth(2026, 10)}, DataNotAvailableError),
        ({"reference_end_year": 2027}, DataNotAvailableError),
        ({"target_end_month": YearMonth(1980, 12)}, OutsideCoverageError),
        ({"latitude": 70.0, "longitude": 10.0}, OutsideCoverageError),
        ({"timescale_months": 0}, ValueError),
        ({"reference_start_year": 2020, "reference_end_year": 1991}, ValueError),
    ],
)
def test_invalid_requests_make_no_requests(env, one_month_routes, overrides, error):
    client, calls, params = env(one_month_routes, **overrides)
    with pytest.raises(error):
        chirps_spi(client, **params)
    assert calls == []


def test_point_on_a_cell_edge_is_flagged(env, season_routes):
    pairs = pairs_for(3, 1, [*range(1991, 2021), 2024])
    client, _, params = env(
        season_routes(pairs, synthetic), latitude=30.0, longitude=-9.5
    )

    result = chirps_spi(client, **params)

    assert result.point_on_cell_boundary is True
    assert result.limitations[0] == BOUNDARY_LIMITATION