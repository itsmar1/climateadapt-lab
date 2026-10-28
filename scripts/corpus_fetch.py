"""Download the automatic-access PDFs of the corpus into data/corpus/raw/ (never into git).

    uv run python scripts/corpus_fetch.py
    uv run python scripts/corpus_fetch.py --only fao-wr45-drought-north-africa-near-east

Manual documents are listed with their landing page; download them yourself and save each as
data/corpus/raw/<doc_id>.pdf. Downloads are sequential and verified to be real PDFs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from climateadapt.config import get_settings
from climateadapt.rag.fetch import FetchError, fetch_pdf, raw_pdf_path
from climateadapt.rag.manifest import load_manifest

MANIFEST = Path("corpus/manifest.json")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="limit to these doc_ids")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    settings = get_settings()
    raw_dir = settings.data_dir / "corpus" / "raw"
    manifest = load_manifest(MANIFEST)
    documents = [d for d in manifest.documents if not args.only or d.doc_id in args.only]
    if not documents:
        print("No matching documents.")
        return 2

    failures = 0
    with httpx.Client(follow_redirects=True) as client:
        for doc in documents:
            target = raw_pdf_path(raw_dir, doc.doc_id)
            if doc.access == "manual":
                state = "present" if target.exists() else "MISSING"
                print(f"[manual {state}] {doc.doc_id}\n    download from: {doc.landing_url}\n"
                      f"    save as:       {target}")
                continue
            try:
                result = fetch_pdf(
                    doc,
                    raw_dir,
                    client,
                    user_agent=settings.http_user_agent,
                    timeout=settings.http_timeout_seconds,
                    force=args.force,
                )
            except FetchError as exc:
                failures += 1
                print(f"[FAILED] {doc.doc_id}: {exc}\n    save the PDF manually as {target} "
                      f"(landing page: {doc.landing_url})")
                continue
            note = "already present" if result.skipped_existing else f"from {result.source_url}"
            print(
                f"[ok] {doc.doc_id}  {result.size_bytes:,} bytes  "
                f"sha256={result.sha256[:12]}...  {note}"
            )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())