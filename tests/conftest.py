import json

import pytest

from invoice_extraction.config import PipelineConfig
from tests.fixtures.sample_invoice_text import RAW_INVOICE_TEXT


@pytest.fixture
def pipeline_config() -> PipelineConfig:
    return PipelineConfig.from_env()


@pytest.fixture
def raw_invoice_text() -> str:
    return RAW_INVOICE_TEXT


@pytest.fixture
def judge_response_agent1_wins() -> str:
    return json.dumps(
        {
            "winner": "agent1",
            "justification": "Agent 1 correctly extracted date_or_range for Smith, Jane.",
            "final_output": [],
        }
    )
