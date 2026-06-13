# Faster-Whisper Local STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local faster-whisper the default speech-to-text engine for the JARVIS voice layer, with the existing Google Web Speech API as an automatic fallback when faster-whisper is not installed.

**Architecture:** Split mic capture from transcription. `voice_in.py` captures audio and returns WAV bytes; two small transcriber classes (`WhisperTranscriber`, `GoogleTranscriber`) turn WAV bytes into text behind a shared duck-typed `transcribe(wav: bytes) -> str | None` interface. `SpeechInput` selects the backend once at construction from config and falls back to Google if faster-whisper import fails.

**Tech Stack:** Python 3.11+, pydantic-settings (config), SpeechRecognition + PyAudio (capture, existing), faster-whisper / CTranslate2 (new local STT), pytest.

Spec: `docs/superpowers/specs/2026-06-13-faster-whisper-stt-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `config.py` | Add 5 STT settings to `Settings` | Modify |
| `jarvis/stt_google.py` | Google Web Speech transcriber (WAV bytes → text) | Create |
| `jarvis/stt_whisper.py` | faster-whisper transcriber (WAV bytes → text), lazy model load | Create |
| `jarvis/voice_in.py` | Capture only + backend selection + delegate | Modify (rewrite) |
| `pyproject.toml` | Add `faster-whisper` to `[jarvis]` extra | Modify |
| `.env.example` | Document new STT env vars | Modify |
| `CLAUDE.md` | One-line note on first-run model download | Modify |
| `tests/test_stt_google.py` | Google transcriber unit tests (fake `speech_recognition`) | Create |
| `tests/test_stt_whisper.py` | Whisper transcriber unit tests (fake `faster_whisper`) | Create |
| `tests/test_voice_in_backend_select.py` | Backend selection + fallback logic | Create |
| `tests/test_config_stt.py` | Assert new settings + defaults declared | Create |

**Key interface (both transcribers):** `transcribe(self, wav: bytes) -> Optional[str]` — returns stripped transcript, or `None` for no-match / empty / error.

---

### Task 1: Add STT config settings

**Files:**
- Modify: `config.py` (RAG section, after `top_k`)
- Test: `tests/test_config_stt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_stt.py`:

```python
"""STT settings are declared on Settings with the documented defaults."""

from config import Settings


class TestSttSettings:
    def test_stt_fields_declared(self):
        fields = Settings.model_fields
        for name in (
            "stt_backend",
            "whisper_model_size",
            "whisper_device",
            "whisper_compute_type",
            "whisper_language",
        ):
            assert name in fields, f"missing setting: {name}"

    def test_stt_defaults(self):
        fields = Settings.model_fields
        assert fields["stt_backend"].default == "whisper"
        assert fields["whisper_model_size"].default == "base"
        assert fields["whisper_device"].default == "auto"
        assert fields["whisper_compute_type"].default == "auto"
        assert fields["whisper_language"].default == "en"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_stt.py -v`
Expected: FAIL — `assert 'stt_backend' in fields` fails (KeyError / AssertionError), settings not yet declared.

- [ ] **Step 3: Add the settings**

In `config.py`, inside the `# ── RAG ──` block, immediately after the line `top_k: int = 5`, add:

```python
    # ── STT (speech-to-text) ───────────────────────────────────
    # "whisper" = local faster-whisper (default). "google" = Google
    # Web Speech API. Whisper falls back to Google if faster-whisper
    # is not installed.
    stt_backend: str = "whisper"
    whisper_model_size: str = "base"  # tiny|base|small|medium|large-v3
    whisper_device: str = "auto"      # auto|cpu|cuda
    whisper_compute_type: str = "auto"  # auto|int8|float16|float32
    whisper_language: str = "en"      # pin to skip language detection
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_stt.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config_stt.py
git commit -m "feat: add STT backend config settings"
```

---

### Task 2: GoogleTranscriber

**Files:**
- Create: `jarvis/stt_google.py`
- Test: `tests/test_stt_google.py`

The test fakes the `speech_recognition` module via `sys.modules` so it runs without the `[jarvis]` extra installed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stt_google.py`:

```python
"""GoogleTranscriber maps recognizer results/errors to text | None.

Uses a fake speech_recognition module so the test runs without PyAudio /
SpeechRecognition installed.
"""

import sys
import types

import pytest


