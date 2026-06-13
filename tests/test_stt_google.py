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