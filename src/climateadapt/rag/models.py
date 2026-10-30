"""Core retrieval data models. Every chunk keeps its document id and page range."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    label: str | None = None
    text: str


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    doc_id: str
    chunk_index: int = Field(ge=0)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    word_count: int = Field(ge=1)
    text: str
    text_sha256: str
    label_start: str | None = None
    label_end: str | None = None
    section_type: Literal["body", "references"] = "body"


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk: Chunk
    score: float
    rank: int = Field(ge=1)
    component_ranks: dict[str, int]
    component_scores: dict[str, float]


def make_chunk_id(doc_id: str, index: int) -> str:
    return f"{doc_id}:{index:05d}"