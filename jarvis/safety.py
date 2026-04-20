"""Safety guards for voice-originated text.

Voice transcripts are untrusted input. Before passing to the agent we:
- cap length to prevent prompt-flood / cost abuse
- strip control chars
- reject empty / whitespace-only text
- block obvious shell/code-exec patterns from leaking into any future
  tool-use code path (defense in depth; current pipeline does not exec
  shell, but we enforce the invariant here so it cannot regress)
"""

from __future__ import annotations

import re
import unicodedata

MAX_INPUT_CHARS = 1000
MIN_INPUT_CHARS = 2

# Patterns that should never appear in a legitimate spoken question.
# Match on the normalised, lowercased transcript.
_BLOCKED_PATTERNS = [
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\b(exec|eval)\s*\("),
    re.compile(r"\bos\.system\b"),
    re.compile(r"\bsubprocess\."),
    re.compile(r"\b__import__\b"),
    re.compile(r"</?script\b", re.IGNORECASE),
    re.compile(r"\bfile:\/\/"),
]


class UnsafeInputError(ValueError):
    """Raised when transcript fails a safety check."""


def _strip_controls(text: str) -> str:
    return "".join(
        ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t", " ")
    )


def sanitize(text: str) -> str:
    """Return a cleaned transcript or raise UnsafeInputError."""
    if text is None:
        raise UnsafeInputError("empty input")

    cleaned = _strip_controls(text).strip()
    if len(cleaned) < MIN_INPUT_CHARS:
        raise UnsafeInputError("input too short")
    if len(cleaned) > MAX_INPUT_CHARS:
        raise UnsafeInputError(f"input exceeds {MAX_INPUT_CHARS} chars")

    lowered = cleaned.lower()
    for pat in _BLOCKED_PATTERNS:
        if pat.search(lowered):
            raise UnsafeInputError(f"blocked pattern: {pat.pattern}")

    return cleaned