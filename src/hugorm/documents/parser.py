from __future__ import annotations

import asyncio
import io


class UnsupportedDocumentError(Exception):
    pass


def _parse_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_pdf_sync(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(p.strip() for p in pages if p.strip())


async def parse_document(data: bytes, content_type: str, filename: str) -> str:
    """Return the text content of a document, or raise UnsupportedDocumentError."""
    ct = content_type.lower().split(";")[0].strip()
    lower = filename.lower()

    if ct == "application/pdf" or lower.endswith(".pdf"):
        return await asyncio.to_thread(_parse_pdf_sync, data)
    if ct.startswith("text/") or lower.endswith((".txt", ".md", ".markdown")):
        return _parse_text(data)
    raise UnsupportedDocumentError(f"unsupported content type: {ct or filename}")
