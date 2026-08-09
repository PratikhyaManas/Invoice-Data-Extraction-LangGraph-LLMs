"""
invoice_extraction
===================

A modular, reusable LangGraph pipeline for AI-powered invoice data
extraction on Databricks (Unity Catalog Volumes for storage, Delta
Lake for the warehouse layer, and Databricks Model Serving / any
LangChain chat model for the LLM agents).

This package intentionally mirrors the multi-agent "extract -> compare
-> judge -> persist" pattern popularised for BigQuery pipelines, but
every I/O boundary (file storage, warehouse, LLM provider) is swapped
for a small interface so it can be reused outside Databricks too.
"""

from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("invoice-extraction-databricks")
except _metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
