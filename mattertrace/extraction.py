"""Text extraction for PDF and TXT files (component 5).

PDF: one segment per page (page_number set).
TXT: one segment per paragraph (page_number is None, segment_index = paragraph number).
Failures raise ExtractionError with a short, user-safe reason.
"""
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .errors import ExtractionError

# pypdf logs warnings for malformed files; failures are reported through ExtractionError instead.
logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass
class Segment:
    page_number: int | None
    segment_index: int
    text: str


def extract_pdf(data: bytes) -> list[Segment]:
    if not data.startswith(b"%PDF"):
        raise ExtractionError("The file is not a valid PDF (missing PDF header).")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("The PDF is password-protected and cannot be read.")
        segments = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                segments.append(Segment(page_number=i, segment_index=len(segments) + 1, text=text))
    except ExtractionError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ExtractionError(f"The PDF could not be read ({type(exc).__name__}).") from exc
    if not segments:
        raise ExtractionError(
            "No readable text was found. The PDF may be a scanned image; OCR is not supported "
            "in this prototype. Review the original manually or upload a text-based copy."
        )
    return segments


def extract_txt(data: bytes) -> list[Segment]:
    if b"\x00" in data:
        raise ExtractionError("The file contains binary data and is not readable text.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]
    if not paragraphs:
        raise ExtractionError("The text file contains no readable text.")
    return [Segment(page_number=None, segment_index=i, text=p) for i, p in enumerate(paragraphs, start=1)]


def extract(path: Path, file_type: str) -> list[Segment]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ExtractionError("The stored original file could not be opened.") from exc
    if file_type == "pdf":
        return extract_pdf(data)
    if file_type == "txt":
        return extract_txt(data)
    raise ExtractionError(f"Unsupported file type '{file_type}'.")


def location_label(page_number: int | None, segment_index: int) -> str:
    return f"page {page_number}" if page_number else f"paragraph {segment_index}"
