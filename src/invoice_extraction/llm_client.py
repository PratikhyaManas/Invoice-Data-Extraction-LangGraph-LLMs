"""
LLM client factory.

The reference implementation hard-codes ``ChatVertexAI`` in the module
body, which makes it impossible to unit test without live Google Cloud
credentials. Here, model construction is deferred behind a factory so:

* Production on Databricks uses ``ChatDatabricks`` against a Model
  Serving endpoint (Databricks-hosted foundation model, a fine-tuned
  model, or an external-model gateway to OpenAI/Anthropic/etc. -- the
  endpoint is just a name, the pipeline code never changes).
* Local/CI unit tests use a scripted ``FakeChatModel`` so the whole
  graph can be exercised with zero network calls and zero API cost.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage

from invoice_extraction.config import LLMConfig


class UnsupportedProviderError(ValueError):
    pass


class FakeChatModel(BaseChatModel):
    """Deterministic stand-in for a real chat model, used in tests.

    ``responses`` is consumed in order; each call to ``invoke`` pops the
    next scripted response. This lets tests assert exact agent/graph
    behavior without any network access.
    """

    responses: List[str] = []
    _call_count: int = 0

    def __init__(self, responses: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "responses", responses or [])
        object.__setattr__(self, "_call_count", 0)

    def _generate(self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs):
        from langchain_core.outputs import ChatGeneration, ChatResult

        idx = min(self._call_count, len(self.responses) - 1) if self.responses else -1
        text = self.responses[idx] if idx >= 0 else "[]"
        object.__setattr__(self, "_call_count", self._call_count + 1)
        message = AIMessage(content=text)
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def invoke(self, input, config=None, **kwargs) -> AIMessage:  # type: ignore[override]
        messages = input if isinstance(input, list) else [input]
        result = self._generate(messages)
        return result.generations[0].message


def _build_databricks_model(config: LLMConfig) -> BaseChatModel:
    from databricks_langchain import ChatDatabricks  # requires `databricks-langchain`

    return ChatDatabricks(
        endpoint=config.endpoint,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )


def _build_openai_model(config: LLMConfig) -> BaseChatModel:
    from langchain_openai import ChatOpenAI  # optional dependency, only needed for this provider

    return ChatOpenAI(
        model=config.endpoint,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout_seconds,
    )


_PROVIDER_BUILDERS: dict[str, Callable[[LLMConfig], BaseChatModel]] = {
    "databricks": _build_databricks_model,
    "openai": _build_openai_model,
}


def build_chat_model(config: LLMConfig, fake_responses: Optional[List[str]] = None) -> BaseChatModel:
    """Construct the chat model described by ``config``.

    Pass ``fake_responses`` (or set ``config.provider == "fake"``) to get
    a scripted ``FakeChatModel`` for tests.
    """
    if config.provider == "fake" or fake_responses is not None:
        return FakeChatModel(responses=fake_responses)

    builder = _PROVIDER_BUILDERS.get(config.provider)
    if builder is None:
        raise UnsupportedProviderError(
            f"Unknown llm provider {config.provider!r}. Supported: "
            f"{sorted(_PROVIDER_BUILDERS)} or 'fake'."
        )
    return builder(config)
