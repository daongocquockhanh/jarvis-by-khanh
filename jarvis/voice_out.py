"""Offline text-to-speech via pyttsx3 (uses macOS `say` / NSSpeechSynthesizer)."""

from __future__ import annotations


class SpeechOutput:
    def __init__(self, rate: int = 185, volume: float = 1.0) -> None:
        import pyttsx3  # deferred

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", max(0.0, min(1.0, volume)))

    def speak(self, text: str) -> None:
        if not text:
            return
        self.engine.say(text)
        self.engine.runAndWait()