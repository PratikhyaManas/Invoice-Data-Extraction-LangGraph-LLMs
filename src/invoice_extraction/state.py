"""
Shared state schema for the LangGraph invoice-extraction workflow.

Kept in its own module (rather than inline in a notebook) so both the
graph builder and the unit tests import the exact same contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class InvoiceState(TypedDict, total=False):
    # --- input -------------------------------------------------------
    invoice_path: str          # Unity Catalog Volume path (or local path in tests)
    invoice_id: str            # stable id derived from the file name, used for idempotency

    # --- load_invoice --------------------------------------------------
    raw_pdf_text: str
    load_error: Optional[str]

    # --- agent outputs ---------------------------------------------------
    agent1_output: List[Dict[str, Any]]
    agent2_output: List[Dict[str, Any]]

    # --- compare_outputs --------------------------------------------------
    match: bool
    mismatch_reason: Optional[str]

    # --- judge_disagreement --------------------------------------------------
    flag_disagreement: bool
    agent_winner: Optional[str]
    justification: Optional[str]

    # --- persist_results --------------------------------------------------
    rows_written: int
    write_error: Optional[str]


def initial_state(invoice_path: str, invoice_id: Optional[str] = None) -> InvoiceState:
    """Factory for a fresh state dict, avoiding hand-rolled dicts scattered
    across call sites (the reference notebook redefines this dict inline
    on every test cell)."""
    return InvoiceState(
        invoice_path=invoice_path,
        invoice_id=invoice_id or invoice_path,
        raw_pdf_text="",
        load_error=None,
        agent1_output=[],
        agent2_output=[],
        match=False,
        mismatch_reason=None,
        flag_disagreement=False,
        agent_winner=None,
        justification=None,
        rows_written=0,
        write_error=None,
    )
