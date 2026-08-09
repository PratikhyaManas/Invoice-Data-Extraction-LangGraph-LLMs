"""
Central, environment-driven configuration for the pipeline.

Design goals
------------
* No hard-coded secrets, project IDs, or paths (unlike the BigQuery
  reference implementation which hard-codes ``PROJECT_ID`` /
  ``your-project-id`` inline).
* Works both as a Databricks Job (env vars / job parameters) and as an
  ad-hoc notebook (``dbutils.widgets``) without code changes elsewhere.
* Every field is validated eagerly via ``PipelineConfig.from_env`` so a
  mis-configured job fails fast at start-up instead of mid-pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    value = os.environ.get(name, default)
    if required and not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the chat model used by every agent.

    ``provider`` selects the LangChain integration so the same pipeline
    can run against Databricks Foundation Model APIs, a Unity-Catalog
    hosted external model, or (for local testing) any other
    LangChain-compatible chat model.
    """

    provider: str = "databricks"          # "databricks" | "openai" | "fake"
    endpoint: str = "databricks-meta-llama-3-3-70b-instruct"
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: int = 120
    max_retries: int = 3
    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 20.0
    enable_cache: bool = True
    prompt_version: str = "v1"  # bump to invalidate the cache after a prompt-wording change


@dataclass(frozen=True)
class StorageConfig:
    """Where invoices are read from and where results are written.

    Databricks equivalents of the reference article's GCS bucket and
    BigQuery table:
      * ``input_volume_path``  -> Unity Catalog Volume holding PDFs
                                   (e.g. /Volumes/finance/invoices/raw_pdfs)
      * ``catalog``/``schema``/``table`` -> Delta table in Unity Catalog
      * ``checkpoint_path``    -> optional Structured Streaming checkpoint
                                   if run in streaming/autoloader mode
    """

    input_volume_path: str = "/Volumes/finance/invoices/raw_pdfs"
    archive_volume_path: str = "/Volumes/finance/invoices/processed_pdfs"
    quarantine_volume_path: str = "/Volumes/finance/invoices/quarantine_pdfs"
    catalog: str = "finance"
    schema: str = "invoices"
    table: str = "invoice_extractions"
    checkpoint_path: Optional[str] = None
    write_mode: str = "append"  # "append" | "merge"


@dataclass(frozen=True)
class PipelineConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    enable_ocr_fallback: bool = True
    max_concurrent_invoices: int = 8
    log_level: str = "INFO"

    @staticmethod
    def from_env(prefix: str = "INVOICE_PIPELINE_") -> "PipelineConfig":
        """Build a config from environment variables / job parameters.

        Every variable is optional and falls back to sane defaults so
        this also works unmodified in local unit tests. Required-only-
        in-production values (e.g. a real Unity Catalog path) should be
        validated by the caller (see ``validate_for_production``).
        """
        llm = LLMConfig(
            provider=_get_env(f"{prefix}LLM_PROVIDER", "databricks"),
            endpoint=_get_env(f"{prefix}LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct"),
            temperature=float(_get_env(f"{prefix}LLM_TEMPERATURE", "0.0")),
            max_tokens=int(_get_env(f"{prefix}LLM_MAX_TOKENS", "4096")),
            timeout_seconds=int(_get_env(f"{prefix}LLM_TIMEOUT_SECONDS", "120")),
            max_retries=int(_get_env(f"{prefix}LLM_MAX_RETRIES", "3")),
            retry_base_delay_seconds=float(_get_env(f"{prefix}LLM_RETRY_BASE_DELAY_SECONDS", "1.0")),
            retry_max_delay_seconds=float(_get_env(f"{prefix}LLM_RETRY_MAX_DELAY_SECONDS", "20.0")),
            enable_cache=_get_env(f"{prefix}LLM_ENABLE_CACHE", "true").lower() == "true",
            prompt_version=_get_env(f"{prefix}LLM_PROMPT_VERSION", "v1"),
        )
        storage = StorageConfig(
            input_volume_path=_get_env(f"{prefix}INPUT_VOLUME_PATH", "/Volumes/finance/invoices/raw_pdfs"),
            archive_volume_path=_get_env(
                f"{prefix}ARCHIVE_VOLUME_PATH", "/Volumes/finance/invoices/processed_pdfs"
            ),
            quarantine_volume_path=_get_env(
                f"{prefix}QUARANTINE_VOLUME_PATH", "/Volumes/finance/invoices/quarantine_pdfs"
            ),
            catalog=_get_env(f"{prefix}CATALOG", "finance"),
            schema=_get_env(f"{prefix}SCHEMA", "invoices"),
            table=_get_env(f"{prefix}TABLE", "invoice_extractions"),
            checkpoint_path=_get_env(f"{prefix}CHECKPOINT_PATH"),
            write_mode=_get_env(f"{prefix}WRITE_MODE", "append"),
        )
        return PipelineConfig(
            llm=llm,
            storage=storage,
            enable_ocr_fallback=_get_env(f"{prefix}ENABLE_OCR_FALLBACK", "true").lower() == "true",
            max_concurrent_invoices=int(_get_env(f"{prefix}MAX_CONCURRENT_INVOICES", "8")),
            log_level=_get_env(f"{prefix}LOG_LEVEL", "INFO"),
        )

    def validate_for_production(self) -> None:
        """Extra checks worth enforcing before a real Databricks Job run."""
        if self.storage.write_mode not in {"append", "merge"}:
            raise ConfigError("storage.write_mode must be 'append' or 'merge'")
        if "your-project-id" in (self.storage.catalog or ""):
            raise ConfigError("storage.catalog looks like an unfilled placeholder")
        if self.llm.provider not in {"databricks", "openai", "fake"}:
            raise ConfigError(f"Unsupported llm.provider: {self.llm.provider}")

    @property
    def full_table_name(self) -> str:
        return f"{self.storage.catalog}.{self.storage.schema}.{self.storage.table}"
