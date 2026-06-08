from __future__ import annotations

import io

import pytest

from hugorm.documents.parser import UnsupportedDocumentError, parse_document


@pytest.mark.asyncio
async def test_parse_plain_text() -> None:
    text = await parse_document(b"hello world", "text/plain", "note.txt")
    assert text == "hello world"


@pytest.mark.asyncio
async def test_parse_markdown_by_extension() -> None:
    text = await parse_document(b"# title\nbody", "application/octet-stream", "readme.md")
    assert "# title" in text


@pytest.mark.asyncio
async def test_parse_unknown_raises() -> None:
    with pytest.raises(UnsupportedDocumentError):
        await parse_document(b"\x89PNG\r\n...", "image/png", "pic.png")


@pytest.mark.asyncio
async def test_parse_pdf_returns_text() -> None:
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    del page
    buf = io.BytesIO()
    writer.write(buf)
    text = await parse_document(buf.getvalue(), "application/pdf", "blank.pdf")
    assert isinstance(text, str)