def _install_fake_sr(monkeypatch):
    sr = types.ModuleType("speech_recognition")

    class UnknownValueError(Exception):
        pass

    class RequestError(Exception):
        pass

    class _Audio:
        pass

    class AudioFile:
        def __init__(self, fileobj):
            self._f = fileobj

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    sr._recognize_return = None
    sr._recognize_raises = None

    class Recognizer:
        def record(self, source):
            return _Audio()

        def recognize_google(self, audio):
            if sr._recognize_raises is not None:
                raise sr._recognize_raises
            return sr._recognize_return

    sr.UnknownValueError = UnknownValueError
    sr.RequestError = RequestError
    sr.AudioFile = AudioFile
    sr.Recognizer = Recognizer
    monkeypatch.setitem(sys.modules, "speech_recognition", sr)
    return sr


class TestGoogleTranscriber:
    def test_returns_text_on_success(self, monkeypatch):
        sr = _install_fake_sr(monkeypatch)
        sr._recognize_return = "what is the weather"
        from jarvis.stt_google import GoogleTranscriber

        assert GoogleTranscriber().transcribe(b"wav") == "what is the weather"

    def test_strips_whitespace(self, monkeypatch):
        sr = _install_fake_sr(monkeypatch)
        sr._recognize_return = "  hello  "
        from jarvis.stt_google import GoogleTranscriber

        assert GoogleTranscriber().transcribe(b"wav") == "hello"

    def test_none_on_unknown_value(self, monkeypatch):
        sr = _install_fake_sr(monkeypatch)
        sr._recognize_raises = sr.UnknownValueError()
        from jarvis.stt_google import GoogleTranscriber

        assert GoogleTranscriber().transcribe(b"wav") is None

    def test_none_on_request_error(self, monkeypatch):
        sr = _install_fake_sr(monkeypatch)
        sr._recognize_raises = sr.RequestError()
        from jarvis.stt_google import GoogleTranscriber

        assert GoogleTranscriber().transcribe(b"wav") is None

    def test_none_on_connection_error(self, monkeypatch):
        sr = _install_fake_sr(monkeypatch)
        sr._recognize_raises = ConnectionResetError()
        from jarvis.stt_google import GoogleTranscriber

        assert GoogleTranscriber().transcribe(b"wav") is None

    def test_none_on_empty_transcript(self, monkeypatch):
        sr = _install_fake_sr(monkeypatch)
        sr._recognize_return = "   "
        from jarvis.stt_google import GoogleTranscriber

        assert GoogleTranscriber().transcribe(b"wav") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stt_google.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jarvis.stt_google'`.

- [ ] **Step 3: Write the implementation**

Create `jarvis/stt_google.py`:

```python
"""Google Web Speech API transcriber (network, free tier).

Reconstructs an AudioData from WAV bytes so it shares the same
`transcribe(wav: bytes) -> str | None` interface as the local whisper
backend. Deferred speech_recognition import keeps the base install light.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GoogleTranscriber:
    def __init__(self) -> None:
        import speech_recognition as sr  # deferred

        self._sr = sr
        self._recognizer = sr.Recognizer()

    def transcribe(self, wav: bytes) -> Optional[str]:
        sr = self._sr
        try:
            with sr.AudioFile(io.BytesIO(wav)) as source:
                audio = self._recognizer.record(source)
            text = self._recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            logger.warning("Google STT request error")
            return None
        except (ConnectionResetError, ConnectionError, TimeoutError, OSError):
            # Transient network blips to Google STT. Treat as no-match.
            return None

        text = (text or "").strip()
        return text or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stt_google.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/stt_google.py tests/test_stt_google.py
git commit -m "feat: add GoogleTranscriber (wav bytes -> text)"
```

---

### Task 3: WhisperTranscriber

**Files:**
- Create: `jarvis/stt_whisper.py`
- Test: `tests/test_stt_whisper.py`

The test fakes the `faster_whisper` module via `sys.modules` so it runs without the real package and never downloads a model.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stt_whisper.py`:

```python
"""WhisperTranscriber: lazy model load, segment join, error -> None.

Fakes faster_whisper so no real model is downloaded.
"""

import sys
import types

import pytest


class _Seg:
    def __init__(self, text):
        self.text = text


def _install_fake_faster_whisper(monkeypatch, *, segments=None, build_raises=None):
    mod = types.ModuleType("faster_whisper")
    state = {"build_count": 0}

    class WhisperModel:
        def __init__(self, model_size, device="auto", compute_type="auto"):
            if build_raises is not None:
                raise build_raises
            state["build_count"] += 1
            self.model_size = model_size

        def transcribe(self, path, language=None):
            info = types.SimpleNamespace(language=language)
            return iter(segments or []), info

    mod.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    return state


