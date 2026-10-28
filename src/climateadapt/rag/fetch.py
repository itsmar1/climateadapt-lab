"""Polite, verified PDF download into data/corpus/raw/ (never into the repository)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from climateadapt.rag.ingest import sha256_file
from climateadapt.rag.manifest import SourceDocument

MAX_PDF_BYTES = 300 * 1024 * 1024
DEFAULT_USER_AGENT = "climateadapt-lab/0.1 (research prototype)"


class FetchError(Exception):
    """A PDF could not be downloaded or verified."""


class FetchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    path: str
    source_url: str
    sha256: str
    size_bytes: int
    skipped_existing: bool


def raw_pdf_path(raw_dir: Path, doc_id: str) -> Path:
    return raw_dir / f"{doc_id}.pdf"


def _download(
    doc: SourceDocument,
    url: str,
    target: Path,
    client: httpx.Client,
    *,
    user_agent: str,
    timeout: float,
    max_bytes: int,
) -> FetchResult:
    tmp = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    size = 0
    head = bytearray()
    try:
        with client.stream(
            "GET", url, headers={"User-Agent": user_agent}, timeout=timeout
        ) as response:
            if response.status_code != 200:
                raise FetchError(f"HTTP {response.status_code}")
            content_type = response.headers.get("content-type")
            final_url = str(response.url)
            with open(tmp, "wb") as handle:
                for block in response.iter_bytes():
                    if len(head) < 5:
                        head += block[: 5 - len(head)]
                        if len(head) >= 5 and not head.startswith(b"%PDF-"):
                            raise FetchError(f"not a PDF (content-type {content_type!r})")
                    size += len(block)
                    if size > max_bytes:
                        raise FetchError(f"file exceeds the {max_bytes}-byte limit")
                    handle.write(block)
                    digest.update(block)
        if not head.startswith(b"%PDF-"):
            raise FetchError(f"not a PDF (content-type {content_type!r})")
        os.replace(tmp, target)
    except httpx.HTTPError as exc:
        raise FetchError(f"network error: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)

    result = FetchResult(
        doc_id=doc.doc_id,
        path=str(target),
        source_url=final_url,
        sha256=digest.hexdigest(),
        size_bytes=size,
        skipped_existing=False,
    )
    sidecar = target.with_name(f"{doc.doc_id}.source.json")
    sidecar.write_text(
        json.dumps(
            {
                **result.model_dump(),
                "requested_url": url,
                "content_type": content_type,
                "retrieved_at_utc": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return result


def fetch_pdf(
    doc: SourceDocument,
    raw_dir: Path,
    client: httpx.Client,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 60.0,
    force: bool = False,
    max_bytes: int = MAX_PDF_BYTES,
) -> FetchResult:
    """Download the first candidate URL that returns a real PDF."""
    if doc.access != "automatic":
        raise FetchError(f"{doc.doc_id} is a manual download; see {doc.landing_url}.")
    target = raw_pdf_path(raw_dir, doc.doc_id)
    if target.exists() and not force:
        sha, size = sha256_file(target)
        return FetchResult(
            doc_id=doc.doc_id,
            path=str(target),
            source_url="",
            sha256=sha,
            size_bytes=size,
            skipped_existing=True,
        )
    raw_dir.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    for url in doc.pdf_urls:
        try:
            return _download(
                doc, url, target, client, 
                user_agent=user_agent, timeout=timeout, max_bytes=max_bytes
            )
        except FetchError as exc:
            problems.append(f"{url}: {exc}")
    raise FetchError("All candidate URLs failed. " + " | ".join(problems))