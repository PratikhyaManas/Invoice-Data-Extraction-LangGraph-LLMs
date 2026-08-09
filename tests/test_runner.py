import json
import time

from invoice_extraction import runner as runner_module
from invoice_extraction.config import LLMConfig, PipelineConfig, StorageConfig
from invoice_extraction.llm_client import FakeChatModel


def _matching_responses():
    a1 = json.dumps([{"invoice_number_1": "INV-1", "contractor_name_1": "Doe, John", "bill_amount_1": 750.0}])
    a2 = json.dumps([{"invoice_number": "INV-1", "contractor_name": "Doe, John", "bill_amount": 750.0}])
    return a1, a2


def test_run_batch_processes_all_invoices_concurrently(tmp_path, monkeypatch):
    input_dir = tmp_path / "raw"
    archive_dir = tmp_path / "archive"
    quarantine_dir = tmp_path / "quarantine"
    input_dir.mkdir()

    invoice_paths = []
    for i in range(4):
        p = input_dir / f"invoice_{i}.pdf"
        p.write_bytes(b"%PDF-1.4 placeholder")
        invoice_paths.append(str(p))

    monkeypatch.setattr(
        runner_module,
        "build_invoice_graph",
        lambda config, cache=None: _FakeApp(match=True),
    )

    config = PipelineConfig(
        llm=LLMConfig(provider="fake"),
        storage=StorageConfig(
            input_volume_path=str(input_dir),
            archive_volume_path=str(archive_dir),
            quarantine_volume_path=str(quarantine_dir),
            catalog="finance",
        ),
        max_concurrent_invoices=4,
    )

    summary = runner_module.run_batch(config)

    assert summary.total == 4
    assert summary.succeeded == 4
    assert summary.failed == 0
    # all input files were moved out of the input dir (archived)
    assert list(input_dir.glob("*.pdf")) == []
    assert len(list(archive_dir.glob("*.pdf"))) == 4


def test_run_batch_isolates_per_invoice_failures(tmp_path, monkeypatch):
    input_dir = tmp_path / "raw"
    archive_dir = tmp_path / "archive"
    quarantine_dir = tmp_path / "quarantine"
    input_dir.mkdir()

    good = input_dir / "good.pdf"
    bad = input_dir / "bad.pdf"
    good.write_bytes(b"%PDF-1.4")
    bad.write_bytes(b"%PDF-1.4")

    def fake_build(config, cache=None):
        return _FakeApp(match=True, fail_on_substring="bad")

    monkeypatch.setattr(runner_module, "build_invoice_graph", fake_build)

    config = PipelineConfig(
        llm=LLMConfig(provider="fake"),
        storage=StorageConfig(
            input_volume_path=str(input_dir),
            archive_volume_path=str(archive_dir),
            quarantine_volume_path=str(quarantine_dir),
            catalog="finance",
        ),
        max_concurrent_invoices=2,
    )

    summary = runner_module.run_batch(config)

    assert summary.total == 2
    assert summary.succeeded == 1
    assert summary.failed == 1
    assert len(list(archive_dir.glob("*.pdf"))) == 1
    assert len(list(quarantine_dir.glob("*.pdf"))) == 1


class _FakeApp:
    """Stand-in for the compiled LangGraph app used only to exercise
    runner.py's concurrency/error-isolation logic in isolation from the
    real graph (which is covered separately in test_graph.py)."""

    def __init__(self, match: bool, fail_on_substring: str | None = None):
        self._match = match
        self._fail_on_substring = fail_on_substring

    def invoke(self, state):
        time.sleep(0.01)  # simulate a bit of I/O-bound work
        path = state.get("invoice_path", "")
        if self._fail_on_substring and self._fail_on_substring in path:
            return {**state, "load_error": "simulated failure", "rows_written": 0}
        return {**state, "match": self._match, "rows_written": 1, "write_error": None, "load_error": None}
