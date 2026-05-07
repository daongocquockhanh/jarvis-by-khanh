"""Long-lived worker that handles retrieval + LLM + TTS.

The voice loop spawns this as a subprocess at startup. It isolates
PyAudio (in the parent) from ChromaDB / claude-cli / torch / `say`
(in the child). Without this isolation, spawning other audio-using
subprocesses from inside a PyAudio-holding Python on macOS can crash
the interpreter or silently block audio output.

Protocol (line-based JSON over stdin/stdout):
  request   {"op": "ask", "q": "..."}
  response  {"ok": true, "answer": "..."} | {"ok": false, "error": "..."}

  request   {"op": "speak", "text": "..."}
  response  {"ok": true}
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import traceback

# Apply before any other import that might spawn subprocesses.
from jarvis._mac_subprocess_patch import apply as _apply_mac_patch

_apply_mac_patch()

_IS_MAC = platform.system() == "Darwin"
# Resolve to absolute paths so subprocess uses posix_spawn, not fork+exec.
# Fork+exec from a multi-threaded Python crashes in Network.framework on mac.
_SAY_BIN = shutil.which("say") or "/usr/bin/say"


def _say(text: str, rate: int = 185, voice: str | None = None) -> None:
    if not text:
        return
    if _IS_MAC:
        cmd = [_SAY_BIN, "-r", str(rate)]
        if voice:
            cmd += ["-v", voice]
        cmd += ["--", text]
        subprocess.run(cmd, check=False, shell=False)
    else:
        # Fallback path (non-mac). Kept minimal.
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass


def main() -> None:
    from agent import ask  # heavy imports deferred

    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = req.get("op", "ask")

            if op == "ask":
                answer = ask(req["q"])
                sys.stdout.write(json.dumps({"ok": True, "answer": answer}) + "\n")
            elif op == "speak":
                _say(req["text"], rate=req.get("rate", 185), voice=req.get("voice"))
                sys.stdout.write(json.dumps({"ok": True}) + "\n")
            else:
                sys.stdout.write(json.dumps({"ok": False, "error": f"unknown op: {op}"}) + "\n")
        except Exception as e:  # noqa: BLE001
            sys.stdout.write(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"{type(e).__name__}: {e}",
                        "tb": traceback.format_exc()[-1000:],
                    }
                )
                + "\n"
            )
        sys.stdout.flush()


if __name__ == "__main__":
    main()