from invoice_extraction.agents.comparator import compare_outputs
from tests.fixtures.sample_invoice_text import (
    AGENT1_MATCHING_OUTPUT,
    AGENT2_MATCHING_OUTPUT,
    AGENT2_MISMATCHED_OUTPUT,
)


def test_compare_outputs_match():
    state = {"agent1_output": AGENT1_MATCHING_OUTPUT, "agent2_output": AGENT2_MATCHING_OUTPUT}
    result = compare_outputs(state)
    assert result == {"match": True, "mismatch_reason": None}


def test_compare_outputs_mismatch_in_field_value():
    state = {"agent1_output": AGENT1_MATCHING_OUTPUT, "agent2_output": AGENT2_MISMATCHED_OUTPUT}
    result = compare_outputs(state)
    assert result["match"] is False
    assert "row" in result["mismatch_reason"].lower()


def test_compare_outputs_mismatch_in_row_count():
    state = {"agent1_output": AGENT1_MATCHING_OUTPUT, "agent2_output": []}
    result = compare_outputs(state)
    assert result == {"match": False, "mismatch_reason": "Different number of rows"}


def test_compare_outputs_currency_formatting_does_not_cause_false_mismatch():
    agent1 = [{**AGENT1_MATCHING_OUTPUT[0], "bill_amount_1": "$750.00"}]
    agent2 = [{**AGENT2_MATCHING_OUTPUT[0], "bill_amount": 750.0}]
    result = compare_outputs({"agent1_output": agent1, "agent2_output": agent2})
    assert result["match"] is True


def test_compare_outputs_empty_both_sides_matches():
    result = compare_outputs({"agent1_output": [], "agent2_output": []})
    assert result["match"] is True
