"""Application configuration loaded from the environment (12-factor)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings sourced from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "NexusAI"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Data stores
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # Authentication / JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # LLM provider (provider-agnostic; "mock" runs without credentials).
    # Set llm_provider="openai" with an API key to use OpenAI or any
    # OpenAI-compatible endpoint (Groq, OpenRouter, local server) via base_url.
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_model: str = "mock-chat-001"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 0  # 0 = provider default (no explicit cap)

    # Retrieval / RAG
    retrieval_top_k: int = 20
    rerank_top_k: int = 5
    context_token_budget: int = 2000

    # Agent orchestration
    agent_max_steps: int = 4
    llm_cost_per_1k_tokens: float = 0.0

    # Rate limiting (fixed-window, per authenticated user or client IP)
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Semantic cache (workspace-scoped RAG answer reuse by query similarity)
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.95
    semantic_cache_max_entries: int = 512

    # Observability & security hardening
    metrics_enabled: bool = True
    security_headers_enabled: bool = True
    otel_enabled: bool = False
    sentry_dsn: str = ""

    # Agent memory (short-term conversation recall + long-term run summaries)
    agent_memory_enabled: bool = True
    agent_short_term_turns: int = 6
    agent_long_term_top_k: int = 3
    agent_long_term_max_entries: int = 256

    # Document storage and upload limits
    upload_dir: str = "./var/uploads"
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB

    # Ingest-from-URL: fetch a public http(s) page/file and index it. The size
    # cap reuses ``max_upload_bytes``; only the request timeout is separate.
    url_fetch_timeout_seconds: float = 15.0

    # Chunking (character-based windows with overlap)
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Embeddings (provider-agnostic; "mock" is deterministic and offline)
    embedding_provider: str = "mock"
    embedding_model: str = "mock-embed-001"
    embedding_dimension: int = 384
    embedding_batch_size: int = 64

    # Vector store: "memory" (default, offline) or "qdrant"
    vector_backend: Literal["memory", "qdrant"] = "memory"
    qdrant_collection: str = "nexus_chunks"

    # Ingestion: run the pipeline inline when true (no external worker needed)
    ingest_eager: bool = True

    # Create tables on startup instead of running Alembic migrations. Intended
    # for local/offline runs (e.g. SQLite); keep false in production.
    db_auto_create: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
