"""
persist_results node: write the reconciled extraction to a Delta table.

This is the Databricks analogue of the reference notebook's
``write_to_bigquery``. Key differences:

* ``build_result_dataframe`` is pure pandas and has no Spark/Databricks
  dependency, so it is fully unit-testable.
* ``write_to_delta`` does the actual Spark write, guarded by
  ``write_mode`` ("append" for a simple audit-log style table, or
  "merge" for idempotent re-runs keyed by ``invoice_id``).
* No hard-coded project/dataset/table -- comes entirely from
  ``PipelineConfig.storage``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from invoice_extraction.config import PipelineConfig
from invoice_extraction.state import InvoiceState
from invoice_extraction.storage.schema import RESULT_SCHEMA

logger = logging.getLogger(__name__)

_A1_COLS = [
    "invoice_number_1", "invoice_date_1", "vendor_name_1", "contractor_name_1",
    "date_or_range_1", "hours_1", "rate_1", "bill_amount_1",
]
_A2_COLS = [
    "invoice_number", "invoice_date", "vendor_name", "contractor_name",
    "date_or_range", "hours", "rate", "bill_amount",
]


def _ensure_cols(records: Optional[List[Dict[str, Any]]], cols: List[str]) -> pd.DataFrame:
    if not records:
        df = pd.DataFrame(columns=cols)
    else:
        df = pd.json_normalize(records)
    for col in cols:
        if col not in df.columns:
            df[col] = pd.NA
    return df[cols]


def build_result_dataframe(state: InvoiceState) -> pd.DataFrame:
    """Flatten agent1/agent2/judge outputs into one row-aligned DataFrame
    matching ``RESULT_SCHEMA``. Pure pandas -- safe to unit test."""
    agent1_output = state.get("agent1_output", [])
    agent2_output = state.get("agent2_output", [])

    df1 = _ensure_cols(agent1_output, _A1_COLS)
    df2 = _ensure_cols(agent2_output, _A2_COLS)

    # If the two agents disagreed on row *count*, they can't be zipped
    # column-wise; pad the shorter one with nulls so nothing is silently
    # dropped from the audit trail.
    max_len = max(len(df1), len(df2), 1)
    df1 = df1.reindex(range(max_len))
    df2 = df2.reindex(range(max_len))

    combined = pd.concat([df1.reset_index(drop=True), df2.reset_index(drop=True)], axis=1)

    combined.insert(0, "invoice_path", state.get("invoice_path"))
    combined.insert(0, "invoice_id", state.get("invoice_id", state.get("invoice_path")))
    combined["match"] = str(state.get("match", False))
    combined["agent_winner"] = state.get("agent_winner", "none")
    combined["justification"] = state.get("justification", "no disagreement")
    combined["ingested_at"] = datetime.now(timezone.utc)

    return combined[RESULT_SCHEMA]


def write_to_delta(state: InvoiceState, config: PipelineConfig, spark=None) -> InvoiceState:
    """LangGraph node: persist ``state`` to the configured Delta table.

    ``spark`` is injected so this is testable with a local/mock session;
    on a real Databricks notebook/job, omit it and the active
    ``SparkSession`` is used automatically.
    """
    try:
        combined_df = build_result_dataframe(state)

        if spark is None:
            from pyspark.sql import SparkSession

            spark = SparkSession.getActiveSession()
            if spark is None:
                raise RuntimeError("No active SparkSession found and none was provided")

        from invoice_extraction.storage.schema import get_result_struct_type

        spark_df = spark.createDataFrame(combined_df, schema=get_result_struct_type())

        target_table = config.full_table_name

        if config.storage.write_mode == "merge":
            _merge_into_delta(spark, spark_df, target_table)
        else:
            spark_df.write.format("delta").mode("append").saveAsTable(target_table)

        logger.info("Wrote %s rows to %s", combined_df.shape[0], target_table)
        return {"rows_written": combined_df.shape[0], "write_error": None}

    except Exception as exc:  # noqa: BLE001 - persistence failures must not crash the whole batch
        logger.exception("Failed writing invoice %s to Delta", state.get("invoice_path"))
        return {"rows_written": 0, "write_error": f"{type(exc).__name__}: {exc}"}


def _merge_into_delta(spark, spark_df, target_table: str) -> None:
    """Idempotent upsert keyed by invoice_id, so re-running a job for the
    same invoice does not duplicate rows."""
    from delta.tables import DeltaTable

    if not spark.catalog.tableExists(target_table):
        spark_df.write.format("delta").mode("append").saveAsTable(target_table)
        return

    delta_table = DeltaTable.forName(spark, target_table)
    (
        delta_table.alias("target")
        .merge(spark_df.alias("source"), "target.invoice_id = source.invoice_id")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
