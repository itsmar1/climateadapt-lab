"""Download pinned CropHarvest v14 files from Zenodo (stdlib only).

Fetches ``labels.geojson``, ``features.tar.gz`` and ``test_features.tar.gz``
for record 10251170 into ``data/cropharvest/``, verifying size + md5 from
:mod:`climateadapt.vision.constants` and extracting the archives.
Honours ``CLIMATEADAPT_ALLOW_DOWNLOADS=false`` (refuses to download).

PowerShell::

    uv run python scripts/vision_download.py
    uv run python scripts/vision_download.py --files labels features
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tarfile
import urllib.request
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.vision.constants import DATASET_VERSION_ID, ZENODO_FILES

FILE_ALIASES = {"labels": "labels.geojson", "features": "features.tar.gz",
                "test_features": "test_features.tar.gz"}


def _h5_dir(base: Path, name: str) -> Path | None:
    """Directory actually holding .h5 files (`<name>/arrays/` or `<name>/`)."""
    for candidate in (base / name / "arrays", base / name):
        if candidate.is_dir() and any(candidate.glob("*.h5")):
            return candidate
    return None


def _archive_h5_count(archive_path: Path) -> int:
    """Count `.h5` members inside a tar.gz (verifies completeness)."""
    with tarfile.open(archive_path, "r:gz") as archive:
        return sum(1 for member in archive if member.name.endswith(".h5"))


def _md5(path: Path) -> str:
    digest = hashlib.md5()  # hex check against Zenodo metadata, not security
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, timeout: float, user_agent: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(request, timeout=timeout) as response, open(tmp, "wb") as out:
        total = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            total += len(chunk)
            if total % (50 << 20) < (1 << 20):
                print(f"  ... {total / 2**20:.0f} MB", flush=True)
    tmp.replace(dest)
    print(f"  saved {dest} ({dest.stat().st_size / 2**20:.1f} MB)")


def main(argv: list[str] | None = None) -> int:
    """Download + verify + extract the requested CropHarvest files."""
    parser = argparse.ArgumentParser(description="Download pinned CropHarvest v14 files.")
    parser.add_argument("--data-dir", default=None, help="Target dir (default: data/cropharvest).")
    parser.add_argument("--record-id", type=int, default=DATASET_VERSION_ID)
    parser.add_argument("--files", nargs="+", choices=sorted(FILE_ALIASES),
                        default=["labels", "features", "test_features"])
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.allow_downloads:
        print("refusing: CLIMATEADAPT_ALLOW_DOWNLOADS=false", file=sys.stderr)
        return 2
    data_dir = Path(args.data_dir) if args.data_dir else settings.data_dir / "cropharvest"
    data_dir.mkdir(parents=True, exist_ok=True)
    pinned = args.record_id == DATASET_VERSION_ID
    if not pinned:
        print(f"WARNING: record {args.record_id} is not the pinned v14 "
              f"({DATASET_VERSION_ID}); skipping hash checks.")

    for alias in args.files:
        name = FILE_ALIASES[alias]
        dest = data_dir / name
        expected_size, expected_md5 = ZENODO_FILES[name]
        if dest.is_file() and pinned:
            size = dest.stat().st_size
            if size == expected_size and _md5(dest) == expected_md5:
                print(f"cached {name} ({size / 2**20:.1f} MB, md5 ok)")
            else:
                print(f"re-downloading {name} (cached copy failed verification)")
                _download(f"https://zenodo.org/api/records/{args.record_id}/files/{name}/content",
                          dest, settings.http_timeout_seconds, settings.http_user_agent)
        else:
            print(f"downloading {name} ...")
            _download(f"https://zenodo.org/api/records/{args.record_id}/files/{name}/content",
                      dest, settings.http_timeout_seconds, settings.http_user_agent)
        if pinned:
            size = dest.stat().st_size
            digest = _md5(dest)
            if size != expected_size or digest != expected_md5:
                print(f"integrity failure for {name}: size={size} md5={digest}", file=sys.stderr)
                return 1
            print(f"verified {name} ({size / 2**20:.1f} MB, md5 {digest[:12]}...)")
        if name.endswith(".tar.gz"):
            dirname = "features" if alias == "features" else "test_features"
            marker = data_dir / f".{dirname}.extracted_ok"
            have = _h5_dir(data_dir, dirname)
            if have is not None and marker.is_file():
                print(f"extracted {have}/ already verified; skipping ({marker.name})")
            else:
                print(f"extracting {name} ...")
                with tarfile.open(dest, "r:gz") as archive:
                    archive.extractall(path=data_dir, filter="data")
                found = sorted(data_dir.glob("*.h5"))
                if found and _h5_dir(data_dir, dirname) is None:
                    target = data_dir / dirname
                    target.mkdir(parents=True, exist_ok=True)
                    for item in found:
                        item.rename(target / item.name)
                have = _h5_dir(data_dir, dirname)
                if have is None:
                    top = sorted(p.name for p in data_dir.iterdir())[:15]
                    print(f"unexpected archive layout for {name}; top level: {top}",
                          file=sys.stderr)
                    return 1
                expected = _archive_h5_count(dest)
                got = len(list(have.glob("*.h5")))
                print(f"  {have}/ holds {got} .h5 files (archive lists {expected})")
                if got != expected:
                    print(f"incomplete extraction for {name}: {got} != {expected}",
                          file=sys.stderr)
                    return 1
                marker.write_text(f"{expected}\n", encoding="utf-8")
    print(f"done: {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
