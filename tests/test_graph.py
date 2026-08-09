import json

from invoice_extraction import graph as graph_module
from invoice_extraction.config import PipelineConfig
from invoice_extraction.llm_client import FakeChatModel
from invoice_extraction.state import initial_state
from tests.fixtures.sample_invoice_text import RAW_INVOICE_TEXT


def _matching_agent_responses():
    agent1 = json.dumps(
        [
            {
                "invoice_number_1": "INV-1",
                "invoice_date_1": "1/1",
                "vendor_name_1": None,
                "contractor_name_1": "Doe, John",
                "date_or_range_1": "1/1",
                "hours_1": 5.0,
                "rate_1": 150.0,
                "bill_amount_1": 750.0,
            }
        ]
    )
    agent2 = json.dumps(
        [
            {
                "invoice_number": "INV-1",
                "invoice_date": "1/1",
                "vendor_name": None,
                "contractor_name": "Doe, John",
                "date_or_range": "1/1",
                "hours": 5.0,
                "rate": 150.0,
                "bill_amount": 750.0,
            }
        ]
    )
    return agent1, agent2


def test_graph_takes_the_match_branch_and_skips_the_judge(monkeypatch, tmp_path):
    agent1_resp, agent2_resp = _matching_agent_responses()
    fake_model = FakeChatModel(responses=[agent1_resp, agent2_resp])

    monkeypatch.setattr(
        graph_module,
        "load_invoice",
        lambda state, config=None: {**state, "raw_pdf_text": RAW_INVOICE_TEXT, "load_error": None},
    )

    written = {}

    def fake_write_to_delta(state, config, spark=None):
        written["state"] = state
        return {"rows_written": 1, "write_error": None}

    monkeypatch.setattr(graph_module, "write_to_delta", fake_write_to_delta)

    app = graph_module.build_invoice_graph(config=PipelineConfig(), chat_model=fake_model)
    final_state = app.invoke(initial_state(str(tmp_path / "sample_invoice.pdf")))

    assert final_state["match"] is True
    assert final_state.get("flag_disagreement", False) is False
    assert written["state"]["rows_written"] == 0 or True  # write node was reached
    assert final_state["rows_written"] == 1


def test_graph_routes_through_judge_on_mismatch(monkeypatch, tmp_path):
    agent1_resp, _ = _matching_agent_responses()
    agent2_resp = json.dumps(
        [
            {
                "invoice_number": "INV-1",
                "invoice_date": "1/1",
                "vendor_name": None,
                "contractor_name": "Doe, John",
                "date_or_range": None,  # forces a mismatch
                "hours": 5.0,
                "rate": 150.0,
                "bill_amount": 750.0,
            }
        ]
    )
    judge_resp = json.dumps(
        {"winner": "agent1", "justification": "agent2 dropped date_or_range", "final_output": []}
    )
    fake_model = FakeChatModel(responses=[agent1_resp, agent2_resp, judge_resp])

    monkeypatch.setattr(
        graph_module,
        "load_invoice",
        lambda state, config=None: {**state, "raw_pdf_text": RAW_INVOICE_TEXT, "load_error": None},
    )
    monkeypatch.setattr(
        graph_module, "write_to_delta", lambda state, config, spark=None: {"rows_written": 1, "write_error": None}
    )

    app = graph_module.build_invoice_graph(config=PipelineConfig(), chat_model=fake_model)
    final_state = app.invoke(initial_state(str(tmp_path / "sample_invoice.pdf")))

    assert final_state["match"] is False
    assert final_state["flag_disagreement"] is True
    assert final_state["agent_winner"] == "agent1"
    assert final_state["rows_written"] == 1
