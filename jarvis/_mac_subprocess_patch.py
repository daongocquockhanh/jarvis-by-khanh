"""Mac-safe subprocess patch.

Background:
- Homebrew Python 3.12 ships without `_posixsubprocess.HAVE_POSIX_SPAWN_CLOSEFROM`.
- Python's subprocess refuses to use `posix_spawn` when `close_fds=True` (the
  default) and that symbol is missing, so it falls back to `fork + exec`.
- On macOS, forking a multi-threaded Python (PyAudio holds threads) crashes in
  the Network.framework atfork handlers. `posix_spawn` does not run atfork
  handlers, so switching paths avoids the crash.

This module flips the default for every `subprocess.Popen` invocation to
`close_fds=False`. Callers that explicitly pass `close_fds=True` still get it.

Caller code does not leak credentials to child processes here — we only invoke
our own trusted binaries (`claude`, `say`, the bundled `flac`) and no secret
FDs stay open in the parent.
"""

from __future__ import annotations

import subprocess

_original_init = subprocess.Popen.__init__
_PATCHED = False


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    def _patched_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("close_fds", False)
        return _original_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_init  # type: ignore[method-assign]
    _PATCHED = True