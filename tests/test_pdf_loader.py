import os

import pytest

from invoice_extraction import pdf_loader
from invoice_extraction.config import PipelineConfig


def test_load_invoice_missing_path_returns_error():
    result = pdf_loader.load_invoice({})
    assert result["load_error"] == "invoice_path missing from state"


def test_load_invoice_file_not_found_is_isolated(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.pdf")
    result = pdf_loader.load_invoice({"invoice_path": missing_path})
    assert result["raw_pdf_text"] == ""
    assert "No such file" in result["load_error"] or "does_not_exist" in result["load_error"]


def test_load_invoice_happy_path(tmp_path, monkeypatch):
    fake_pdf_path = tmp_path / "sample_invoice.pdf"
    fake_pdf_path.write_bytes(b"%PDF-1.4 minimal placeholder, parsing is monkeypatched")

    monkeypatch.setattr(
        pdf_loader,
        "_extract_text_with_ocr_fallback",
        lambda pdf_bytes, enable_ocr_fallback: "Invoice No: INV-001234   messy___text",
    )

    result = pdf_loader.load_invoice({"invoice_path": str(fake_pdf_path)}, config=PipelineConfig())

    assert result["load_error"] is None
    assert "INV-001234" in result["raw_pdf_text"]
    assert "___" not in result["raw_pdf_text"]


def test_load_invoice_empty_extracted_text_is_an_error(tmp_path, monkeypatch):
    fake_pdf_path = tmp_path / "blank.pdf"
    fake_pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(pdf_loader, "_extract_text_with_ocr_fallback", lambda *a, **k: "")

    result = pdf_loader.load_invoice({"invoice_path": str(fake_pdf_path)})

    assert result["raw_pdf_text"] == ""
    assert result["load_error"] is not None
