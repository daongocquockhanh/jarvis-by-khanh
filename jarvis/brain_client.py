"""Client that manages the brain subprocess and forwards queries."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Optional


class BrainClient:
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return

        env = os.environ.copy()
        # Parent may have loaded PyAudio; child should start clean.
        env.setdefault("PYTHONUNBUFFERED", "1")

        # No start_new_session — it disables posix_spawn on py3.12 and
        # would crash mac Network.framework on multi-threaded fork.
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "jarvis.brain"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
            env=env,
        )

        # Wait for the ready handshake.
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("brain subprocess failed to start")
        try:
            ready = json.loads(line)
            if not ready.get("ready"):
                raise RuntimeError(f"brain unexpected startup line: {line!r}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"brain bad startup line: {line!r}") from e

    def _call(self, req: dict) -> dict:
        if not self.proc or self.proc.poll() is not None:
            self.start()
        assert self.proc is not None
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()

        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("brain closed the pipe")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "unknown brain error"))
        return resp

    def ask(self, question: str) -> str:
        return self._call({"op": "ask", "q": question})["answer"]

    def speak(self, text: str, rate: int = 185, voice: Optional[str] = None) -> None:
        if not text:
            return
        payload: dict = {"op": "speak", "text": text, "rate": rate}
        if voice:
            payload["voice"] = voice
        self._call(payload)

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()  # type: ignore[union-attr]
            except Exception:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()