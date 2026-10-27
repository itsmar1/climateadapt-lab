import logging
import sys
import types

import pytest

from climateadapt.config import Settings
from climateadapt.data.cds_client import make_cds_client_factory, supported_options
from climateadapt.data.era5_land import build_era5_land_client
from climateadapt.data.errors import DataAccessError


class FullClient:
    def __init__(self, url=None, key=None, retry_max=500, sleep_max=120, timeout=60):
        self.options = {"retry_max": retry_max, "sleep_max": sleep_max, "timeout": timeout}


class TimeoutOnlyClient:
    def __init__(self, url=None, key=None, timeout=60):
        self.options = {"timeout": timeout}


class KwargsClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def install_fake_cdsapi(monkeypatch, client_class):
    monkeypatch.setitem(sys.modules, "cdsapi", types.SimpleNamespace(Client=client_class))


def test_supported_options_splits_by_signature():
    desired = {"retry_max": 2, "sleep_max": 15, "timeout": 30.0}
    assert supported_options(FullClient, desired) == (desired, [])
    assert supported_options(TimeoutOnlyClient, desired) == (
        {"timeout": 30.0},
        ["retry_max", "sleep_max"]
    )


def test_bare_kwargs_do_not_count_as_support():
    supported, unsupported = supported_options(KwargsClient, {"retry_max": 2})
    assert supported == {}
    assert unsupported == ["retry_max"]


def test_factory_passes_every_supported_option(monkeypatch):
    install_fake_cdsapi(monkeypatch, FullClient)
    client = make_cds_client_factory(retry_max=2, sleep_max_seconds=15.0, timeout_seconds=30.0)()
    assert client.options == {"retry_max": 2, "sleep_max": 15, "timeout": 30.0}


def test_factory_passes_only_what_exists_and_warns_about_the_rest(monkeypatch, caplog):
    install_fake_cdsapi(monkeypatch, TimeoutOnlyClient)
    with caplog.at_level(logging.WARNING):
        client = make_cds_client_factory(
            retry_max=2, sleep_max_seconds=15.0, timeout_seconds=30.0
        )()
    assert client.options == {"timeout": 30.0}
    assert "retry_max" in caplog.text and "sleep_max" in caplog.text


def test_factory_with_no_supported_options_still_builds_a_client(monkeypatch, caplog):
    install_fake_cdsapi(monkeypatch, KwargsClient)
    with caplog.at_level(logging.WARNING):
        client = make_cds_client_factory(
            retry_max=2, sleep_max_seconds=15.0, timeout_seconds=30.0
        )()
    assert client.kwargs == {}
    assert "defaults apply" in caplog.text


def test_missing_cdsapi_package_is_a_data_access_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "cdsapi", None)  # makes `import cdsapi` raise ImportError
    with pytest.raises(DataAccessError, match="cdsapi"):
        make_cds_client_factory(retry_max=2, sleep_max_seconds=15.0, timeout_seconds=30.0)()


def test_settings_are_wired_into_the_default_downloader(tmp_path, monkeypatch):
    seen = {}

    def fake_factory(**kwargs):
        seen.update(kwargs)
        return lambda: None

    monkeypatch.setattr("climateadapt.data.era5_land.make_cds_client_factory", fake_factory)
    build_era5_land_client(
        Settings(
            data_dir=tmp_path, cds_retry_max=2, cds_sleep_max_seconds=15, cds_timeout_seconds=30
        )
    )
    assert seen == {"retry_max": 2, "sleep_max_seconds": 15.0, "timeout_seconds": 30.0}


def test_default_retry_bounds_are_far_below_cdsapi_defaults():
    settings = Settings()
    assert settings.cds_retry_max < 500
    assert settings.cds_sleep_max_seconds <= 120