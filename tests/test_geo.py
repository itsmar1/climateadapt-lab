import pytest

from climateadapt.geo import haversine_km


def test_identical_points_are_zero_apart():
    assert haversine_km(30.4, -9.6, 30.4, -9.6) == 0.0


def test_one_degree_of_latitude():
    assert haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.195, rel=1e-4)


def test_one_degree_of_longitude_shrinks_with_latitude():
    assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.195, rel=1e-4)
    assert haversine_km(60.0, 0.0, 60.0, 1.0) == pytest.approx(55.6, rel=2e-3)


def test_distance_is_symmetric():
    forward = haversine_km(30.43, -9.61, 30.5, -9.6)
    backward = haversine_km(30.5, -9.6, 30.43, -9.61)
    assert forward == pytest.approx(backward)


def test_antipodal_points_are_half_the_circumference():
    assert haversine_km(0.0, 0.0, 0.0, 180.0) == pytest.approx(20015.09, rel=1e-4)


def test_distance_across_the_antimeridian_is_short():
    assert haversine_km(0.0, 179.5, 0.0, -179.5) == pytest.approx(111.195, rel=1e-4)