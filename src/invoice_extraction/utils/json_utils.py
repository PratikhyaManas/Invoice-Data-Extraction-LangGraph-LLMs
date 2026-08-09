"""
Utilities for coaxing well-formed JSON out of LLM chat responses.

LLMs frequently wrap JSON in markdown fences, add a leading sentence,
or emit a single object instead of the requested array. This module
centralizes that recovery logic instead of duplicating a bespoke regex
in every agent (as the original notebook did per-agent).
"""

from __future__ import annotations

import json
import re
from typing import Any, List

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_ARRAY_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> List[Any]:
    """Best-effort extraction of a JSON array from raw LLM text.

    Tries, in order:
      1. Direct ``json.loads``.
      2. Content inside a ```json ... ``` fenced block.
      3. The first ``[...]`` array-looking substring.
      4. The first ``{...}`` object-looking substring, wrapped in a list.

    Returns an empty list (never raises) if nothing parses, so callers
    can treat "no data extracted" uniformly regardless of the failure
    mode -- this is important for pipeline resilience since a single
    malformed LLM response should not crash the whole invoice batch.
    """
    if not text:
        return []

    candidates = [text]

    fence_match = _FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1))

    for candidate in candidates:
        parsed = _try_parse(candidate)
        if parsed is not None:
            return parsed

    array_match = _ARRAY_RE.search(text)
    if array_match:
        parsed = _try_parse(array_match.group())
        if parsed is not None:
            return parsed

    object_match = _OBJECT_RE.search(text)
    if object_match:
        parsed = _try_parse(object_match.group())
        if parsed is not None:
            return parsed if isinstance(parsed, list) else [parsed]

    return []


def _try_parse(candidate: str) -> Any:
    try:
        value = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return None
