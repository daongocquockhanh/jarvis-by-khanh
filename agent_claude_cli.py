"""Claude Code CLI backend.

Shells out to the `claude` CLI with `-p` (print mode). Uses the user's
Claude Code subscription auth — no API key, no per-call billing.

Security notes:
- `shell=False` (args list). No shell-metachar injection.
- Question text passed as a single positional arg.
- Hard timeout prevents runaway subprocesses.
- Input already sanitized upstream in jarvis/safety.py.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from config import get_settings
from jarvis.memory import recall, remember
from retriever import retrieve

_REPO_ROOT = Path(__file__).resolve().parent
_IDEAS_FILE = _REPO_ROOT / "business idea" / "ideas.md"


def _load_ideas() -> str:
    try:
        return _IDEAS_FILE.read_text(encoding="utf-8")
    except Exception:
        return ""

logger = logging.getLogger(__name__)

_settings = get_settings()

SYSTEM_PROMPT = (
    "You are JARVIS, a witty, concise AI assistant modeled after Tony Stark's JARVIS. "
    "Prefer the provided context documents when the question relates to them, and cite "
    "the source. For general questions outside the context, answer from your own "
    "knowledge. Keep spoken replies short (no markdown, no bullet lists).\n\n"
    "When the user asks you to scaffold, build, or write code for one of the business "
    "ideas in the 'Business ideas' section below, produce the code in fenced code "
    "blocks. The FIRST line of each code block MUST be a file directive of this exact "
    "form:\n"
    "  # file: <idea_slug>/<relative/path.ext>\n"
    "Example:\n"
    "  ```python\n"
    "  # file: life_manager/app.py\n"
    "  from fastapi import FastAPI\n"
    "  ...\n"
    "  ```\n"
    "Rules for the file directive:\n"
    "- Always include the directive when generating code for an idea. Files save to "
    "business_ideas/<idea_slug>/... in the repo.\n"
    "- Use a short snake_case idea_slug derived from the idea name (e.g. 'life_manager', "
    "'burnout_recovery'). Reuse the same slug for all files of one idea.\n"
    "- Relative paths only. No '..', no leading slash.\n"
    "- Never write to paths outside business_ideas/. Never target existing repo files.\n"
    "After the code, give a one-sentence spoken summary of what was built."
)


def _build_prompt(question: str, chunks: list[dict], memories: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk["metadata"].get("source", "doc")
        parts.append(f"[Source {i}: {source}]\n{chunk['text']}")
    context = "\n\n".join(parts) if parts else "No relevant documents found."

    if memories:
        mem_parts = [f"- {m['text']}" for m in memories]
        memory_block = "\n".join(mem_parts)
    else:
        memory_block = "None."

    ideas = _load_ideas()
    ideas_block = ideas if ideas else "(none on file)"

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Business ideas (from business idea/ideas.md):\n{ideas_block}\n\n"
        f"Prior memory (your past conversations / learned facts):\n{memory_block}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )


def _resolve_cli(path: str) -> str:
    """Return absolute path to the claude CLI.

    subprocess on macOS only uses posix_spawn when argv[0] has a directory
    component. Passing a bare name triggers fork+exec, which crashes in
    Network.framework atfork handlers when the parent is multi-threaded.
    """
    resolved = shutil.which(path)
    if not resolved:
        raise RuntimeError(
            f"`{path}` not found on PATH. Install Claude Code first: "
            "https://docs.anthropic.com/claude/docs/claude-code"
        )
    return resolved


def ask(question: str) -> str:
    cli = _resolve_cli(_settings.claude_cli_path)

    chunks = retrieve(question)
    memories = recall(question)
    prompt = _build_prompt(question, chunks, memories)

    # Pipe prompt via stdin to avoid argv length limits.
    cmd = [
        cli,
        "-p",
        "--output-format",
        "text",
        "--allowedTools",
        "WebSearch,WebFetch",
    ]

    # Retry once on SIGSEGV (exit -11) — occasionally seen when spawning
    # from inside a PyAudio-held mic context on macOS.
    attempts = 0
    while True:
        attempts += 1
        try:
            # IMPORTANT: do NOT pass start_new_session=True here.
            # Python 3.12 disables posix_spawn when that flag is set, forcing
            # the fork+exec path. On macOS, fork+exec from a multi-threaded
            # process crashes in Network.framework atfork handlers. With an
            # absolute-path executable and default flags, subprocess uses
            # posix_spawn which is safe.
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=_settings.claude_cli_timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return "Request timed out. Please try again."

        if result.returncode != -11 or attempts >= 2:
            break
        logger.warning("claude CLI SIGSEGV on attempt %d; retrying", attempts)

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        dump = Path(tempfile.gettempdir()) / "jarvis_last_failed_prompt.txt"
        try:
            dump.write_text(prompt, encoding="utf-8")
        except Exception:
            pass
        logger.error(
            "claude CLI failed: exit=%s stderr=%r stdout=%r prompt_dump=%s",
            result.returncode,
            stderr[:500],
            stdout[:200],
            dump,
        )
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}). "
            f"stderr: {stderr[:200] or '<empty>'} | prompt dumped to {dump}"
        )

    answer = (result.stdout or "").strip()
    if answer:
        remember(question, answer)
    return answer