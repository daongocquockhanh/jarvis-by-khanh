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