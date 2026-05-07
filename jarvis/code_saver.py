"""Extract fenced code blocks from answer, save to sandbox dirs.

Voice path is read-only (no Write/Edit/Bash tools). This module gives
Jarvis a safe way to "save code" without handing it shell access:
parse the LLM's own answer text for ```lang ... ``` blocks and write
them to a sandbox directory under the repo.

Two save modes:
1. Block starts with `# file: <relpath>` → write to business_ideas/<relpath>
   (sandboxed scaffolding for business-idea projects in ideas.md).
2. No directive → write to jarvis_output/<timestamp>_<N>.<ext>.

Security:
- Both target dirs are fixed, not user-controllable.
- `# file:` relpath is sanitized: no absolute, no `..`, must resolve
  under business_ideas/. Path traversal rejected.
- Never overwrites files outside the two sandbox dirs.
- No shell invocation, no symlink following at write time.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _REPO_ROOT / "jarvis_output"
_IDEAS_DIR = _REPO_ROOT / "business_ideas"

_FILE_DIRECTIVE_RE = re.compile(r"^\s*(?://|#)\s*file:\s*(.+?)\s*$", re.IGNORECASE)

_FENCE_RE = re.compile(r"```([a-zA-Z0-9_+\-]*)\s*\n(.*?)```", re.DOTALL)

_LANG_EXT = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "bash": "sh",
    "sh": "sh",
    "zsh": "sh",
    "go": "go",
    "rust": "rs",
    "rs": "rs",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "html": "html",
    "css": "css",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "sql": "sql",
    "md": "md",
    "markdown": "md",
}


def _safe_ideas_path(relpath: str) -> Path | None:
    """Resolve relpath under business_ideas/. Reject traversal or absolute.

    Rules:
    - Must be relative, no leading slash or drive letter.
    - No `..` segments.
    - Final resolved path must stay under business_ideas/.
    - Must contain at least one directory (enforces per-idea grouping).
    """
    if not relpath:
        return None
    relpath = relpath.strip().lstrip("/\\")
    if ".." in Path(relpath).parts or Path(relpath).is_absolute():
        return None
    candidate = (_IDEAS_DIR / relpath).resolve()
    try:
        candidate.relative_to(_IDEAS_DIR.resolve())
    except ValueError:
        return None
    if candidate.parent == _IDEAS_DIR.resolve():
        # Must be grouped into a subfolder, not written at base.
        return None
    return candidate


def _parse_directive(code: str) -> tuple[str | None, str]:
    """If first line is `# file: <relpath>`, return (relpath, body_without_directive)."""
    lines = code.split("\n", 1)
    if not lines:
        return None, code
    m = _FILE_DIRECTIVE_RE.match(lines[0])
    if not m:
        return None, code
    relpath = m.group(1).strip()
    body = lines[1] if len(lines) > 1 else ""
    return relpath, body


def extract_and_save(answer: str) -> list[Path]:
    """Find code blocks in `answer`, write each to sandbox dir.

    Returns list of saved paths (empty if no fenced blocks).
    """
    if not answer:
        return []

    matches = _FENCE_RE.findall(answer)
    if not matches:
        return []

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved: list[Path] = []

    for idx, (lang, code) in enumerate(matches, 1):
        relpath, body = _parse_directive(code)

        target: Path | None = None
        if relpath:
            target = _safe_ideas_path(relpath)
            if target is None:
                logger.warning("code_saver: rejected unsafe path %r", relpath)

        if target is None:
            ext = _LANG_EXT.get(lang.lower().strip(), "txt")
            _OUTPUT_DIR.mkdir(exist_ok=True)
            target = _OUTPUT_DIR / f"{ts}_{idx}.{ext}"
            write_body = code
        else:
            write_body = body

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(write_body.strip() + "\n", encoding="utf-8")
            saved.append(target)
        except Exception:
            logger.exception("code_saver: write failed for %s", target)

    return saved
