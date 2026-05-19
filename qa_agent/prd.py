"""Extract plain text from an uploaded PRD (PDF, DOCX, or raw text)."""

from __future__ import annotations

import io
from pathlib import Path

import PyPDF2
from docx import Document


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _from_pdf(data)
    if suffix == ".docx":
        return _from_docx(data)
    if suffix in (".txt", ".md", ""):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported PRD format: {suffix}")


def _from_pdf(data: bytes) -> str:
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _from_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()
