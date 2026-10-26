import pytest

from climateadapt.data.chirps import ChirpsV3Client
from climateadapt.data.errors import (
    DataNotAvailableError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.data.periods import YearMonth
from climateadapt.pipelines.rainfall_anomaly import (
    InsufficientBaselineError,
    chirps_rainfall_anomaly,
    season_window,
)

MAM = (3, 4, 5)


def mam_pairs(years):
    return [(y, m) for y in years for m in MAM]


@pytest.fixture
def env(make_store, http_mock, cell_center):
    """Return (client, calls, default_params) for a route table."""

    def build(routes, **overrides):
        http, calls = http_mock(routes)
        client = ChirpsV3Client(make_store(http))
        lat, lon = cell_center(5, 7)
        params = {
            "latitude": lat,
            "longitude": lon,
            "observed_start": YearMonth(2024, 3),
            "window_months_count": 3,
            "baseline_start_year": 2011,
            "baseline_end_year": 2020,
        }
        params.update(overrides)
        return client, calls, params

    return build


def standard_routes(season_routes):
    """Baseline 2011-2020 MAM = 30 mm/month; observed 2024 MAM = 24 mm/month."""
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    return season_routes(pairs, lambda y, m: 24.0 if y == 2024 else 30.0)


# ------------------------------------------------------------------ windows


def test_season_window_within_year():
    assert season_window(YearMonth(2024, 3), 3) == (YearMonth(2024, 3), YearMonth(2024, 5))


def test_season_window_crosses_year_boundary():
    assert season_window(YearMonth(2023, 11), 3) == (YearMonth(2023, 11), YearMonth(2024, 1))


def test_season_window_single_month():
    assert season_window(YearMonth(2024, 7), 1) == (YearMonth(2024, 7), YearMonth(2024, 7))


@pytest.mark.parametrize("bad", [0, 13, -1, True, 2.5, "3"])
def test_season_window_rejects_bad_length(bad):
    with pytest.raises(ValueError):
        season_window(YearMonth(2024, 1), bad)


# ------------------------------------------------------------------ results


def test_basic_anomaly(season_routes, env):
    client, calls, params = env(standard_routes(season_routes))

    result = chirps_rainfall_anomaly(client, **params)

    assert result.status == "ok"
    assert result.observed_total_mm == pytest.approx(72.0)
    assert result.baseline_mean_mm == pytest.approx(90.0)
    assert result.percentage_anomaly == pytest.approx(-20.0)
    assert result.absolute_difference_mm == pytest.approx(-18.0)
    assert result.direction == "below_baseline"
    assert result.observed_window_start == "2024-03"
    assert result.observed_window_end == "2024-05"
    assert result.baseline_years_used == 10
    assert len(result.baseline_totals) == 10
    assert result.baseline_excluded == []
    assert result.baseline_includes_observed_period is False
    assert len(result.source_files) == 33
    assert len(calls) == 33
    assert "G2JQ0P" in result.doi
    assert result.citation
    dumped = result.model_dump()
    assert "severity" not in dumped and "drought_class" not in dumped
    assert any("not a calibrated drought index" in text for text in result.limitations)
    assert any("30-year" in text for text in result.limitations)


def test_window_crossing_year_boundary_uses_matching_baseline_windows(season_routes, env):
    baseline_pairs = [
        pair
        for y in range(2011, 2021)
        for pair in ((y, 11), (y, 12), (y + 1, 1))
    ]
    observed_pairs = [(2023, 11), (2023, 12), (2024, 1)]

    def value(year, month):
        season_year = year if month >= 11 else year - 1
        return 20.0 if season_year == 2023 else 10.0 + (season_year - 2011)

    routes = season_routes(baseline_pairs + observed_pairs, value)
    client, _, params = env(routes, observed_start=YearMonth(2023, 11))

    result = chirps_rainfall_anomaly(client, **params)

    assert result.observed_window_start == "2023-11"
    assert result.observed_window_end == "2024-01"
    assert result.observed_total_mm == pytest.approx(60.0)
    assert result.baseline_mean_mm == pytest.approx(43.5)  # 3 * mean(10..19)
    assert result.percentage_anomaly == pytest.approx((60.0 - 43.5) / 43.5 * 100.0)
    assert result.direction == "above_baseline"
    assert result.baseline_totals[0].window_end == "2012-01"


def test_incomplete_baseline_year_is_excluded_not_imputed(season_routes, env):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(
        pairs, lambda y, m: 24.0 if y == 2024 else 30.0, missing={(2015, 4)}
    )
    client, _, params = env(routes)

    result = chirps_rainfall_anomaly(client, min_baseline_years=5, **params)

    assert result.baseline_years_used == 9
    assert [e.season_year for e in result.baseline_excluded] == [2015]
    assert "2015-04" in result.baseline_excluded[0].reason
    assert result.baseline_mean_mm == pytest.approx(90.0)
    assert any("excluded" in text for text in result.limitations)


def test_too_few_complete_years_raises(season_routes, env):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(
        pairs, lambda y, m: 24.0 if y == 2024 else 30.0, missing={(2015, 4)}
    )
    client, _, params = env(routes)

    with pytest.raises(InsufficientBaselineError, match="Only 9 of 10"):
        chirps_rainfall_anomaly(client, **params)


def test_missing_observed_month_raises(season_routes, env):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(
        pairs, lambda y, m: 24.0 if y == 2024 else 30.0, missing={(2024, 4)}
    )
    client, _, params = env(routes)

    with pytest.raises(MissingDataError, match="2024-04"):
        chirps_rainfall_anomaly(client, **params)


def test_zero_baseline_is_explicitly_undefined(season_routes, env):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(pairs, lambda y, m: 10.0 if y == 2024 else 0.0)
    client, _, params = env(routes)

    result = chirps_rainfall_anomaly(client, **params)

    assert result.status == "undefined"
    assert result.percentage_anomaly is None
    assert result.baseline_mean_mm == 0.0
    assert "undefined" in result.message.lower()


def test_baseline_overlapping_observed_window_is_flagged(season_routes, env):
    routes = season_routes(mam_pairs(range(2015, 2025)), lambda y, m: 30.0)
    client, _, params = env(routes, baseline_start_year=2015, baseline_end_year=2024)

    result = chirps_rainfall_anomaly(client, **params)

    assert result.baseline_includes_observed_period is True
    assert any("includes the observation window" in text for text in result.limitations)


# ------------------------------------------------------------------ fail-fast (no requests)


def test_baseline_beyond_available_data_makes_no_requests(season_routes, env):
    client, calls, params = env(standard_routes(season_routes), baseline_end_year=2027)
    with pytest.raises(DataNotAvailableError):
        chirps_rainfall_anomaly(client, **params)
    assert calls == []


def test_baseline_before_record_start_makes_no_requests(season_routes, env):
    client, calls, params = env(standard_routes(season_routes), baseline_start_year=1975)
    with pytest.raises(OutsideCoverageError):
        chirps_rainfall_anomaly(client, **params)
    assert calls == []


def test_observed_window_in_the_future_makes_no_requests(season_routes, env):
    client, calls, params = env(
        standard_routes(season_routes), observed_start=YearMonth(2026, 9)
    )
    with pytest.raises(DataNotAvailableError):
        chirps_rainfall_anomaly(client, **params)
    assert calls == []


def test_point_outside_coverage_makes_no_requests(season_routes, env):
    client, calls, params = env(standard_routes(season_routes), latitude=70.0, longitude=10.0)
    with pytest.raises(OutsideCoverageError):
        chirps_rainfall_anomaly(client, **params)
    assert calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"baseline_start_year": 2020, "baseline_end_year": 2011},
        {"window_months_count": 0},
        {"min_baseline_years": 1},
        {"min_baseline_years": 11},
        {"baseline_start_year": 2011.0},
    ],
)
def test_invalid_parameters_make_no_requests(season_routes, env, overrides):
    client, calls, params = env(standard_routes(season_routes))
    params.update(overrides)
    with pytest.raises(ValueError):
        chirps_rainfall_anomaly(client, **params)
    assert calls == []