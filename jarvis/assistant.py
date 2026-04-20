"""Main JARVIS loop: wake -> listen -> agent.ask() -> speak."""

from __future__ import annotations

import logging

from agent import ask
from jarvis.safety import UnsafeInputError, sanitize
from jarvis.wake import WakeWordDetector

logger = logging.getLogger(__name__)

GREETING = "Hello, I am JARVIS."
NO_MATCH = "Sorry, I did not catch that."
UNSAFE_REPLY = "I can't process that request."
ERROR_REPLY = "Something went wrong. Please try again."


def run_assistant(wake_words: tuple[str, ...] = ("jarvis",)) -> None:
    """Blocking loop. Ctrl+C to exit."""
    try:
        from jarvis.voice_in import SpeechInput
        from jarvis.voice_out import SpeechOutput
    except ImportError as e:
        raise SystemExit(
            "Voice dependencies missing. Install with: pip install '.[jarvis]'"
        ) from e

    stt = SpeechInput()
    tts = SpeechOutput()
    wake = WakeWordDetector(wake_words)

    tts.speak(GREETING)
    print(f"JARVIS ready. Say '{wake_words[0]}' followed by your question.")

    while True:
        try:
            transcript = stt.listen_once()
        except KeyboardInterrupt:
            print("\nShutting down.")
            return
        except Exception:
            logger.exception("listen error")
            continue

        if not transcript:
            continue

        print(f"heard: {transcript}")

        if not wake.triggered(transcript):
            continue

        query = wake.strip_wake(transcript)
        if not query:
            tts.speak("Yes?")
            try:
                query = stt.listen_once(timeout=6.0)
            except Exception:
                logger.exception("listen error (post-wake)")
                continue

        if not query:
            tts.speak(NO_MATCH)
            continue

        try:
            safe_query = sanitize(query)
        except UnsafeInputError as e:
            logger.warning("unsafe input rejected: %s", e)
            tts.speak(UNSAFE_REPLY)
            continue

        try:
            answer = ask(safe_query)
        except Exception:
            logger.exception("agent.ask failed")
            tts.speak(ERROR_REPLY)
            continue

        print(f"jarvis: {answer}")
        tts.speak(answer)
