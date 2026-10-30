"""Offline tests for the Baseten settings. No network, no real credentials.

The fake key values below are obviously not real keys. Tests chdir to an empty
directory so a developer's real .env can never leak into assertions.
"""

from __future__ import annotations

import pytest

from climateadapt.config import Settings

PREFIXED = "CLIMATEADAPT_BASETEN_API_KEY"
UNPREFIXED = "BASETEN_API_KEY"


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(PREFIXED, raising=False)
    monkeypatch.delenv(UNPREFIXED, raising=False)
    monkeypatch.delenv("CLIMATEADAPT_BASETEN_BASE_URL", raising=False)
    monkeypatch.delenv("CLIMATEADAPT_BASETEN_MODEL_ID", raising=False)


def test_baseten_defaults():
    settings = Settings()
    assert settings.baseten_base_url == "https://inference.baseten.co/v1"
    assert settings.baseten_model_id == "meta-models/muse-spark-open-1026"
    assert settings.baseten_api_key is None


def test_prefixed_key_name_loads(monkeypatch):
    monkeypatch.setenv(PREFIXED, "sk-test-prefixed")
    settings = Settings()
    assert settings.baseten_api_key is not None
    assert settings.baseten_api_key.get_secret_value() == "sk-test-prefixed"


def test_unprefixed_key_name_loads(monkeypatch):
    monkeypatch.setenv(UNPREFIXED, "sk-test-unprefixed")
    settings = Settings()
    assert settings.baseten_api_key is not None
    assert settings.baseten_api_key.get_secret_value() == "sk-test-unprefixed"


def test_prefixed_key_name_wins_when_both_are_set(monkeypatch):
    monkeypatch.setenv(PREFIXED, "sk-test-prefixed")
    monkeypatch.setenv(UNPREFIXED, "sk-test-unprefixed")
    assert Settings().baseten_api_key.get_secret_value() == "sk-test-prefixed"


def test_key_is_never_exposed_by_repr_or_dump(monkeypatch):
    monkeypatch.setenv(PREFIXED, "sk-test-supersecret")
    settings = Settings()
    assert repr(settings.baseten_api_key) == "SecretStr('**********')"
    assert "sk-test-supersecret" not in repr(settings)
    assert "sk-test-supersecret" not in str(settings.model_dump())
    assert "sk-test-supersecret" not in settings.model_dump_json()


def test_base_url_and_model_id_are_overridable(monkeypatch):
    monkeypatch.setenv("CLIMATEADAPT_BASETEN_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("CLIMATEADAPT_BASETEN_MODEL_ID", "meta-models/muse-spark-open")
    settings = Settings()
    assert settings.baseten_base_url == "https://example.invalid/v1"
    assert settings.baseten_model_id == "meta-models/muse-spark-open"
