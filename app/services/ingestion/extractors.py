"""Text extraction from uploaded files.

Plain-text formats (txt/markdown/html/csv) are handled with the standard
library. PDF and DOCX use optional dependencies imported lazily, so the platform
runs without them installed; an unsupported or missing-dependency upload fails
cleanly and lands in the DLQ rather than crashing the worker.
"""

from dataclasses import dataclass
from html.parser import HTMLParser


class UnsupportedDocumentType(Exception):
    """Raised when no extractor is available for a file type."""


@dataclass(slots=True)
class ExtractedPage:
    """Extracted text for one logical page (``page`` is 1-based, if known)."""

    text: str
    page: int | None = None


class _TextHTMLParser(HTMLParser):
    _SKIP = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._parts)


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _extract_text(data: bytes) -> list[ExtractedPage]:
    return [ExtractedPage(text=data.decode("utf-8", errors="replace"))]


def _extract_html(data: bytes) -> list[ExtractedPage]:
    parser = _TextHTMLParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    return [ExtractedPage(text=parser.text)]


def _extract_pdf(data: bytes) -> list[ExtractedPage]:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return [
        ExtractedPage(text=page.extract_text() or "", page=index)
        for index, page in enumerate(reader.pages, start=1)
    ]


def _extract_docx(data: bytes) -> list[ExtractedPage]:
    import io

    from docx import Document as DocxDocument

    document = DocxDocument(io.BytesIO(data))
    text = "\n".join(p.text for p in document.paragraphs)
    return [ExtractedPage(text=text)]


def _extract_csv(data: bytes) -> list[ExtractedPage]:
    import csv
    import io

    # ``utf-8-sig`` transparently strips a leading BOM written by Excel.
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace")))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [ExtractedPage(text="")]

    header = rows[0]
    lines = [" | ".join(header)]
    for row in rows[1:]:
        pairs = [
            f"{header[i]}: {value}" if i < len(header) and header[i].strip() else value
            for i, value in enumerate(row)
        ]
        lines.append(" | ".join(pairs))
    return [ExtractedPage(text="\n".join(lines))]


_EXTRACTORS = {
    "txt": _extract_text,
    "md": _extract_text,
    "markdown": _extract_text,
    "html": _extract_html,
    "htm": _extract_html,
    "csv": _extract_csv,
    "pdf": _extract_pdf,
    "docx": _extract_docx,
}

SUPPORTED_EXTENSIONS = frozenset(_EXTRACTORS)


def extract(filename: str, data: bytes) -> list[ExtractedPage]:
    """Return extracted pages for a file, dispatching on its extension."""
    extractor = _EXTRACTORS.get(_ext(filename))
    if extractor is None:
        raise UnsupportedDocumentType(_ext(filename) or filename)
    return extractor(data)
