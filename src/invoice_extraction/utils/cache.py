"""
Content-addressed cache for extraction-agent results.

Two situations make this worth having in a Databricks job:

1. **Re-runs**: a job retry or a manually re-triggered run should not
   re-pay for LLM calls on invoices it already successfully processed
   in this process's lifetime.
2. **Duplicate content**: some vendors resend byte-identical invoices
   (different filename, same PDF). Hashing the *cleaned text* rather
   than the file means these are recognized as duplicates even when
   the filename differs.

This is intentionally a simple two-tier cache:

* An in-memory ``dict`` (fast, free, scoped to one job run / one driver
  process -- exactly what a Databricks Job task needs).
* An optional pluggable backend (``CacheBackend`` protocol) so a longer-
  lived store (e.g. a small Delta table, or Databricks' key-value
  feature store) can be swapped in without touching call sites.

Caching is opt-in via ``PipelineConfig.enable_llm_cache`` and never
required for correctness -- a cache miss just means "call the LLM."
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


def cache_key(*parts: str) -> str:
    """Stable content hash for a set of string parts (prompt version,
    agent name, cleaned invoice text, ...)."""
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


class CacheBackend(Protocol):
    def get(self, key: str) -> Optional[List[Dict[str, Any]]]: ...

    def set(self, key: str, value: List[Dict[str, Any]]) -> None: ...


class InMemoryCache:
    """Thread-safe LRU-ish cache (simple size-capped dict) for use within
    a single driver process / job run."""

    def __init__(self, max_entries: int = 2048):
        self._max_entries = max_entries
        self._store: "Dict[str, List[Dict[str, Any]]]" = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        with self._lock:
            value = self._store.get(key)
            if value is not None:
                self.hits += 1
            else:
                self.misses += 1
            return value

    def set(self, key: str, value: List[Dict[str, Any]]) -> None:
        with self._lock:
            if len(self._store) >= self._max_entries:
                # Evict an arbitrary (oldest-inserted, dict-ordered) entry
                # rather than pulling in a dependency for true LRU -- this
                # cache exists to save API calls, not to be a perfect LRU.
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
            self._store[key] = value

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def stats(self) -> Dict[str, Any]:
        return {"hits": self.hits, "misses": self.misses, "hit_rate": round(self.hit_rate, 4), "size": len(self._store)}


# One process-wide default cache, shared across agents within a job run.
# Explicitly constructed (not a bare module-level dict) so tests can
# create an isolated instance instead of sharing global state.
default_cache = InMemoryCache()