class TestWhisperTranscriber:
    def test_joins_segments_to_text(self, monkeypatch):
        _install_fake_faster_whisper(
            monkeypatch, segments=[_Seg(" hello"), _Seg(" world")]
        )
        from jarvis.stt_whisper import WhisperTranscriber

        assert WhisperTranscriber().transcribe(b"wav") == "hello world"

    def test_empty_segments_returns_none(self, monkeypatch):
        _install_fake_faster_whisper(monkeypatch, segments=[])
        from jarvis.stt_whisper import WhisperTranscriber

        assert WhisperTranscriber().transcribe(b"wav") is None

    def test_lazy_load_builds_model_once(self, monkeypatch):
        state = _install_fake_faster_whisper(
            monkeypatch, segments=[_Seg("hi")]
        )
        from jarvis.stt_whisper import WhisperTranscriber

        t = WhisperTranscriber()
        assert state["build_count"] == 0  # not built at construction
        t.transcribe(b"wav")
        t.transcribe(b"wav")
        assert state["build_count"] == 1  # built once, reused

    def test_model_load_failure_returns_none(self, monkeypatch):
        _install_fake_faster_whisper(
            monkeypatch, build_raises=RuntimeError("download failed")
        )
        from jarvis.stt_whisper import WhisperTranscriber

        # Construction succeeds (import works); load happens at first call.
        assert WhisperTranscriber().transcribe(b"wav") is None

    def test_missing_package_raises_importerror_at_construction(self, monkeypatch):
        # Simulate faster_whisper not installed.
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        from jarvis.stt_whisper import WhisperTranscriber

        with pytest.raises(ImportError):
            WhisperTranscriber()
```

Note on the last test: setting `sys.modules["faster_whisper"] = None` makes `import faster_whisper` raise `ImportError` (Python treats a `None` entry as "known missing").

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stt_whisper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jarvis.stt_whisper'`.

- [ ] **Step 3: Write the implementation**

Create `jarvis/stt_whisper.py`:

```python
"""Local faster-whisper transcriber (CTranslate2, offline after first download).

The faster_whisper import happens in __init__ so a missing package raises
ImportError at construction — letting SpeechInput fall back to Google. The
model itself is loaded lazily on the first transcribe() call (first run
downloads ~140MB for the `base` model and caches it under
~/.cache/huggingface).
"""

from __future__ import annotations

import logging
import tempfile
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


class WhisperTranscriber:
    def __init__(self) -> None:
        from faster_whisper import WhisperModel  # ImportError -> Google fallback

        self._WhisperModel = WhisperModel
        self._model = None  # lazy: built on first transcribe()

    def _ensure_model(self):
        if self._model is None:
            logger.info(
                "Loading whisper model %r (device=%s, compute=%s); "
                "first run downloads the model (~140MB for 'base')",
                _settings.whisper_model_size,
                _settings.whisper_device,
                _settings.whisper_compute_type,
            )
            self._model = self._WhisperModel(
                _settings.whisper_model_size,
                device=_settings.whisper_device,
                compute_type=_settings.whisper_compute_type,
            )
        return self._model

    def transcribe(self, wav: bytes) -> Optional[str]:
        try:
            model = self._ensure_model()
        except Exception:
            logger.exception("whisper model load failed")
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                tmp.write(wav)
                tmp.flush()
                segments, _info = model.transcribe(
                    tmp.name, language=_settings.whisper_language
                )
                text = "".join(seg.text for seg in segments).strip()
        except Exception:
            logger.exception("whisper transcription failed")
            return None

        return text or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stt_whisper.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/stt_whisper.py tests/test_stt_whisper.py
git commit -m "feat: add WhisperTranscriber with lazy model load"
```

---

### Task 4: Refactor SpeechInput — capture + backend selection

**Files:**
- Modify: `jarvis/voice_in.py` (full rewrite)
- Test: `tests/test_voice_in_backend_select.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_voice_in_backend_select.py`:

