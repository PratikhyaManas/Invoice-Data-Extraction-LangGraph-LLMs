"""
Batch orchestration: discover PDFs under ``config.storage.input_volume_path``
and run each one through the compiled LangGraph app.

Kept separate from ``graph.py`` so the graph itself stays a pure,
single-invoice unit that's easy to test, while this module owns the
"loop over a directory, parallelize, handle partial failures, move
processed files, report metrics" concerns a Databricks Job actually
needs.

Performance notes
------------------
* Invoices are processed **concurrently** with a thread pool
  (``config.max_concurrent_invoices`` workers). This is a plain
  ``ThreadPoolExecutor``, not multiprocessing, because the per-invoice
  work is I/O-bound (LLM HTTP calls, PDF reads) rather than CPU-bound --
  threads are the right tool and avoid the pickling overhead of
  multiprocessing for a LangGraph app + chat-model client.
* The LangGraph app and chat model are built **once** and shared across
  worker threads; each ``invoke()`` call gets its own state dict, so
  there's no shared mutable pipeline state to race on. The extraction
  cache (see ``utils/cache.py``) is intentionally thread-safe for the
  same reason.
* A failure in one invoice never blocks or cancels the others --
  results are collected as futures complete, not in submission order.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional

from invoice_extraction.config import PipelineConfig
from invoice_extraction.graph import build_invoice_graph
from invoice_extraction.state import InvoiceState, initial_state
from invoice_extraction.utils.cache import InMemoryCache

logger = logging.getLogger(__name__)


@dataclass
class InvoiceRunResult:
    invoice_path: str
    success: bool
    rows_written: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0
    flagged_for_review: bool = False


@dataclass
class BatchSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    flagged_for_review: int = 0
    total_duration_seconds: float = 0.0
    cache_stats: dict = field(default_factory=dict)
    results: List[InvoiceRunResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.succeeded / self.total if self.total else 1.0


def discover_invoices(input_volume_path: str, pattern: str = "*.pdf") -> List[str]:
    search_pattern = os.path.join(input_volume_path, pattern)
    return sorted(glob.glob(search_pattern))


def _invoice_id_from_path(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _process_one(app, path: str, config: PipelineConfig) -> InvoiceRunResult:
    started = time.monotonic()
    state: InvoiceState = initial_state(path, invoice_id=_invoice_id_from_path(path))
    try:
        final_state = app.invoke(state)
    except Exception as exc:  # noqa: BLE001 - one bad invoice must not kill the batch
        logger.exception("Unhandled error processing %s", path)
        return InvoiceRunResult(
            invoice_path=path, success=False, error=str(exc), duration_seconds=time.monotonic() - started
        )

    write_error = final_state.get("write_error")
    load_error = final_state.get("load_error")
    error = load_error or write_error

    return InvoiceRunResult(
        invoice_path=path,
        success=error is None,
        rows_written=final_state.get("rows_written", 0),
        error=error,
        duration_seconds=time.monotonic() - started,
        flagged_for_review=bool(final_state.get("flag_disagreement", False)),
    )


def run_batch(
    config: Optional[PipelineConfig] = None,
    invoice_paths: Optional[List[str]] = None,
    move_processed: bool = True,
) -> BatchSummary:
    """Run every discovered (or explicitly provided) invoice through the
    graph, concurrently, and return a structured summary.

    A failure on one invoice is isolated (logged + recorded) and never
    stops the batch. Concurrency is capped at
    ``config.max_concurrent_invoices`` to avoid overwhelming the LLM
    endpoint's rate limits.
    """
    config = config or PipelineConfig()
    config.validate_for_production()

    paths = invoice_paths or discover_invoices(config.storage.input_volume_path)
    if not paths:
        logger.warning("No invoices found under %s", config.storage.input_volume_path)
        return BatchSummary()

    # One cache, shared by agent1/agent2, scoped to this batch run -- lets
    # duplicate/re-run invoices within the same job execution skip
    # redundant LLM calls, without leaking across separate job runs.
    batch_cache = InMemoryCache()
    app = build_invoice_graph(config, cache=batch_cache)
    results: List[InvoiceRunResult] = []
    batch_started = time.monotonic()

    max_workers = max(1, min(config.max_concurrent_invoices, len(paths)))
    logger.info("Processing %s invoice(s) with %s concurrent worker(s)", len(paths), max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {executor.submit(_process_one, app, path, config): path for path in paths}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - defensive: _process_one already catches its own errors
                logger.exception("Executor-level failure processing %s", path)
                result = InvoiceRunResult(invoice_path=path, success=False, error=str(exc))
            results.append(result)

            destination = (
                config.storage.archive_volume_path if result.success else config.storage.quarantine_volume_path
            )
            _maybe_move(path, destination, move_processed)

    total_duration = time.monotonic() - batch_started
    summary = _build_summary(results, total_duration, batch_cache)
    _log_summary(summary)
    return summary


def _maybe_move(path: str, destination_dir: str, move_processed: bool) -> None:
    if not move_processed:
        return
    try:
        os.makedirs(destination_dir, exist_ok=True)
        shutil.move(path, os.path.join(destination_dir, os.path.basename(path)))
    except Exception:  # noqa: BLE001 - archival is best-effort, never fatal to the pipeline
        logger.exception("Failed to move %s to %s", path, destination_dir)


def _build_summary(results: List[InvoiceRunResult], total_duration: float, cache: InMemoryCache) -> BatchSummary:
    succeeded = sum(1 for r in results if r.success)
    flagged = sum(1 for r in results if r.flagged_for_review)
    return BatchSummary(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        flagged_for_review=flagged,
        total_duration_seconds=round(total_duration, 2),
        cache_stats=cache.stats(),
        results=results,
    )


def _log_summary(summary: BatchSummary) -> None:
    logger.info(
        "Batch complete: %s/%s succeeded (%.1f%%), %s flagged for review, %.2fs wall clock, cache hit rate %.1f%%",
        summary.succeeded,
        summary.total,
        summary.success_rate * 100,
        summary.flagged_for_review,
        summary.total_duration_seconds,
        summary.cache_stats.get("hit_rate", 0.0) * 100,
    )
    for r in summary.results:
        if not r.success:
            logger.error("FAILED %s (%.2fs): %s", r.invoice_path, r.duration_seconds, r.error)
