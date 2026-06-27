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