```python
"""SpeechInput backend selection + Google fallback on whisper ImportError.

Tests the _make_transcriber() selection logic only — no mic, no real deps.
Importing jarvis.voice_in is safe: speech_recognition is imported lazily
inside SpeechInput.__init__, not at module load.
"""

import jarvis.stt_google as sg
import jarvis.stt_whisper as sw
import jarvis.voice_in as vi


class TestBackendSelection:
    def test_selects_whisper_when_available(self, monkeypatch):
        monkeypatch.setattr(vi._settings, "stt_backend", "whisper")
        monkeypatch.setattr(sw, "WhisperTranscriber", lambda: "WHISPER")
        monkeypatch.setattr(sg, "GoogleTranscriber", lambda: "GOOGLE")
        assert vi._make_transcriber() == "WHISPER"

    def test_falls_back_to_google_on_import_error(self, monkeypatch):
        monkeypatch.setattr(vi._settings, "stt_backend", "whisper")

        def boom():
            raise ImportError("faster_whisper missing")

        monkeypatch.setattr(sw, "WhisperTranscriber", boom)
        monkeypatch.setattr(sg, "GoogleTranscriber", lambda: "GOOGLE")
        assert vi._make_transcriber() == "GOOGLE"

    def test_selects_google_when_configured(self, monkeypatch):
        monkeypatch.setattr(vi._settings, "stt_backend", "google")
        monkeypatch.setattr(sg, "GoogleTranscriber", lambda: "GOOGLE")
        assert vi._make_transcriber() == "GOOGLE"

    def test_unknown_backend_raises(self, monkeypatch):
        monkeypatch.setattr(vi._settings, "stt_backend", "bogus")
        try:
            vi._make_transcriber()
        except ValueError as e:
            assert "bogus" in str(e)
        else:
            raise AssertionError("expected ValueError for unknown backend")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_in_backend_select.py -v`
Expected: FAIL — `AttributeError: module 'jarvis.voice_in' has no attribute '_make_transcriber'` (and no `_settings`).

- [ ] **Step 3: Rewrite voice_in.py**

Replace the entire contents of `jarvis/voice_in.py` with:

```python
"""Mic capture + pluggable transcription.

Capture (PyAudio via SpeechRecognition) is isolated from transcription so
the STT backend can be swapped. Default backend is local faster-whisper;
the Google Web Speech API is the fallback when faster-whisper is not
installed. The chosen backend is fixed at construction.
"""

from __future__ import annotations

import logging
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


def _make_transcriber():
    """Build the configured transcriber, falling back to Google if whisper
    is unavailable. Returns an object with `transcribe(wav: bytes) -> str | None`."""
    backend = _settings.stt_backend.lower()
    if backend == "whisper":
        try:
            from jarvis.stt_whisper import WhisperTranscriber

            return WhisperTranscriber()
        except ImportError:
            logger.warning(
                "faster-whisper not installed; falling back to Google STT. "
                "Install with: pip install '.[jarvis]'"
            )
            from jarvis.stt_google import GoogleTranscriber

            return GoogleTranscriber()
    if backend == "google":
        from jarvis.stt_google import GoogleTranscriber

        return GoogleTranscriber()
    raise ValueError(f"Unknown STT_BACKEND: {_settings.stt_backend!r}")


class SpeechInput:
    def __init__(self, energy_threshold: int = 300, pause_threshold: float = 0.8) -> None:
        import speech_recognition as sr  # deferred

        self._sr = sr
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = energy_threshold
        self.recognizer.pause_threshold = pause_threshold
        self.recognizer.dynamic_energy_threshold = True
        self._transcriber = _make_transcriber()

    def listen_once(self, timeout: float = 5.0, phrase_time_limit: float = 10.0) -> Optional[str]:
        """Capture one utterance from the default mic and return transcript or None."""
        sr = self._sr
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
            try:
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )
            except sr.WaitTimeoutError:
                return None

        wav = audio.get_wav_data()
        return self._transcriber.transcribe(wav)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_in_backend_select.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `pytest -q`
Expected: PASS — all prior tests (safety, wake, ingest, decomposer, models) plus the 4 new test files green.

- [ ] **Step 6: Commit**

```bash
git add jarvis/voice_in.py tests/test_voice_in_backend_select.py
git commit -m "refactor: split SpeechInput into capture + pluggable transcriber"
```

---

### Task 5: Dependencies and docs

**Files:**
- Modify: `pyproject.toml` (`[jarvis]` extra)
- Modify: `.env.example`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add faster-whisper to the jarvis extra**

In `pyproject.toml`, change the `jarvis` optional-dependencies block from:

```toml
jarvis = [
    "SpeechRecognition>=3.10.0",
    "PyAudio>=0.2.14",
    "pyttsx3>=2.90",
]
```

to:

```toml
jarvis = [
    "SpeechRecognition>=3.10.0",
    "PyAudio>=0.2.14",
    "pyttsx3>=2.90",
    "faster-whisper>=1.0.0",
]
```

- [ ] **Step 2: Document the new env vars**

In `.env.example`, after the `# RAG` block (after the `TOP_K=5` line), add:

