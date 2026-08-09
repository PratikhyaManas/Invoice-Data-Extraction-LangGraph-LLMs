"""
Builds the LangGraph workflow:

    load_invoice --+--> agent1_extract --+--> compare_outputs --[match]--> write_to_delta --> END
                    |                     |                 \\
                    +--> agent2_extract --+                  --[mismatch]--> judge_disagreement --> write_to_delta --> END

Exposed as a factory (``build_invoice_graph``) rather than a module-level
compiled graph so tests (and multi-tenant jobs) can inject a fake chat
model / fake Spark session without monkey-patching globals.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, StateGraph

from invoice_extraction.agents.comparator import compare_outputs
from invoice_extraction.agents.extraction_agent import ExtractionAgent, ExtractionAgentConfig
from invoice_extraction.agents.judge import make_judge_node
from invoice_extraction.config import PipelineConfig
from invoice_extraction.llm_client import build_chat_model
from invoice_extraction.pdf_loader import load_invoice
from invoice_extraction.state import InvoiceState
from invoice_extraction.storage.delta_writer import write_to_delta
from invoice_extraction.utils.cache import CacheBackend, InMemoryCache

logger = logging.getLogger(__name__)

AGENT1_CONFIG = ExtractionAgentConfig(name="Agent 1", state_key="agent1_output", field_suffix="_1")
AGENT2_CONFIG = ExtractionAgentConfig(
    name="Agent 2 - double check accuracy",
    state_key="agent2_output",
    field_suffix="",
)


def build_invoice_graph(
    config: Optional[PipelineConfig] = None,
    chat_model: Optional[BaseChatModel] = None,
    spark=None,
    cache: Optional[CacheBackend] = None,
):
    """Compile and return the invoice-extraction LangGraph app.

    Parameters
    ----------
    config:
        Pipeline configuration; defaults to ``PipelineConfig()`` (safe
        defaults, no network calls until nodes actually run).
    chat_model:
        Optional pre-built chat model, useful for tests
        (``FakeChatModel``) or to share one client across agents/judge.
        If omitted, one is built from ``config.llm``.
    spark:
        Optional SparkSession to inject into the writer node for tests.
    cache:
        Optional cache backend shared between agent1 and agent2 for this
        graph build. Defaults to a **fresh** ``InMemoryCache`` scoped to
        this single ``build_invoice_graph`` call -- so every call (every
        test, every batch run) starts isolated by default; pass one
        explicitly (see ``runner.py``) to read hit-rate stats after a
        batch, or to intentionally widen the cache's lifetime.
    """
    config = config or PipelineConfig()
    chat_model = chat_model or build_chat_model(config.llm)
    cache = cache if cache is not None else InMemoryCache()

    agent_kwargs = dict(
        max_retries=config.llm.max_retries,
        retry_base_delay_seconds=config.llm.retry_base_delay_seconds,
        retry_max_delay_seconds=config.llm.retry_max_delay_seconds,
        enable_cache=config.llm.enable_cache,
        prompt_version=config.llm.prompt_version,
        cache=cache,
    )
    agent1 = ExtractionAgent(chat_model, AGENT1_CONFIG, **agent_kwargs)
    agent2 = ExtractionAgent(chat_model, AGENT2_CONFIG, **agent_kwargs)

    graph = StateGraph(InvoiceState)

    graph.add_node("load_invoice", lambda state: load_invoice(state, config))
    graph.add_node("agent1_extract", agent1.as_node())
    graph.add_node("agent2_extract", agent2.as_node())
    graph.add_node("compare_outputs", compare_outputs)
    graph.add_node(
        "judge_disagreement",
        make_judge_node(
            chat_model,
            max_retries=config.llm.max_retries,
            retry_base_delay_seconds=config.llm.retry_base_delay_seconds,
            retry_max_delay_seconds=config.llm.retry_max_delay_seconds,
        ),
    )
    graph.add_node("write_to_delta", lambda state: write_to_delta(state, config, spark=spark))

    graph.set_entry_point("load_invoice")

    graph.add_edge("load_invoice", "agent1_extract")
    graph.add_edge("load_invoice", "agent2_extract")

    graph.add_edge("agent1_extract", "compare_outputs")
    graph.add_edge("agent2_extract", "compare_outputs")

    graph.add_conditional_edges(
        "compare_outputs",
        lambda state: bool(state.get("match", False)),
        {True: "write_to_delta", False: "judge_disagreement"},
    )

    graph.add_edge("judge_disagreement", "write_to_delta")
    graph.add_edge("write_to_delta", END)

    compiled_app = graph.compile()
    try:
        # Best-effort: expose the cache so callers (e.g. runner.py) can
        # report hit-rate stats after a batch. Not load-bearing for
        # correctness -- if the compiled graph object doesn't allow
        # arbitrary attributes in some langgraph version, we just skip it.
        compiled_app.invoice_extraction_cache = cache
    except AttributeError:
        logger.debug("Could not attach cache to compiled graph for stats reporting; continuing without it.")
    return compiled_app
