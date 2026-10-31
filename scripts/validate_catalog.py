"""Validate the intervention catalog against the manifest and ingested corpus.

    uv run python scripts/validate_catalog.py
    uv run python scripts/validate_catalog.py --require-ingested

Offline: reads corpus/manifest.json, the packaged catalog (or --catalog), and
page counts/emptiness from data/corpus/processed (never the text itself beyond
an emptiness check). Exit 0 when no errors were found (warnings allowed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from climateadapt.rag.manifest import load_manifest
from climateadapt.rag.models import Page
from climateadapt.rag.text import normalize_text
from climateadapt.recommend.loader import load_catalog
from climateadapt.recommend.validate import IngestedDocInfo, validate_catalog

MANIFEST = Path("corpus/manifest.json")
PROCESSED_DIR = Path("data/corpus/processed")


def _ingested_info(processed_dir: Path) -> dict[str, IngestedDocInfo] | None:
    if not processed_dir.exists():
        return None
    ingested: dict[str, IngestedDocInfo] = {}
    for meta_path in sorted(processed_dir.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pages_path = meta_path.parent / "pages.jsonl"
        empty: set[int] = set()
        if pages_path.exists():
            for line in pages_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    page = Page.model_validate_json(line)
                    if not normalize_text(page.text):
                        empty.add(page.page)
        ingested[meta_path.parent.name] = IngestedDocInfo(
            n_pages=int(meta["n_pages"]), empty_pages=frozenset(empty)
        )
    return ingested


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the intervention catalog.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument(
        "--require-ingested",
        action="store_true",
        help="Fail when the processed corpus is missing instead of skipping those checks.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"manifest error: {exc}")
        return 1
    try:
        catalog = load_catalog(args.catalog)
    except (OSError, ValueError) as exc:
        print(f"catalog error: {exc}")
        return 1

    ingested = _ingested_info(args.processed_dir)
    if ingested is None and args.require_ingested:
        print(f"processed corpus not found: {args.processed_dir}")
        return 1

    report = validate_catalog(catalog, manifest, ingested)
    for issue in (*report.errors, *report.warnings):
        where = f"[{issue.entry}] " if issue.entry else ""
        print(f"{issue.level}: {where}{issue.message}")
    print(
        f"catalog v{catalog.catalog_version}: {report.checked_entries} entries, "
        f"{len(report.errors)} errors, {len(report.warnings)} warnings."
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
