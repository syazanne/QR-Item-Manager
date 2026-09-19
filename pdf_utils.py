"""Reference only: PDF/manual helpers from the earlier prototype.

The current app does not import this module. See docs/REFERENCE.md.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract PDF text with the app's existing pypdf dependency."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("Please install pypdf to extract PDF text.") from exc

    reader = PdfReader(str(pdf_path))
    text_chunks = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_chunks.append(page_text)
    return "\n".join(text_chunks)


def search_manual_text(manual_text: str, query: str) -> List[str]:
    """Search extracted manual text and return short matching snippets."""
    if not query or not manual_text:
        return []

    keywords = [part.lower() for part in re.split(r"\s+", query.strip()) if part]
    if not keywords:
        return []

    sentences = re.split(r"\n+|(?<=[.!?])\s+", manual_text)
    matches: List[str] = []

    for sentence in sentences:
        cleaned_sentence = sentence.strip()
        if not cleaned_sentence:
            continue
        lowered_sentence = cleaned_sentence.lower()
        if any(keyword in lowered_sentence for keyword in keywords):
            matches.append(cleaned_sentence)

    return matches[:10]
