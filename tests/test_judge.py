from invoice_extraction.agents.judge import judge_disagreement
from invoice_extraction.llm_client import FakeChatModel
from tests.fixtures.sample_invoice_text import (
    AGENT1_MATCHING_OUTPUT,
    AGENT2_MISMATCHED_OUTPUT,
    RAW_INVOICE_TEXT,
)


def test_judge_disagreement_picks_a_winner(judge_response_agent1_wins):
    fake_model = FakeChatModel(responses=[judge_response_agent1_wins])
    state = {
        "raw_pdf_text": RAW_INVOICE_TEXT,
        "agent1_output": AGENT1_MATCHING_OUTPUT,
        "agent2_output": AGENT2_MISMATCHED_OUTPUT,
    }

    result = judge_disagreement(state, fake_model)

    assert result["flag_disagreement"] is True
    assert result["agent_winner"] == "agent1"
    assert "date_or_range" in result["justification"] or result["justification"]


def test_judge_disagreement_handles_malformed_judge_response():
    fake_model = FakeChatModel(responses=["not valid json at all"])
    state = {
        "raw_pdf_text": RAW_INVOICE_TEXT,
        "agent1_output": AGENT1_MATCHING_OUTPUT,
        "agent2_output": AGENT2_MISMATCHED_OUTPUT,
    }

    result = judge_disagreement(state, fake_model)

    assert result["flag_disagreement"] is True
    assert result["agent_winner"] == "unresolved"
    assert result["justification"]
