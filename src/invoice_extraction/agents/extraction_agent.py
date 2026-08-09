"""
A single, reusable extraction agent class.

The reference notebook defines ``agent1_extract`` and ``agent2_extract``
as two near-identical, copy-pasted functions that differ only in their
prompt wording and output field suffix. Here that duplication is
replaced with one ``ExtractionAgent`` class configured twice (see
``graph.py``), which:

* keeps the two prompts independently editable (still two distinct
  "opinions" for the compare/judge step to be meaningful), but
* removes duplicated parsing/error-handling logic, and
* makes it trivial to add a third, fourth, ... extraction agent later
  without copy-pasting another function.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from invoice_extraction.state import InvoiceState
from invoice_extraction.utils.cache import CacheBackend, InMemoryCache, cache_key
from invoice_extraction.utils.json_utils import extract_json
from invoice_extraction.utils.retry import with_retry

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = (
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "contractor_name",
    "date_or_range",
    "hours",
    "rate",
    "bill_amount",
)


@dataclass(frozen=True)
class ExtractionAgentConfig:
    """Everything that differs between "agent 1" and "agent 2"."""

    name: str                      # human-readable label used in the prompt, e.g. "Agent 1"
    state_key: str                 # which InvoiceState key to write to, e.g. "agent1_output"
    field_suffix: str = ""         # "_1" for agent 1 in the reference impl; kept optional/configurable
    prompt_template: str = (
        "You are an invoice data extraction agent ({agent_label}). Your job is to "
        "extract key fields from unstructured invoice text.\n"
        "Each invoice may contain one or more contractors. The contractor name does "
        "not appear on every line -- until you see a new name, keep repeating the "
        "contractor name from before.\n\n"
        "Extract and return a JSON array of objects with exactly these fields:\n"
        "- invoice_number{suffix} (string) -- e.g. \"Invoice: 0008508473\"\n"
        "- invoice_date{suffix} (string) -- e.g. \"Invoice Date: July 3, 2025\"\n"
        "- vendor_name{suffix} (string) -- text found between '@' and '.com' in a "
        "contact email, if present\n"
        "- contractor_name{suffix} (string)\n"
        "- date_or_range{suffix} (string)\n"
        "- hours{suffix} (number)\n"
        "- rate{suffix} (number)\n"
        "- bill_amount{suffix} (number)\n\n"
        "Each contractor line should be a separate object in the array. Repeat the "
        "invoice_number and invoice_date in each object. Only include rows with "
        "valid contractor data. Never invent values -- use null when a field is "
        "not present in the text.\n\n"
        "Return ONLY a raw JSON array. No markdown fences, no commentary.\n\n"
        "Invoice text:\n{raw_text}\n"
    )


class ExtractionAgent:
    """Runs one prompt against the shared chat model and parses its JSON output.

    Two optimizations sit between the prompt and the model call:

    * **Retry with backoff** -- transient model-serving errors (timeouts,
      429s) are retried instead of failing the whole invoice.
    * **Content-addressed caching** -- if the exact same cleaned invoice
      text has already been extracted by this agent (same prompt
      version), skip the LLM call entirely. This matters a lot for
      re-runs/retried Databricks Job tasks and for vendors who resend
      byte-identical invoices under a new filename.
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        config: ExtractionAgentConfig,
        *,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 1.0,
        retry_max_delay_seconds: float = 20.0,
        enable_cache: bool = True,
        prompt_version: str = "v1",
        cache: Optional[CacheBackend] = None,
    ):
        self._chat_model = chat_model
        self._config = config
        self._max_retries = max_retries
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._retry_max_delay_seconds = retry_max_delay_seconds
        self._enable_cache = enable_cache
        self._prompt_version = prompt_version
        # Defaults to a fresh, isolated cache scoped to THIS agent instance
        # (not a shared global) -- this is what makes it safe to build a
        # new graph per test / per tenant without any risk of one run's
        # cached extraction leaking into another's. Pass an explicit
        # `cache=` (e.g. shared between agent1/agent2 within one graph, see
        # graph.py) to widen the scope intentionally.
        self._cache: CacheBackend = cache if cache is not None else InMemoryCache()

    def build_prompt(self, raw_text: str) -> str:
        return self._config.prompt_template.format(
            agent_label=self._config.name,
            suffix=self._config.field_suffix,
            raw_text=raw_text,
        )

    def run(self, state: InvoiceState) -> InvoiceState:
        raw_text = state.get("raw_pdf_text", "")
        if not raw_text:
            logger.warning("%s: no raw_pdf_text in state, skipping extraction", self._config.name)
            return {self._config.state_key: []}

        key = cache_key(self._prompt_version, self._config.state_key, raw_text)
        if self._enable_cache:
            cached = self._cache.get(key)
            if cached is not None:
                logger.debug("%s: cache hit, skipping LLM call", self._config.name)
                return {self._config.state_key: cached}

        prompt = self.build_prompt(raw_text)
        started = time.monotonic()
        response = with_retry(
            lambda: self._chat_model.invoke([HumanMessage(content=prompt)]),
            max_retries=self._max_retries,
            base_delay_seconds=self._retry_base_delay_seconds,
            max_delay_seconds=self._retry_max_delay_seconds,
        )
        elapsed_ms = (time.monotonic() - started) * 1000
        content = getattr(response, "content", "") or ""

        extracted_data: List[dict] = extract_json(content)
        if not extracted_data:
            logger.warning("%s: produced no parseable rows", self._config.name)
        logger.debug("%s: LLM call took %.0fms, extracted %s row(s)", self._config.name, elapsed_ms, len(extracted_data))

        if self._enable_cache and extracted_data:
            self._cache.set(key, extracted_data)

        return {self._config.state_key: extracted_data}

    def as_node(self):
        """Return a LangGraph-compatible node function (``state -> partial state``)."""

        def _node(state: InvoiceState) -> InvoiceState:
            return self.run(state)

        _node.__name__ = f"extract_{self._config.state_key}"
        return _node
