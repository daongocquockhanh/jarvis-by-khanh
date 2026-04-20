"""Centralized configuration via pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── RAG ────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-4-5-20250929"
    chunk_size: int = 500
    chunk_overlap: int = 50
    collection_name: str = "documents"
    top_k: int = 5
    documents_dir: str = os.path.join(os.path.dirname(__file__), "documents")
    chroma_persist_dir: str = os.path.join(os.path.dirname(__file__), "chroma_db")

    # ── Orchestrator infra ─────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    pg_dsn: str = "postgresql://localhost:5432/orchestrator"
    kafka_servers: str = "localhost:9092"

    # ── Auth ───────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
