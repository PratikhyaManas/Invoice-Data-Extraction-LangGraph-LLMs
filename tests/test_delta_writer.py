from invoice_extraction.storage.delta_writer import build_result_dataframe
from invoice_extraction.storage.schema import RESULT_SCHEMA
from tests.fixtures.sample_invoice_text import AGENT1_MATCHING_OUTPUT, AGENT2_MATCHING_OUTPUT


def test_build_result_dataframe_has_expected_columns():
    state = {
        "invoice_path": "sample_invoice.pdf",
        "invoice_id": "sample_invoice",
        "agent1_output": AGENT1_MATCHING_OUTPUT,
        "agent2_output": AGENT2_MATCHING_OUTPUT,
        "match": True,
        "agent_winner": "none",
        "justification": "no disagreement",
    }
    df = build_result_dataframe(state)
    assert list(df.columns) == RESULT_SCHEMA
    assert df.shape[0] == 1
    assert df.loc[0, "contractor_name_1"] == "Doe, John"
    assert df.loc[0, "bill_amount"] == 750.0
    assert df.loc[0, "match"] == "True"


def test_build_result_dataframe_handles_uneven_agent_row_counts():
    state = {
        "invoice_path": "sample_invoice.pdf",
        "invoice_id": "sample_invoice",
        "agent1_output": AGENT1_MATCHING_OUTPUT * 2,
        "agent2_output": AGENT2_MATCHING_OUTPUT,
        "match": False,
        "agent_winner": "agent1",
        "justification": "agent2 dropped a row",
    }
    df = build_result_dataframe(state)
    # padded to the longer side instead of silently dropping data
    assert df.shape[0] == 2


def test_build_result_dataframe_empty_outputs_still_returns_schema():
    state = {"invoice_path": "empty.pdf", "invoice_id": "empty", "agent1_output": [], "agent2_output": []}
    df = build_result_dataframe(state)
    assert list(df.columns) == RESULT_SCHEMA
    assert df.shape[0] == 1  # one placeholder row, not zero
