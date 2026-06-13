# Faster-Whisper Local STT — Design

**Date:** 2026-06-13
**Status:** Approved (design), pending implementation plan
**Scope:** Add local speech-to-text (faster-whisper) to the JARVIS voice layer,
defaulting to whisper with the existing Google Web Speech API as fallback.

## Goal

Replace the network-dependent Google Web Speech API as the default STT engine
with local faster-whisper transcription. Keep Google as an automatic fallback so
voice mode still works if faster-whisper is not installed. Offline-first: after a
one-time model download, transcription needs no network.

## Decisions (locked during brainstorming)

1. **Policy:** whisper default, Google fallback (not full replace, not manual-only switch).
2. **Model:** `base` default (~140MB), balanced latency/accuracy for short voice commands.
3. **Location:** transcription runs in the parent (mic) process as a drop-in.
   The brain subprocess isolation exists because ChromaDB / claude-cli / macOS
   `say` spawn audio subprocesses that crash PyAudio. faster-whisper (CTranslate2)
   is pure in-process compute and spawns nothing, so that crash reason does not
   apply to it.
4. **Code structure:** split backends with shared capture (Approach B), no registry.
5. **Load-failure behavior:** if the whisper model fails to load at first call,
   return `None` (no-match) — do NOT fall back to Google. Backend is fixed at
   construction time.

## Architecture

Capture stays isolated from transcription. `voice_in.py` captures mic audio and
returns WAV bytes; two small transcriber modules turn WAV bytes into text.

```
jarvis/
  voice_in.py      SpeechInput — capture only. sr.Microphone + VAD / energy
                   threshold (unchanged). Picks a transcriber at construction,
                   holds it, delegates. listen_once() returns text | None.
  stt_whisper.py   WhisperTranscriber.transcribe(wav: bytes) -> str | None
                   Lazy-loads faster_whisper.WhisperModel on first call.
  stt_google.py    GoogleTranscriber.transcribe(wav: bytes) -> str | None
                   recognize_google logic, moved out of voice_in.
```

### Transcriber interface

Duck-typed, two implementations, no shared base class:

```python
def transcribe(self, wav: bytes) -> str | None: ...
```

Returns stripped transcript text, or `None` for no-match / empty / error.

### Backend selection (SpeechInput.__init__)

- `stt_backend == "whisper"`: try to construct `WhisperTranscriber`. On
  `ImportError` (faster-whisper not installed), log a WARNING and use
  `GoogleTranscriber` instead.
- `stt_backend == "google"`: use `GoogleTranscriber` directly.

Selection happens once, at construction. The chosen transcriber is fixed for the
session.

### listen_once()

Signature and capture behavior unchanged: `sr.Microphone`, `adjust_for_ambient_noise`,
`listen(timeout, phrase_time_limit)`, `WaitTimeoutError` handling. After capture:

```python
wav = audio.get_wav_data()
return self._transcriber.transcribe(wav)
```

`assistant.py` and `brain.py` are untouched — the `SpeechInput` API is stable.

## Data flow

```
mic → sr.Microphone capture → AudioData → get_wav_data() → wav bytes
    → transcriber.transcribe(wav) → text | None → assistant loop (unchanged)
```

## Configuration

New settings in `config.py` (`Settings`), per project convention — no scattered
env reads:

```python
stt_backend: str = "whisper"        # "whisper" | "google"
whisper_model_size: str = "base"    # tiny|base|small|medium|large-v3
whisper_device: str = "auto"        # auto|cpu|cuda
whisper_compute_type: str = "auto"  # auto|int8|float16|float32
whisper_language: str = "en"        # pin to skip language detection (faster)
```

`whisper_compute_type="auto"` lets CTranslate2 pick a safe type per device
(int8 on CPU, float16 on GPU) instead of hardcoding float16, which crashes on
CPU-only machines.

`whisper_language="en"` pins English to skip per-utterance language detection.
Mishears in other languages — acceptable for an English assistant.

## Dependencies

Add to the existing `[jarvis]` optional extra in `pyproject.toml`:

```
"faster-whisper>=1.0.0",
```

Voice users already install this extra (`pip install '.[jarvis]'`) for PyAudio /
SpeechRecognition, so no new install step. No model ships in the repo;
faster-whisper downloads the `base` model (~140MB) from Hugging Face on first run
and caches it under `~/.cache/huggingface`. First `./run.sh voice` after install
pulls the model (one-time, needs network); afterward fully offline.

Document the new env vars in `.env.example` and add a one-line note in `CLAUDE.md`
about the first-run model download. Log a line on first model load so the pause is
not mysterious.

## Error handling

Two distinct fallback layers, kept separate:

### Construction-time (whisper unavailable → switch backend)

`stt_backend="whisper"` but `faster_whisper` import fails → log WARNING, build
`GoogleTranscriber`. Voice still works (needs network). Happens once, at
`SpeechInput.__init__`.

### Call-time (no transcript → no-match, NOT a backend switch)

- Empty / whitespace transcript → return `None`. Loop treats it as "didn't catch
  that" and keeps listening. No mid-session switch to Google — backend is fixed
  after construction (predictable; a transient whisper hiccup must not silently
  start shipping audio to Google).
- Model load failure on the first `transcribe` call (HF download fails, no
  network, disk full) surfaces at call time because the model is lazy-loaded.
  Catch it, log ERROR, return `None`. Voice degrades to "can't hear you" rather
  than crashing the loop. Repeated no-match → user checks logs.

### Capture errors

Unchanged. `WaitTimeoutError`, `ConnectionError`, `OSError` already handled in
`listen_once` and stay as-is.

### Edge cases

- Empty wav / silence → whisper returns empty string → `None`.
- Very long utterance → already bounded by `phrase_time_limit=10.0` at capture.
- Non-English speech → mishear, acceptable.

## Testing

faster-whisper is too heavy to load a real model in CI, so all whisper tests mock
the import / model. `pytest` stays green without faster-whisper installed.

### tests/test_stt_google.py

- `transcribe` returns text on recognizer success (mock `recognize_google`).
- Returns `None` on `UnknownValueError`, `RequestError`, `ConnectionError`.
- Pure logic, no mic, no network.

### tests/test_stt_whisper.py

- Mock `faster_whisper.WhisperModel`; assert lazy-load happens once (model built
  on first `transcribe`, reused after).
- `transcribe` joins segments → stripped text.
- Empty segments → `None`.
- Model construction raises (simulated download failure) → caught, returns `None`,
  logged.
- No real model download.

### tests/test_voice_in_backend_select.py

- `stt_backend="whisper"` + import OK → holds `WhisperTranscriber`.
- `stt_backend="whisper"` + simulated `ImportError` → falls back to
  `GoogleTranscriber`, logs WARNING.
- `stt_backend="google"` → `GoogleTranscriber` direct.
- Mock transcriber classes; assert selection logic only. No mic.

### Manual smoke (in the plan, not CI)

`./run.sh voice`, say wake word, confirm transcription works and first-load model
download succeeds. Verifies real mic capture, model accuracy, and latency, which
unit tests do not cover.

## Out of scope

- Local TTS (Kokoro) — separate future change.
- Streaming / partial transcription.
- Additional STT backends (Deepgram, etc.) — Approach B keeps adding one cheap if
  needed later, but no registry now (YAGNI).
- Wake-word engine replacement.

## Attribution

Pattern adapted from OpenJarvis (`src/openjarvis/speech/faster_whisper.py`,
Apache-2.0). Their backend takes audio files and hardcodes `compute_type="float16"`;
this design takes WAV bytes from the existing capture path and uses `auto` compute
type for CPU safety.