import json

from invoice_extraction.agents.extraction_agent import ExtractionAgent, ExtractionAgentConfig
from invoice_extraction.llm_client import FakeChatModel


def test_extraction_agent_parses_valid_json_response(raw_invoice_text):
    scripted = json.dumps([{"contractor_name_1": "Doe, John", "hours_1": 5.0}])
    fake_model = FakeChatModel(responses=[scripted])
    agent = ExtractionAgent(fake_model, ExtractionAgentConfig(name="Agent 1", state_key="agent1_output", field_suffix="_1"))

    result = agent.run({"raw_pdf_text": raw_invoice_text})

    assert result == {"agent1_output": [{"contractor_name_1": "Doe, John", "hours_1": 5.0}]}


def test_extraction_agent_handles_unparseable_response_gracefully(raw_invoice_text):
    fake_model = FakeChatModel(responses=["I could not extract anything useful."])
    agent = ExtractionAgent(fake_model, ExtractionAgentConfig(name="Agent 2", state_key="agent2_output"))

    result = agent.run({"raw_pdf_text": raw_invoice_text})

    assert result == {"agent2_output": []}


def test_extraction_agent_skips_llm_call_when_no_text():
    fake_model = FakeChatModel(responses=["should not be used"])
    agent = ExtractionAgent(fake_model, ExtractionAgentConfig(name="Agent 1", state_key="agent1_output"))

    result = agent.run({"raw_pdf_text": ""})

    assert result == {"agent1_output": []}


def test_as_node_returns_callable_with_stable_name():
    fake_model = FakeChatModel(responses=["[]"])
    agent = ExtractionAgent(fake_model, ExtractionAgentConfig(name="Agent 1", state_key="agent1_output"))
    node = agent.as_node()
    assert callable(node)
    assert node.__name__ == "extract_agent1_output"
