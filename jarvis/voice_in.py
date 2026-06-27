"""Mic capture + pluggable transcription.

Capture (PyAudio via SpeechRecognition) is isolated from transcription so
the STT backend can be swapped. Default backend is local faster-whisper;
the Google Web Speech API is the fallback when faster-whisper is not
installed. The chosen backend is fixed at construction.
"""

from __future__ import annotations

import logging
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


def _make_transcriber():
    """Build the configured transcriber, falling back to Google if whisper
    is unavailable. Returns an object with `transcribe(wav: bytes) -> str | None`."""
    backend = _settings.stt_backend.lower()
    if backend == "whisper":
        try:
            from jarvis.stt_whisper import WhisperTranscriber

            return WhisperTranscriber()
        except ImportError:
            logger.warning(
                "faster-whisper not installed; falling back to Google STT. "
                "Install with: pip install '.[jarvis]'"
            )
            from jarvis.stt_google import GoogleTranscriber

            return GoogleTranscriber()
    if backend == "google":
        from jarvis.stt_google import GoogleTranscriber

        return GoogleTranscriber()
    raise ValueError(f"Unknown STT_BACKEND: {_settings.stt_backend!r}")


class SpeechInput:
    def __init__(self, energy_threshold: int = 300, pause_threshold: float = 0.8) -> None:
        import speech_recognition as sr  # deferred

        self._sr = sr
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = energy_threshold
        self.recognizer.pause_threshold = pause_threshold
        self.recognizer.dynamic_energy_threshold = True
        self._transcriber = _make_transcriber()

    def listen_once(self, timeout: float = 5.0, phrase_time_limit: float = 10.0) -> Optional[str]:
        """Capture one utterance from the default mic and return transcript or None."""
        sr = self._sr
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
            try:
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )
            except sr.WaitTimeoutError:
                return None

        wav = audio.get_wav_data()
        return self._transcriber.transcribe(wav)