"""Centralized configuration via pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env.local overrides .env (later file wins in pydantic-settings)
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── RAG ────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-4-5-20250929"
    # "api" = use Anthropic API (needs ANTHROPIC_API_KEY + credits)
    # "claude_cli" = shell out to `claude` CLI (uses Claude Code subscription)
    agent_backend: str = "api"
    claude_cli_path: str = "claude"
    claude_cli_timeout: int = 60
    chunk_size: int = 500
    chunk_overlap: int = 50
    collection_name: str = "documents"
    memory_collection_name: str = "jarvis_memory"
    memory_top_k: int = 3
    top_k: int = 5
    documents_dir: str = os.path.join(os.path.dirname(__file__), "documents")
    chroma_persist_dir: str = os.path.join(os.path.dirname(__file__), "chroma_db")

    # ── Orchestrator infra ─────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    pg_dsn: str = "postgresql://localhost:5432/orchestrator"
    kafka_servers: str = "localhost:9092"

    # ── Auth ───────────────────────────────────────────────────
    # Must be supplied via JWT_SECRET env var. Empty default prevents
    # an insecure hardcoded value shipping to any environment.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    def require_jwt_secret(self) -> str:
        if not self.jwt_secret or len(self.jwt_secret) < 16:
            raise RuntimeError(
                "JWT_SECRET env var is required (>=16 chars). Generate with: "
                "python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        return self.jwt_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
