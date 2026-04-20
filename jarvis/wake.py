"""Simple keyword-based wake word detector.

No external service or model needed. Matches "jarvis" (or any configured
alias) as a whole word in a transcript.
"""

from __future__ import annotations

import re
from typing import Iterable


class WakeWordDetector:
    def __init__(self, words: Iterable[str] = ("jarvis",)) -> None:
        joined = "|".join(re.escape(w.lower()) for w in words)
        self._pattern = re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)

    def triggered(self, transcript: str) -> bool:
        if not transcript:
            return False
        return self._pattern.search(transcript) is not None

    def strip_wake(self, transcript: str) -> str:
        """Remove leading wake word(s) so the remainder can be sent as a query."""
        return self._pattern.sub("", transcript, count=1).strip(" ,.:;-")