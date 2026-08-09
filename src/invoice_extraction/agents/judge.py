"""judge_disagreement node: a third LLM call arbitrates agent1 vs agent2."""

from __future__ import annotations

import json
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from invoice_extraction.state import InvoiceState
from invoice_extraction.utils.json_utils import extract_json
from invoice_extraction.utils.retry import with_retry

logger = logging.getLogger(__name__)

JUDGE_PROMPT_TEMPLATE = """\
You are an expert invoice reviewer. Two AI agents have attempted to extract
structured data from the same invoice. Compare their outputs and determine
which one is more accurate by checking against the original invoice text.

Original Invoice Text:
{raw_text}

Agent 1 Output:
{agent1_output}

Agent 2 Output:
{agent2_output}

Return your answer as a single JSON object in this exact shape:
{{
  "winner": "agent1" or "agent2",
  "justification": "short explanation of why",
  "final_output": <copy of the more accurate agent's output array>
}}

Do not invent new values. Only pick between the two agent outputs.
Return ONLY the JSON object, no markdown fences, no commentary.
"""


def build_judge_prompt(raw_text: str, agent1_output: list, agent2_output: list) -> str:
    return JUDGE_PROMPT_TEMPLATE.format(
        raw_text=raw_text,
        agent1_output=json.dumps(agent1_output, indent=2),
        agent2_output=json.dumps(agent2_output, indent=2),
    )


def judge_disagreement(
    state: InvoiceState,
    chat_model: BaseChatModel,
    *,
    max_retries: int = 3,
    retry_base_delay_seconds: float = 1.0,
    retry_max_delay_seconds: float = 20.0,
) -> InvoiceState:
    raw_text = state.get("raw_pdf_text", "")
    agent1_output = state.get("agent1_output", [])
    agent2_output = state.get("agent2_output", [])

    prompt = build_judge_prompt(raw_text, agent1_output, agent2_output)
    response = with_retry(
        lambda: chat_model.invoke([HumanMessage(content=prompt)]),
        max_retries=max_retries,
        base_delay_seconds=retry_base_delay_seconds,
        max_delay_seconds=retry_max_delay_seconds,
    )
    content = getattr(response, "content", "") or ""

    parsed = extract_json(content)
    result = parsed[0] if parsed else {}

    winner = result.get("winner")
    justification = result.get("justification")

    if winner not in {"agent1", "agent2"}:
        logger.warning("judge_disagreement: could not parse a valid winner from judge response")
        winner = winner or "unresolved"
        justification = justification or "Judge response could not be parsed."

    return {
        "flag_disagreement": True,
        "agent_winner": winner,
        "justification": justification,
    }


def make_judge_node(chat_model: BaseChatModel, *, max_retries: int = 3,
                     retry_base_delay_seconds: float = 1.0, retry_max_delay_seconds: float = 20.0):
    """Return a LangGraph-compatible node bound to a specific chat model."""

    def _node(state: InvoiceState) -> InvoiceState:
        return judge_disagreement(
            state,
            chat_model,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
            retry_max_delay_seconds=retry_max_delay_seconds,
        )

    _node.__name__ = "judge_disagreement"
    return _node
