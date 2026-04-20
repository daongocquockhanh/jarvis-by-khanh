"""Tests for ingest — chunk_text unit tests."""

from ingest import chunk_text


class TestChunkText:
    def test_basic_chunking(self):
        text = "a" * 100
        chunks = chunk_text(text, chunk_size=30, overlap=10)
        assert len(chunks) > 1
        assert chunks[0] == "a" * 30

    def test_overlap(self):
        text = "abcdefghij" * 10  # 100 chars
        chunks = chunk_text(text, chunk_size=30, overlap=10)
        # Each chunk starts 20 chars after the previous one
        assert chunks[0] == text[0:30]
        assert chunks[1] == text[20:50]

    def test_empty_text(self):
        chunks = chunk_text("", chunk_size=10, overlap=5)
        assert chunks == []

    def test_text_shorter_than_chunk(self):
        chunks = chunk_text("hello", chunk_size=100, overlap=10)
        assert chunks == ["hello"]

    def test_exact_chunk_size(self):
        text = "a" * 50
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_zero_overlap(self):
        text = "a" * 100
        chunks = chunk_text(text, chunk_size=25, overlap=0)
        assert len(chunks) == 4
        assert all(len(c) == 25 for c in chunks)
