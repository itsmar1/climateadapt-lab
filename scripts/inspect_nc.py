"""Print the structure and every grid value of a small NetCDF file (no network needed).

    uv run python scripts/inspect_nc.py "data\\cache\\era5_land\\raw\\19dd3da20aa42dbf.nc"

Use it to see exactly what the Copernicus CDS returned: variable names, units, the grid,
and which grid points are NaN (for example, points ERA5-Land treats as sea).
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import xarray as xr

TIME_NAMES = ("valid_time", "time")
LAT_NAMES = ("latitude", "lat")
LON_NAMES = ("longitude", "lon")


def _first_present(dataset: xr.Dataset, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in dataset.variables:
            return name
    return None


def _print_grid(values: np.ndarray, lats: np.ndarray, lons: np.ndarray) -> None:
    print("           " + " ".join(f"{lon:>10.2f}" for lon in lons))
    for lat, row in zip(lats, values, strict=True):
        cells = " ".join(f"{v:>10.6f}" if not np.isnan(v) else f"{'NaN':>10}" for v in row)
        print(f"  {lat:>8.2f} {cells}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path")
    args = parser.parse_args()

    with xr.open_dataset(args.path) as dataset:
        print(f"dimensions:        {dict(dataset.sizes)}")
        print(f"coordinates:       {list(dataset.coords)}")
        print(f"global attributes: {dict(dataset.attrs)}")

        time_name = _first_present(dataset, TIME_NAMES)
        lat_name = _first_present(dataset, LAT_NAMES)
        lon_name = _first_present(dataset, LON_NAMES)
        if time_name is None or lat_name is None or lon_name is None:
            print("Could not identify the time/latitude/longitude coordinates.")
            return 1

        lats = np.atleast_1d(dataset[lat_name].values)
        lons = np.atleast_1d(dataset[lon_name].values)
        print(f"{lat_name}: {lats}")
        print(f"{lon_name}: {lons}")

        for name, variable in dataset.data_vars.items():
            print(
                f"\nvariable {name!r}: dims={variable.dims} shape={variable.shape} "
                f"dtype={variable.dtype}"
            )
            print(f"  attributes: {dict(variable.attrs)}")
            share = float(np.isnan(np.asarray(variable.values, dtype='float64')).mean())
            print(f"  share of NaN values overall: {share:.3f}")

            for index, stamp in enumerate(np.atleast_1d(dataset[time_name].values)):
                slab = variable
                for dim in list(slab.dims):
                    if dim in (lat_name, lon_name):
                        continue
                    slab = slab.isel({dim: index if dim == time_name else 0})
                if lat_name not in slab.dims or lon_name not in slab.dims:
                    print("  (variable has no latitude/longitude grid; skipped)")
                    break
                values = np.asarray(slab.transpose(lat_name, lon_name).values, dtype="float64")
                print(f"  time step {np.datetime_as_string(stamp, unit='D')}:")
                _print_grid(values, lats, lons)
    return 0


if __name__ == "__main__":
    sys.exit(main())