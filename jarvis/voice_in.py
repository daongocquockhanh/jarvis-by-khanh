"""Speech-to-text using SpeechRecognition + Google Web Speech API (free tier).

Deferred import so the base agentic-bot install does not require PyAudio.
"""

from __future__ import annotations

from typing import Optional


class SpeechInput:
    def __init__(self, energy_threshold: int = 300, pause_threshold: float = 0.8) -> None:
        import speech_recognition as sr  # deferred

        self._sr = sr
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = energy_threshold
        self.recognizer.pause_threshold = pause_threshold
        self.recognizer.dynamic_energy_threshold = True

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

        try:
            return self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            return None
        except (ConnectionResetError, ConnectionError, TimeoutError, OSError):
            # Transient network blips to Google STT. Treat as no-match.
            return None