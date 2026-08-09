import pytest

from invoice_extraction.config import ConfigError, LLMConfig, PipelineConfig, StorageConfig


def test_default_config_builds_without_error():
    config = PipelineConfig()
    assert config.llm.provider == "databricks"
    assert config.full_table_name == "finance.invoices.invoice_extractions"


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("INVOICE_PIPELINE_LLM_PROVIDER", "fake")
    monkeypatch.setenv("INVOICE_PIPELINE_CATALOG", "acme")
    monkeypatch.setenv("INVOICE_PIPELINE_SCHEMA", "ap")
    monkeypatch.setenv("INVOICE_PIPELINE_TABLE", "invoices")

    config = PipelineConfig.from_env()

    assert config.llm.provider == "fake"
    assert config.full_table_name == "acme.ap.invoices"


def test_validate_for_production_rejects_placeholder_catalog():
    config = PipelineConfig(storage=StorageConfig(catalog="your-project-id"))
    with pytest.raises(ConfigError):
        config.validate_for_production()


def test_validate_for_production_rejects_bad_write_mode():
    config = PipelineConfig(storage=StorageConfig(write_mode="overwrite"))
    with pytest.raises(ConfigError):
        config.validate_for_production()


def test_validate_for_production_accepts_sane_defaults():
    config = PipelineConfig(storage=StorageConfig(catalog="finance"))
    config.validate_for_production()  # should not raise
