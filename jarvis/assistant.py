"""Main JARVIS loop: wake -> listen -> agent.ask() -> speak."""

from __future__ import annotations

import logging
import time

from jarvis.brain_client import BrainClient
from jarvis.code_saver import extract_and_save
from jarvis.safety import UnsafeInputError, sanitize
from jarvis.wake import WakeWordDetector

OPEN_WINDOW_SECONDS = 30.0

logger = logging.getLogger(__name__)

GREETING = "Hello, I am JARVIS."
NO_MATCH = "Sorry, I did not catch that."
UNSAFE_REPLY = "I can't process that request."
ERROR_REPLY = "Something went wrong. Please try again."


def run_assistant(
    wake_words: tuple[str, ...] = (
        "jarvis",
        "jarvus",
        "jervis",
        "jarvi",
        "service",
        "jarvice",
        "harvest",
        "garvis",
    ),
) -> None:
    """Blocking loop. Ctrl+C to exit."""
    try:
        from jarvis.voice_in import SpeechInput
    except ImportError as e:
        raise SystemExit(
            "Voice dependencies missing. Install with: pip install '.[jarvis]'"
        ) from e

    # Start the brain worker BEFORE opening the mic. It runs in its own
    # Python process so ChromaDB / claude-cli / torch / `say` never share
    # state with PyAudio — which otherwise crashes the interpreter or
    # silently blocks audio output on macOS.
    brain = BrainClient()
    brain.start()

    stt = SpeechInput()
    wake = WakeWordDetector(wake_words)

    brain.speak(GREETING)
    print(f"JARVIS ready. Say '{wake_words[0]}' followed by your question.")

    try:
        _loop(brain, stt, wake)
    finally:
        brain.close()


def _loop(brain, stt, wake) -> None:
    open_until = 0.0
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

        now = time.monotonic()
        in_open_window = now < open_until

        if wake.triggered(transcript):
            query = wake.strip_wake(transcript)
            if not query:
                brain.speak("Yes?")
                try:
                    query = stt.listen_once(timeout=6.0)
                except Exception:
                    logger.exception("listen error (post-wake)")
                    continue
        elif in_open_window:
            query = transcript
        else:
            continue

        if not query:
            brain.speak(NO_MATCH)
            continue

        try:
            safe_query = sanitize(query)
        except UnsafeInputError as e:
            logger.warning("unsafe input rejected: %s", e)
            brain.speak(UNSAFE_REPLY)
            continue

        try:
            answer = brain.ask(safe_query)
        except Exception:
            logger.exception("brain.ask failed")
            brain.speak(ERROR_REPLY)
            continue

        print(f"jarvis: {answer}")

        saved = extract_and_save(answer)
        if saved:
            names = ", ".join(p.name for p in saved)
            print(f"saved code: {names}")
            spoken = answer + f" Saved {len(saved)} file{'s' if len(saved) > 1 else ''} to jarvis output."
        else:
            spoken = answer

        brain.speak(spoken)
        open_until = time.monotonic() + OPEN_WINDOW_SECONDS
