"""Persistent memory for JARVIS.

Stores Q&A pairs in a separate ChromaDB collection so the agent can
recall prior conversations and web-learned facts across sessions.
The docs collection (ingested files) stays untouched.
"""

from __future__ import annotations

import hashlib
import logging
import time

import chromadb

from config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=_settings.chroma_persist_dir)
    return _client


def _collection():
    return _get_client().get_or_create_collection(name=_settings.memory_collection_name)


def remember(question: str, answer: str) -> None:
    if not question or not answer:
        return
    try:
        doc = f"Q: {question}\nA: {answer}"
        ts = time.time()
        doc_id = hashlib.sha1(f"{ts}:{question}".encode()).hexdigest()[:16]
        _collection().add(
            ids=[doc_id],
            documents=[doc],
            metadatas=[{"source": "memory", "timestamp": ts, "question": question}],
        )
    except Exception:
        logger.exception("memory.remember failed")


def recall(query: str, top_k: int | None = None) -> list[dict]:
    if top_k is None:
        top_k = _settings.memory_top_k
    try:
        col = _collection()
        if col.count() == 0:
            return []
        results = col.query(query_texts=[query], n_results=min(top_k, col.count()))
    except Exception:
        logger.exception("memory.recall failed")
        return []

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })
    return chunks


def forget_all() -> None:
    try:
        _get_client().delete_collection(_settings.memory_collection_name)
    except Exception:
        logger.exception("memory.forget_all failed")