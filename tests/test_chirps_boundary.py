import pytest

from climateadapt.data.chirps import (
    BOUNDARY_LIMITATION,
    ChirpsV3Client,
    sample_point,
)
from climateadapt.data.periods import YearMonth
from climateadapt.pipelines.rainfall_anomaly import chirps_rainfall_anomaly

# Synthetic grid: west -10.0, north 31.0, 0.05 degree cells (see conftest).
EDGE_AND_CORNER_POINTS = [
    (30.0, -9.5),  # corner: both a row edge and a column edge
    (30.0, -9.525),  # row edge only
    (30.025, -9.5),  # column edge only
]


@pytest.mark.parametrize(("lat", "lon"), EDGE_AND_CORNER_POINTS)
def test_point_on_an_edge_or_corner_is_flagged(tmp_path, tif_factory, lat, lon):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory())
    assert sample_point(path, lat, lon).on_cell_boundary is True


def test_cell_centre_and_interior_points_are_not_flagged(tmp_path, tif_factory, cell_center):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory())
    lat, lon = cell_center(5, 7)

    assert sample_point(path, lat, lon).on_cell_boundary is False
    assert sample_point(path, lat + 0.01, lon - 0.01).on_cell_boundary is False
    assert sample_point(path, 30.01, -9.51).on_cell_boundary is False


def test_series_reports_the_flag_and_limitation(tif_factory, http_mock, make_store, cell_center):
    routes = {"chirps-v3.0.2024.01.tif": tif_factory(), "chirps-v3.0.2024.02.tif": tif_factory()}
    http, _ = http_mock(routes)
    client = ChirpsV3Client(make_store(http))

    flagged = client.monthly_point_series(30.0, -9.5, YearMonth(2024, 1), YearMonth(2024, 2))
    centred = client.monthly_point_series(
        *cell_center(5, 7), YearMonth(2024, 1), YearMonth(2024, 2)
    )

    assert flagged.point_on_cell_boundary is True
    assert BOUNDARY_LIMITATION in flagged.limitations
    assert centred.point_on_cell_boundary is False
    assert BOUNDARY_LIMITATION not in centred.limitations


def test_pipeline_reports_the_flag_and_limitation(season_routes, http_mock, make_store):
    pairs = [(y, m) for y in range(2011, 2021) for m in (3, 4, 5)]
    pairs += [(2024, m) for m in (3, 4, 5)]
    http, _ = http_mock(season_routes(pairs, lambda y, m: 24.0 if y == 2024 else 30.0))
    client = ChirpsV3Client(make_store(http))

    result = chirps_rainfall_anomaly(
        client,
        latitude=30.0,
        longitude=-9.5,
        observed_start=YearMonth(2024, 3),
        window_months_count=3,
        baseline_start_year=2011,
        baseline_end_year=2020,
    )

    assert result.status == "ok"
    assert result.point_on_cell_boundary is True
    assert result.limitations[0] == BOUNDARY_LIMITATION