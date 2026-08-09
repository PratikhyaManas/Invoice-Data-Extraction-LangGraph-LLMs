# Databricks notebook source
# MAGIC %md
# MAGIC # Invoice Extraction Pipeline — Run
# MAGIC
# MAGIC Entry point notebook for the modular `invoice_extraction` package.
# MAGIC Reads invoice PDFs from a Unity Catalog Volume, runs the LangGraph
# MAGIC multi-agent extraction workflow, and writes reconciled results to a
# MAGIC Delta table. Designed to be attached to a Databricks Job (see
# MAGIC `jobs/invoice_pipeline_job.yml`) or run ad-hoc.

# COMMAND ----------

# MAGIC %pip install -r ../requirements.txt
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import logging

from invoice_extraction.config import PipelineConfig, StorageConfig, LLMConfig
from invoice_extraction.runner import run_batch

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widgets
# MAGIC Every value is overridable as a Job parameter or notebook widget so
# MAGIC the same notebook serves dev / staging / prod without code edits.

# COMMAND ----------

dbutils.widgets.text("input_volume_path", "/Volumes/finance/invoices/raw_pdfs")
dbutils.widgets.text("archive_volume_path", "/Volumes/finance/invoices/processed_pdfs")
dbutils.widgets.text("quarantine_volume_path", "/Volumes/finance/invoices/quarantine_pdfs")
dbutils.widgets.text("catalog", "finance")
dbutils.widgets.text("schema", "invoices")
dbutils.widgets.text("table", "invoice_extractions")
dbutils.widgets.dropdown("write_mode", "merge", ["append", "merge"])
dbutils.widgets.text("llm_endpoint", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.dropdown("log_level", "INFO", ["DEBUG", "INFO", "WARNING", "ERROR"])
dbutils.widgets.text("max_concurrent_invoices", "8")
dbutils.widgets.dropdown("enable_llm_cache", "true", ["true", "false"])

# COMMAND ----------

config = PipelineConfig(
    llm=LLMConfig(
        provider="databricks",
        endpoint=dbutils.widgets.get("llm_endpoint"),
        temperature=0.0,
        enable_cache=dbutils.widgets.get("enable_llm_cache") == "true",
    ),
    storage=StorageConfig(
        input_volume_path=dbutils.widgets.get("input_volume_path"),
        archive_volume_path=dbutils.widgets.get("archive_volume_path"),
        quarantine_volume_path=dbutils.widgets.get("quarantine_volume_path"),
        catalog=dbutils.widgets.get("catalog"),
        schema=dbutils.widgets.get("schema"),
        table=dbutils.widgets.get("table"),
        write_mode=dbutils.widgets.get("write_mode"),
    ),
    max_concurrent_invoices=int(dbutils.widgets.get("max_concurrent_invoices")),
    log_level=dbutils.widgets.get("log_level"),
)
config.validate_for_production()

logging.basicConfig(level=config.log_level)

# COMMAND ----------

# MAGIC %md
# MAGIC Make sure the target schema/volumes exist (idempotent, safe to re-run).

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {config.storage.catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {config.storage.catalog}.{config.storage.schema}")
for volume_path in (
    config.storage.input_volume_path,
    config.storage.archive_volume_path,
    config.storage.quarantine_volume_path,
):
    volume_name = volume_path.rstrip("/").split("/")[-1]
    spark.sql(
        f"CREATE VOLUME IF NOT EXISTS {config.storage.catalog}.{config.storage.schema}.{volume_name}"
    )

# COMMAND ----------

summary = run_batch(config)

print(
    f"{summary.succeeded}/{summary.total} succeeded ({summary.success_rate:.1%}), "
    f"{summary.flagged_for_review} flagged for review, "
    f"{summary.total_duration_seconds}s wall clock, "
    f"cache hit rate {summary.cache_stats.get('hit_rate', 0.0):.1%}"
)

# COMMAND ----------

display(
    spark.createDataFrame(
        [
            (r.invoice_path, r.success, r.rows_written, r.error, r.duration_seconds, r.flagged_for_review)
            for r in summary.results
        ],
        schema=(
            "invoice_path string, success boolean, rows_written int, error string, "
            "duration_seconds double, flagged_for_review boolean"
        ),
    )
)

# COMMAND ----------

if summary.failed > 0:
    raise RuntimeError(f"{summary.failed} of {summary.total} invoices failed to process; see task logs above.")
