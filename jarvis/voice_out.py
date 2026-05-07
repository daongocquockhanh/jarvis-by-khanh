"""Offline text-to-speech.

On macOS we shell out to the built-in `say` command. This avoids a known
pyttsx3 issue where `runAndWait()` deadlocks on the second call inside a
long-running loop. `say` is fully offline, ships with macOS, and handles
repeat invocations reliably.
"""

from __future__ import annotations

import platform
import subprocess


class SpeechOutput:
    def __init__(self, rate: int = 185, voice: str | None = None) -> None:
        self.rate = rate
        self.voice = voice
        self._is_mac = platform.system() == "Darwin"
        self._pyttsx_engine = None
        if not self._is_mac:
            import pyttsx3  # deferred

            self._pyttsx_engine = pyttsx3.init()
            self._pyttsx_engine.setProperty("rate", rate)

    def speak(self, text: str) -> None:
        if not text:
            return

        if self._is_mac:
            cmd = ["say", "-r", str(self.rate)]
            if self.voice:
                cmd += ["-v", self.voice]
            cmd += ["--", text]
            subprocess.run(cmd, check=False, shell=False)
        else:
            self._pyttsx_engine.say(text)
            self._pyttsx_engine.runAndWait()