"""
PDF and HTML text extraction.

Tries PyMuPDF (fitz) for PDFs first, falls back to pdfminer, then raw text decode.
For HTML content uses BeautifulSoup.
"""

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def extract_text_from_bytes(content: bytes, source_url: str = "") -> str:
    """
    Extract plain text from raw document bytes.
    Detects PDF vs HTML by content signature and URL extension.
    """
    if not content:
        return ""

    is_pdf = content[:4] == b"%PDF" or source_url.lower().endswith(".pdf")

    if is_pdf:
        text = _extract_pdf(content)
        if text.strip():
            return text

    # Try HTML extraction
    text = _extract_html(content)
    if text.strip():
        return text

    # Last resort — decode as utf-8
    try:
        return content.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_pdf(content: bytes) -> str:
    """Try PyMuPDF first, fall back to pdfminer."""
    text = _try_pymupdf(content)
    if not text.strip():
        text = _try_pdfminer(content)
    return text


def _try_pymupdf(content: bytes) -> str:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=content, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
        doc.close()
        return "\n".join(pages)
    except ImportError:
        logger.debug("PyMuPDF not installed — skipping")
        return ""
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed: %s", exc)
        return ""


def _try_pdfminer(content: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract

        return pdfminer_extract(BytesIO(content))
    except ImportError:
        logger.debug("pdfminer.six not installed — skipping")
        return ""
    except Exception as exc:
        logger.warning("pdfminer extraction failed: %s", exc)
        return ""


def _extract_html(content: bytes) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content, "html.parser")
        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except ImportError:
        logger.debug("BeautifulSoup not installed — skipping HTML parse")
        return ""
    except Exception as exc:
        logger.warning("HTML extraction failed: %s", exc)
        return ""


def extract_text_from_file(path: str) -> str:
    """Convenience wrapper for local file paths."""
    try:
        with open(path, "rb") as f:
            content = f.read()
        return extract_text_from_bytes(content, source_url=path)
    except Exception as exc:
        logger.error("Failed to read file %s: %s", path, exc)
        return ""
