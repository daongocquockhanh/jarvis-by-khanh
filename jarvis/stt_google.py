"""Google Web Speech API transcriber (network, free tier).

Reconstructs an AudioData from WAV bytes so it shares the same
`transcribe(wav: bytes) -> str | None` interface as the local whisper
backend. Deferred speech_recognition import keeps the base install light.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GoogleTranscriber:
    def __init__(self) -> None:
        import speech_recognition as sr  # deferred

        self._sr = sr
        self._recognizer = sr.Recognizer()

    def transcribe(self, wav: bytes) -> Optional[str]:
        sr = self._sr
        try:
            with sr.AudioFile(io.BytesIO(wav)) as source:
                audio = self._recognizer.record(source)
            text = self._recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            logger.warning("Google STT request error")
            return None
        except (ConnectionResetError, ConnectionError, TimeoutError, OSError):
            # Transient network blips to Google STT. Treat as no-match.
            return None

        text = (text or "").strip()
        return text or None