```bash

# STT (speech-to-text)
# whisper = local faster-whisper (default, offline after first download).
# google  = Google Web Speech API (network). Whisper auto-falls-back to
# google if faster-whisper is not installed.
STT_BACKEND=whisper
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
WHISPER_LANGUAGE=en
```

- [ ] **Step 3: Note the first-run download in CLAUDE.md**

In `CLAUDE.md`, under the `## Architecture notes` section, add this bullet after the "Backend: claude-cli subprocess" line:

```markdown
- STT: local faster-whisper by default (`jarvis/stt_whisper.py`), Google Web Speech fallback (`jarvis/stt_google.py`). First `./run.sh voice` downloads the `base` model (~140MB) to `~/.cache/huggingface`; offline after that. Capture lives in `jarvis/voice_in.py`; transcription is swappable via `STT_BACKEND`.
```

- [ ] **Step 4: Verify the project still imports and installs cleanly**

Run: `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject ok')"`
Expected: `pyproject ok`

Run: `pytest -q`
Expected: PASS — unchanged from Task 4 (docs/deps changes don't affect tests).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example CLAUDE.md
git commit -m "docs: document STT backend config and first-run model download"
```

---

### Task 6: Manual smoke test (verification, not code)

This task verifies the real audio path that unit tests mock. Requires a mic and network for the first model download. Not run in CI.

- [ ] **Step 1: Install the voice extra into the venv**

Run: `./setup.sh` (if `.venv` missing), then `pip install '.[jarvis]'`
Expected: faster-whisper and its CTranslate2 dependency install without error.

- [ ] **Step 2: Confirm whisper is the active backend and model downloads**

Run: `./run.sh voice`
Expected: On first launch, the log shows `Loading whisper model 'base' ...` and a one-time model download. JARVIS greets with "Hello, I am JARVIS."

- [ ] **Step 3: Speak a wake-word command**

Say: "Jarvis, what time is it?"
Expected: Terminal prints `heard: ...` with an accurate transcript produced by whisper (no network call to Google), then JARVIS answers.

- [ ] **Step 4: Confirm the fallback path (optional)**

In a scratch venv without faster-whisper, run `./run.sh voice`.
Expected: Log shows the warning `faster-whisper not installed; falling back to Google STT`, and voice still works over the network.

- [ ] **Step 5: No commit** — this task only verifies behavior.

---

## Self-Review

**Spec coverage:**
- Whisper default + Google fallback → Task 4 (`_make_transcriber` ImportError branch), Task 1 (config default).
- `base` model default → Task 1.
- Parent-process drop-in → Task 4 (transcription stays in `voice_in.py` call path; no brain protocol change).
- Split backends (Approach B) → Tasks 2, 3, 4.
- 5 config vars + `auto` compute type → Task 1.
- `faster-whisper` in `[jarvis]` extra → Task 5.
- First-run model download docs → Task 5.
- No fallback on load failure (return None) → Task 3 (`_ensure_model` wrapped, returns None) + test `test_model_load_failure_returns_none`.
- Construction-time ImportError fallback → Task 4 test `test_falls_back_to_google_on_import_error`.
- Call-time empty/whitespace → None → Tasks 2 & 3 (`test_none_on_empty_transcript`, `test_empty_segments_returns_none`).
- Capture errors unchanged → Task 4 (WaitTimeoutError handling preserved verbatim).
- 3 mocked test files + manual smoke → Tasks 2, 3, 4 tests + Task 6.
- `assistant.py` / `brain.py` untouched → confirmed: no task modifies them; `SpeechInput` API (`listen_once` signature) preserved.

**Placeholder scan:** No TBD/TODO/"handle edge cases". Every code step shows full code; every run step shows expected output.

**Type consistency:** `transcribe(self, wav: bytes) -> Optional[str]` identical in `stt_google.py` and `stt_whisper.py`. `_make_transcriber()` returns objects exposing that method. `_settings.stt_backend` / `whisper_*` names match config field names in Task 1. Fake-module test helpers match the real APIs used (`Recognizer.record/recognize_google`, `AudioFile` context manager; `WhisperModel(...).transcribe(path, language=...)` → `(segments, info)`).

**Out of scope (per spec):** Kokoro TTS, streaming, extra STT backends, wake-word engine — none added.