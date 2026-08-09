"""
load_invoice node.

On Databricks, Unity Catalog Volumes are exposed as ordinary POSIX
paths (``/Volumes/<catalog>/<schema>/<volume>/...``), so the exact same
``open()``/``pdfplumber`` code that reads a local file in unit tests
also reads a governed Volume in production -- no GCS-client-specific
code path is needed, unlike the BigQuery/GCS reference implementation.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from invoice_extraction.config import PipelineConfig
from invoice_extraction.state import InvoiceState
from invoice_extraction.utils.text_utils import clean_raw_text

logger = logging.getLogger(__name__)


class InvoiceLoadError(RuntimeError):
    """Raised when a PDF cannot be read or produces no extractable text."""


def _extract_text_with_ocr_fallback(pdf_bytes: BytesIO, enable_ocr_fallback: bool) -> str:
    import pdfplumber  # local import keeps module importable without the dependency in light tests

    full_text_parts = []
    with pdfplumber.open(pdf_bytes) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""

            if not page_text and enable_ocr_fallback:
                page_text = _ocr_page(page, page_number)

            full_text_parts.append(page_text)

    return "\n".join(full_text_parts)


def _ocr_page(page, page_number: int) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("OCR fallback requested for page %s but pytesseract/Pillow not installed", page_number)
        return ""

    ocr_text_parts = []
    for image in page.images:
        try:
            im = Image.open(BytesIO(image["data"]))
            ocr_text_parts.append(pytesseract.image_to_string(im))
        except Exception:  # noqa: BLE001 - OCR is best-effort, never fatal
            logger.exception("OCR failed for an image on page %s", page_number)
    return "\n".join(ocr_text_parts)


def load_invoice(state: InvoiceState, config: Optional[PipelineConfig] = None) -> InvoiceState:
    """LangGraph node: read a PDF path from state and populate ``raw_pdf_text``."""
    config = config or PipelineConfig()
    invoice_path = state.get("invoice_path")

    if not invoice_path:
        return {**state, "load_error": "invoice_path missing from state"}

    try:
        with open(invoice_path, "rb") as f:
            pdf_bytes = BytesIO(f.read())

        full_text = _extract_text_with_ocr_fallback(pdf_bytes, config.enable_ocr_fallback)
        cleaned_text = clean_raw_text(full_text)

        if not cleaned_text:
            raise InvoiceLoadError(f"No extractable text found in {invoice_path!r}")

        return {**state, "raw_pdf_text": cleaned_text, "load_error": None}

    except FileNotFoundError as exc:
        logger.error("Invoice not found: %s", invoice_path)
        return {**state, "raw_pdf_text": "", "load_error": str(exc)}
    except InvoiceLoadError as exc:
        logger.error(str(exc))
        return {**state, "raw_pdf_text": "", "load_error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - convert any parser error into pipeline state
        logger.exception("Unexpected error loading invoice %s", invoice_path)
        return {**state, "raw_pdf_text": "", "load_error": f"{type(exc).__name__}: {exc}"}
