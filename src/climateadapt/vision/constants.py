"""Pinned CropHarvest-data constants for the P16 vision baseline.

Every value below was read from a primary source on 2026-11-01 (URLs and
access dates in ``docs/VISION_BASELINE.md`` §1): the Zenodo API record,
``cropharvest/config.py`` and ``cropharvest/bands.py`` at ``main``.

The ``cropharvest`` PyPI package itself is NOT used: version 0.7.0 pins
``pandas<2``, ``geopandas==0.9.0`` and ``xarray<0.20``, which would
downgrade this project's working stack. Only documented data facts are
reused here, with our own minimal loader in :mod:`loader`.
"""

from __future__ import annotations

DATASET_VERSION_ID = 10251170
DATASET_VERSION_LABEL = "v14"
DATASET_DOI = "10.5281/zenodo.10251170"
DATASET_CONCEPT_DOI = "10.5281/zenodo.5021761"
DATASET_URL = f"https://zenodo.org/records/{DATASET_VERSION_ID}"
LICENCE_SPDX = "CC-BY-SA-4.0"
LICENCE_URL = "https://github.com/nasaharvest/cropharvest/blob/main/LICENSE.txt"
CITATION_KEY = "tseng2021cropharvest"
CITATION_TITLE = "CropHarvest: A global dataset for crop-type classification"
CITATION_AUTHORS = "Gabriel Tseng, Ivan Zvonkov, Catherine Lilian Nakalembe, Hannah Kerner"
CITATION_VENUE = "NeurIPS Datasets and Benchmarks Track (Round 2), 2021"
CITATION_URL = "https://openreview.net/forum?id=JtjzUXPEaCu"

# (size in bytes, md5) from the Zenodo API record 10251170. ``eo_data.tar.gz``
# (~26.7 GB of raw GeoTIFFs) is intentionally not used: ``features.tar.gz``
# already holds the processed model-ready arrays.
ZENODO_FILES: dict[str, tuple[int, str]] = {
    "labels.geojson": (85689847, "54a5070f103bc3e635afba27c139ac8d"),
    "features.tar.gz": (82479907, "d757e6c32cb6d65aa517f003607f6f81"),
    "test_features.tar.gz": (786061051, "be1d9e07ee69c7ef6a316a0edb3432bf"),
}

# Channel order of the ``array`` dataset in each ``.h5`` feature file, from
# cropharvest/bands.py: dynamic S1 (VV, VH) + S2 without B1/B10 + ERA5, then
# static SRTM (elevation, slope), then NDVI. Each array is (12, 18): 12
# monthly timesteps x 18 bands.
BAND_NAMES: tuple[str, ...] = (
    "VV",
    "VH",
    "B2",
    "B3",
    "B4",
    "B5",
    "B6",
    "B7",
    "B8",
    "B8A",
    "B9",
    "B11",
    "B12",
    "temperature_2m",
    "total_precipitation",
    "elevation",
    "slope",
    "NDVI",
)
N_TIMESTEPS = 12
N_BANDS = len(BAND_NAMES)
H5_DATASET = "array"

# Official held-out evaluation splits from cropharvest/config.py. Splitting
# in this package keys off the ``is_test`` label flag plus the directory a
# feature file was found in; these constants document what those flags mean.
TEST_DATASETS: dict[str, str] = {"Togo": "togo-eval", "People's Republic of China": "china-crop"}
TEST_REGIONS: dict[str, dict[str, float]] = {
    "Kenya_maize_2020_0": {"min_lat": 0.47190, "max_lat": 0.47749,
                            "min_lon": 34.22847, "max_lon": 34.23266},
    "Kenya_maize_2020_1": {"min_lat": 0.69365, "max_lat": 0.69767,
                            "min_lon": 34.36586, "max_lon": 34.37199},
    "Brazil_coffee_2020_0": {"min_lat": -12.1995, "max_lat": -12.1226,
                              "min_lon": -45.8238, "max_lon": -45.7579},
    "Brazil_coffee_2021_0": {"min_lat": -12.1995, "max_lat": -12.1226,
                              "min_lon": -45.8238, "max_lon": -45.7579},
}

DEFAULT_SEED = 42
