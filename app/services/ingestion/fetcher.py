"""Fetch remote content for ingest-from-URL.

Downloads a single public ``http(s)`` resource and returns the bytes together
with a filename whose extension lets :mod:`app.services.ingestion.extractors`
dispatch correctly. Only the schemes and content types the pipeline can already
extract are accepted; anything else fails cleanly with :class:`UrlFetchError`.
"""

import posixpath
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx

from app.services.ingestion.extractors import SUPPORTED_EXTENSIONS

_ALLOWED_SCHEMES = {"http", "https"}

# Map a response content type to the extension the extractors dispatch on.
_CONTENT_TYPE_EXT = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
    "application/csv": "csv",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


class UrlFetchError(Exception):
    """Raised when a URL cannot be fetched or is not ingestible."""


@dataclass(slots=True)
class FetchedDocument:
    """A downloaded resource ready to hand to ``create_document``."""

    filename: str
    content_type: str
    data: bytes


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _resolve_filename(url: str, content_type: str, override: str | None) -> str:
    """Pick a filename whose extension a registered extractor supports."""
    if override:
        if _ext(override) not in SUPPORTED_EXTENSIONS:
            raise UrlFetchError(f"unsupported filename extension: {override!r}")
        return override

    parsed = urlparse(url)
    base = unquote(posixpath.basename(parsed.path))
    if _ext(base) in SUPPORTED_EXTENSIONS:
        return base

    mapped = _CONTENT_TYPE_EXT.get(content_type.split(";", 1)[0].strip().lower())
    if mapped is None:
        raise UrlFetchError(f"unsupported content type: {content_type or 'unknown'!r}")

    stem = base.rsplit(".", 1)[0] if base else (parsed.netloc or "download")
    return f"{stem}.{mapped}"


async def fetch_url(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    filename: str | None = None,
) -> FetchedDocument:
    """Download ``url`` and return its bytes with an extractable filename."""
    scheme = urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UrlFetchError(f"unsupported URL scheme: {scheme or 'none'!r}")

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise UrlFetchError(f"failed to fetch URL: {exc}") from exc

    data = response.content
    if not data:
        raise UrlFetchError("fetched resource is empty")
    if len(data) > max_bytes:
        raise UrlFetchError("fetched resource exceeds the maximum allowed size")

    content_type = response.headers.get("content-type", "")
    resolved = _resolve_filename(url, content_type, filename)
    return FetchedDocument(
        filename=resolved,
        content_type=content_type or "application/octet-stream",
        data=data,
    )
