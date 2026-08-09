"""Text cleanup and normalization helpers shared by loader + comparator."""

from __future__ import annotations

import re
from typing import Any, Dict


def clean_raw_text(raw_text: str) -> str:
    """Strip common OCR/pdfplumber artifacts before handing text to an LLM."""
    if not raw_text:
        return ""
    text = re.sub(r"[_]{2,}", " ", raw_text)                 # long underscore runs
    text = re.sub(r"([A-Za-z])[_]+([A-Za-z])", r"\1\2", text)  # letters split by underscores
    text = re.sub(r"\s{2,}", " ", text)                       # collapse whitespace
    text = text.replace("\n", " ")
    return text.strip()


def normalize_value(value: Any) -> Any:
    """Normalize a scalar so equivalent values compare equal.

    e.g. ``"$525.00"``, ``"525.0"`` and ``525.0`` should all be treated
    as the same amount when comparing two agents' outputs.
    """
    if isinstance(value, str):
        value = value.strip().lower()
        value = value.replace("$", "").replace(",", "")
        value = re.sub(r"\s+", "", value)
        try:
            return float(value)
        except ValueError:
            return value
    return value


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {key: normalize_value(value) for key, value in row.items()}
