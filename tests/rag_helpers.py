"""Helpers for RAG tests: a minimal valid PDF writer and chunk factories. All data is synthetic."""

from __future__ import annotations

from climateadapt.rag.chunking import sha256_text
from climateadapt.rag.models import Chunk, make_chunk_id


def make_pdf(pages: list[str]) -> bytes:
    """Build a valid PDF with one Helvetica text page per entry (lines split on newlines)."""
    n = len(pages)
    font_id = 3 + 2 * n
    objects: dict[int, bytes] = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("latin-1")
    for i, text in enumerate(pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode("latin-1")
        lines = text.split("\n")
        ops = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
        for j, line in enumerate(lines):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({escaped}) Tj")
            if j < len(lines) - 1:
                ops.append("T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects[content_id] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(out)
        out += f"{obj_id} 0 obj\n".encode() + objects[obj_id] + b"\nendobj\n"
    xref_pos = len(out)
    size = font_id + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for obj_id in range(1, size):
        out += f"{offsets[obj_id]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


def make_labeled_pdf(pages: list[str], *, start: int = 1, prefix: str = "") -> bytes:
    """Like make_pdf, but stamped with printed page labels via pypdf's own writer."""
    import io

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(make_pdf(pages)))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.set_page_label(0, len(pages) - 1, style="/D", start=start, prefix=prefix or None)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_chunk(
        index: int,
        text: str,
        doc_id: str = "doc-a",
        pages: tuple[int, int] = (1, 1),
        labels: tuple[str | None, str | None] | None = None,
        section_type: str = "body",
) -> Chunk:
    return Chunk(
        chunk_id=make_chunk_id(doc_id, index),
        doc_id=doc_id,
        chunk_index=index,
        page_start=pages[0],
        page_end=pages[1],
        word_count=len(text.split()),
        text=text,
        text_sha256=sha256_text(text),
        label_start=labels[0] if labels else None,
        label_end=labels[1] if labels else None,
        section_type=section_type,
    )