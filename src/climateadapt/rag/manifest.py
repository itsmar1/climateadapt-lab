"""Curated source manifest: the single source of truth for citations.

Citation metadata (titles, authors, licences, URLs) is NEVER invented by code. Each entry lists
the fields that could not be verified when it was written (``unverified_fields``).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DOC_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{2,80}$"
_URL = re.compile(r"^https?://\S+$")

SourceType = Literal[
    "guidance", "technical_report", "peer_reviewed", "dataset_documentation", "method_guide"
]
LicenseStatus = Literal["verified_in_record", "stated_in_document", "unverified"]
Access = Literal["automatic", "manual"]


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(pattern=DOC_ID_PATTERN)
    title: str = Field(min_length=3)
    authors: list[str]
    publisher: str = Field(min_length=2)
    year: int | None = Field(default=None, ge=1900, le=2100)
    series: str | None = None
    identifier: str | None = None
    source_type: SourceType
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    topics: list[str]
    regions: list[str] = Field(default_factory=list)
    landing_url: str
    pdf_urls: list[str] = Field(default_factory=list)
    access: Access
    license: str = Field(min_length=2)
    license_status: LicenseStatus
    license_notes: str | None = None
    unverified_fields: list[str] = Field(default_factory=list)
    verification_notes: str = Field(min_length=10)
    metadata_verified_on: date

    @field_validator("landing_url")
    @classmethod
    def _landing_is_url(cls, value: str) -> str:
        if not _URL.match(value):
            raise ValueError(f"not an http(s) URL: {value!r}")
        return value

    @field_validator("pdf_urls")
    @classmethod
    def _pdf_urls_are_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            if not _URL.match(value):
                raise ValueError(f"not an http(s) URL: {value!r}")
        return values

    @model_validator(mode="after")
    def _check_consistency(self) -> SourceDocument:
        if self.access == "automatic" and not self.pdf_urls:
            raise ValueError("access 'automatic' requires at least one pdf_urls entry.")
        unknown = set(self.unverified_fields) - set(type(self).model_fields)
        if unknown:
            raise ValueError(f"unverified_fields names unknown fields: {sorted(unknown)}")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal[1]
    description: str
    documents: list[SourceDocument]

    @model_validator(mode="after")
    def _unique_ids(self) -> Manifest:
        seen: set[str] = set()
        for doc in self.documents:
            if doc.doc_id in seen:
                raise ValueError(f"duplicate doc_id: {doc.doc_id}")
            seen.add(doc.doc_id)
        return self

    def get(self, doc_id: str) -> SourceDocument:
        for doc in self.documents:
            if doc.doc_id == doc_id:
                return doc
        raise KeyError(doc_id)

    @property
    def doc_ids(self) -> list[str]:
        return [doc.doc_id for doc in self.documents]


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate_json(Path(path).read_text(encoding="utf-8"))