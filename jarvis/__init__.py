"""JARVIS-style voice assistant layer for agentic-bot.

Thin adapter: wake word -> STT -> agentic-bot agent.ask() -> TTS.
All heavy/unsafe JARVIS features (shell exec, nmap, yara, filesystem
automation, browser control) are intentionally excluded.
"""

__all__ = ["run_assistant"]


def run_assistant(*args, **kwargs):
    from jarvis.assistant import run_assistant as _run

    return _run(*args, **kwargs)