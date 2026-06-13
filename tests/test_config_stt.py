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