"""
Delta table schema for extraction results.

Direct analogue of the ``bigquery.SchemaField`` list in the reference
notebook, expressed as a Spark ``StructType`` for Unity Catalog /
Delta Lake instead. Imported lazily wherever PySpark is required so
this package stays importable (e.g. for unit tests) on a machine
without PySpark installed.
"""

from __future__ import annotations


def get_result_struct_type():
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType, TimestampType

    return StructType(
        [
            # -- invoice-level identifiers (duplicated across both agents' rows
            #    for easy filtering/joining downstream) --
            StructField("invoice_id", StringType(), nullable=False),
            StructField("invoice_path", StringType(), nullable=True),
            # -- agent 1 --
            StructField("invoice_number_1", StringType(), nullable=True),
            StructField("invoice_date_1", StringType(), nullable=True),
            StructField("vendor_name_1", StringType(), nullable=True),
            StructField("contractor_name_1", StringType(), nullable=True),
            StructField("date_or_range_1", StringType(), nullable=True),
            StructField("hours_1", DoubleType(), nullable=True),
            StructField("rate_1", DoubleType(), nullable=True),
            StructField("bill_amount_1", DoubleType(), nullable=True),
            # -- agent 2 --
            StructField("invoice_number", StringType(), nullable=True),
            StructField("invoice_date", StringType(), nullable=True),
            StructField("vendor_name", StringType(), nullable=True),
            StructField("contractor_name", StringType(), nullable=True),
            StructField("date_or_range", StringType(), nullable=True),
            StructField("hours", DoubleType(), nullable=True),
            StructField("rate", DoubleType(), nullable=True),
            StructField("bill_amount", DoubleType(), nullable=True),
            # -- resolution metadata --
            StructField("match", StringType(), nullable=True),  # "true"/"false" as string for BI-tool friendliness
            StructField("agent_winner", StringType(), nullable=True),
            StructField("justification", StringType(), nullable=True),
            StructField("ingested_at", TimestampType(), nullable=False),
        ]
    )


# Plain-Python description (no PySpark import needed) used by both the
# writer's pandas fallback and unit tests.
RESULT_SCHEMA = [
    "invoice_id",
    "invoice_path",
    "invoice_number_1",
    "invoice_date_1",
    "vendor_name_1",
    "contractor_name_1",
    "date_or_range_1",
    "hours_1",
    "rate_1",
    "bill_amount_1",
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "contractor_name",
    "date_or_range",
    "hours",
    "rate",
    "bill_amount",
    "match",
    "agent_winner",
    "justification",
    "ingested_at",
]
