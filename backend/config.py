"""Application settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All required environment variables for the research agent service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM — HuggingFace Inference API
    huggingface_api_key: str
    llm_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    llm_provider: str | None = None  # e.g. "featherless-ai", "together", "novita"

    # Tracing
    langsmith_api_key: str
    langsmith_project: str = "research-agent"

    # Object storage — MinIO (S3-compatible)
    minio_endpoint: str = "http://minio:9000"
    minio_public_endpoint: str = "http://localhost:9000"  # used in presigned URLs returned to clients
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "research-reports"

    # Infrastructure
    redis_url: str = "redis://redis:6379/0"
    environment: str = "development"


settings = Settings()
