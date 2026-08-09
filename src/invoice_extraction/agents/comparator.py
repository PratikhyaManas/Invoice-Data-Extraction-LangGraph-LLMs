"""compare_outputs node: normalize + diff agent1 vs agent2 output."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from invoice_extraction.state import InvoiceState
from invoice_extraction.utils.text_utils import normalize_row

logger = logging.getLogger(__name__)

# Agent 1 rows carry a configurable suffix (see ExtractionAgentConfig.field_suffix);
# this maps suffixed field names back to the canonical (agent-2-style) names so the
# two outputs are directly comparable.
_CANONICAL_FIELDS = (
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "contractor_name",
    "date_or_range",
    "hours",
    "rate",
    "bill_amount",
)


def _strip_suffix(field_name: str, suffix: str) -> str:
    if suffix and field_name.endswith(suffix):
        return field_name[: -len(suffix)]
    return field_name


def _row_sort_key(row: Dict[str, Any]):
    return (
        str(row.get("invoice_number", "")).lower(),
        str(row.get("vendor_name", "")).lower(),
        str(row.get("contractor_name", "")).lower(),
        str(row.get("date_or_range", "")).lower(),
    )


def compare_outputs(state: InvoiceState, agent1_field_suffix: str = "_1") -> InvoiceState:
    output1: List[Dict[str, Any]] = state.get("agent1_output", [])
    output2: List[Dict[str, Any]] = state.get("agent2_output", [])

    if len(output1) != len(output2):
        logger.info("compare_outputs: row-count mismatch (%s vs %s)", len(output1), len(output2))
        return {"match": False, "mismatch_reason": "Different number of rows"}

    normalized1 = [normalize_row(row) for row in output1]
    normalized2 = [normalize_row(row) for row in output2]

    mapped1 = [
        {_strip_suffix(key, agent1_field_suffix): value for key, value in row.items()}
        for row in normalized1
    ]

    sorted1 = sorted(mapped1, key=_row_sort_key)
    sorted2 = sorted(normalized2, key=_row_sort_key)

    for idx, (row1, row2) in enumerate(zip(sorted1, sorted2), start=1):
        if row1 != row2:
            logger.info("compare_outputs: mismatch in row %s: %s vs %s", idx, row1, row2)
            return {"match": False, "mismatch_reason": f"Mismatch in row {idx}"}

    logger.info("compare_outputs: agent outputs match after normalization")
    return {"match": True, "mismatch_reason": None}
