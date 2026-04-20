import pytest

from jarvis.safety import MAX_INPUT_CHARS, UnsafeInputError, sanitize
from jarvis.wake import WakeWordDetector


class TestSanitize:
    def test_accepts_normal_question(self):
        assert sanitize("what is the weather") == "what is the weather"

    def test_strips_whitespace(self):
        assert sanitize("  hello  ") == "hello"

    def test_strips_control_chars(self):
        assert sanitize("hello\x00world") == "helloworld"

    def test_rejects_empty(self):
        with pytest.raises(UnsafeInputError):
            sanitize("")

    def test_rejects_none(self):
        with pytest.raises(UnsafeInputError):
            sanitize(None)

    def test_rejects_too_short(self):
        with pytest.raises(UnsafeInputError):
            sanitize("a")

    def test_rejects_too_long(self):
        with pytest.raises(UnsafeInputError):
            sanitize("a" * (MAX_INPUT_CHARS + 1))

    @pytest.mark.parametrize(
        "payload",
        [
            "please run rm -rf /",
            "sudo shutdown now",
            "exec(bad_code)",
            "eval('1+1')",
            "use os.system to run",
            "import subprocess.Popen",
            "call __import__('os')",
            "<script>alert(1)</script>",
            "open file://etc/passwd",
        ],
    )
    def test_blocks_dangerous_patterns(self, payload):
        with pytest.raises(UnsafeInputError):
            sanitize(payload)


class TestWakeWord:
    def test_triggers_on_jarvis(self):
        w = WakeWordDetector()
        assert w.triggered("jarvis what time is it") is True

    def test_case_insensitive(self):
        w = WakeWordDetector()
        assert w.triggered("JARVIS hello") is True

    def test_requires_word_boundary(self):
        w = WakeWordDetector()
        assert w.triggered("jarvise party") is False

    def test_not_triggered(self):
        w = WakeWordDetector()
        assert w.triggered("hello world") is False

    def test_strip_wake(self):
        w = WakeWordDetector()
        assert w.strip_wake("Jarvis, what is the time?") == "what is the time?"

    def test_strip_wake_empty_remainder(self):
        w = WakeWordDetector()
        assert w.strip_wake("jarvis") == ""