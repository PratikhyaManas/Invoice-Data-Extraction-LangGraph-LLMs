import pytest

from invoice_extraction.utils.retry import with_retry


class RateLimitError(Exception):
    """Named to match the retryable-exception heuristic in retry.py."""


def test_with_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)  # skip real backoff delay in tests
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitError("rate limited")
        return "ok"

    result = with_retry(flaky, max_retries=5, base_delay_seconds=0.01)
    assert result == "ok"
    assert calls["n"] == 3


def test_with_retry_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)

    def always_fails():
        raise RateLimitError("nope")

    with pytest.raises(RateLimitError):
        with_retry(always_fails, max_retries=2, base_delay_seconds=0.01)


def test_with_retry_does_not_retry_non_transient_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = {"n": 0}

    def bad_prompt():
        calls["n"] += 1
        raise ValueError("this will never succeed no matter how many times we retry")

    with pytest.raises(ValueError):
        with_retry(bad_prompt, max_retries=5, base_delay_seconds=0.01)

    assert calls["n"] == 1  # failed fast, no retries wasted on a non-transient error


def test_with_retry_calls_on_retry_callback(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    seen = []

    def flaky():
        if len(seen) < 1:
            raise RateLimitError("rate limited")
        return "ok"

    result = with_retry(
        flaky, max_retries=3, base_delay_seconds=0.01, on_retry=lambda attempt, exc: seen.append(attempt)
    )
    assert result == "ok"
    assert seen == [1]
