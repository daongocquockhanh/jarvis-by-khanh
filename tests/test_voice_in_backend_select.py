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