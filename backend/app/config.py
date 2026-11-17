from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASKREPO_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    indexing_concurrency: int = Field(default=1, ge=1)
    max_file_bytes: int = Field(default=300 * 1024, ge=1)
    max_repo_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    max_files: int = Field(default=10000, ge=1)
    clone_timeout_seconds: int = Field(default=180, ge=1)
    max_clone_bytes: int = Field(default=200 * 1024 * 1024, ge=1)
    chunk_strategy: Literal["ast", "fixed"] = "ast"
    max_chunk_chars: int = Field(default=6000, ge=256)
    max_queued_jobs: int = Field(default=20, ge=1)
    bootstrap_demos: bool = False
    deployment_id: str = Field(default="local", pattern=r"^[A-Za-z0-9_-]{1,50}$")
    demo_repos: list[str] = [
        "https://github.com/ShlokMaharwal/Seekr",
        "https://github.com/ShlokMaharwal/CodeNest",
        "https://github.com/ShlokMaharwal/DPTrace",
    ]
    bootstrap_retry_seconds: float = Field(default=60, ge=0.1, le=3600)
    gemini_embedding_batch_size: int = Field(default=32, ge=1, le=32)
    gemini_embedding_rpm: int = Field(default=10, ge=1, le=1000)
    gemini_embedding_retries: int = Field(default=3, ge=0, le=5)
    gemini_embedding_backoff_seconds: float = Field(default=5, ge=0, le=300)
    model_threads: int = Field(default=4, ge=1, le=32)
    model_cache: Path = Path("data/models")
    gemini_embedding_model: str = "gemini-embedding-001"
    fusion_threshold: float = Field(default=0.55, ge=0, le=1)
    bm25_threshold: float = Field(default=0.15, ge=0, le=1)
    vector_threshold: float = Field(default=0.55, ge=0, le=1)
    rerank_threshold: float = Field(default=0.2, ge=0, le=1)
    gemini_model: str = "gemini-2.5-flash"
    gemini_fast_model: str = Field(
        default="gemini-2.5-flash-lite", validation_alias="GEMINI_FAST_MODEL"
    )
    gemini_answer_model: str | None = Field(default=None, validation_alias="GEMINI_ANSWER_MODEL")
    max_llm_calls_per_question: int = Field(
        default=3, ge=1, le=10, validation_alias="MAX_LLM_CALLS_PER_QUESTION"
    )
    agentic_enabled: bool = Field(default=True, validation_alias="AGENTIC_ENABLED")
    agentic_good_score: float = Field(default=0.65, ge=0, le=1)
    agentic_lower_score: float = Field(default=0.35, ge=0, le=1)
    llm_global_rpm: int = Field(default=10, ge=1)
    llm_per_ip_rpm: int = Field(default=6, ge=1)
    llm_queue_wait_seconds: float = Field(default=2, ge=0, le=10)
    llm_max_queued: int = Field(default=32, ge=1, le=100)
    llm_max_retries: int = Field(default=2, ge=0, le=2)
    llm_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=10)
    answer_cache_size: int = Field(default=128, ge=0, le=1000)
    answer_cache_ttl_seconds: int = Field(default=600, ge=1, le=3600)
    llm_provider: Literal["auto", "gemini", "extractive"] = "auto"
    max_context_chars: int = Field(default=100000, ge=6000, le=300000)
    ask_rate_per_minute: int = Field(default=30, ge=1)
    index_rate_per_minute: int = Field(default=5, ge=1)
    max_request_bytes: int = Field(default=32768, ge=1024, le=65536)
    quantize_models: bool = False
    quantize_linears: bool = True
    embedding_batch_size: int = Field(default=16, ge=1, le=64)
    reranker_batch_size: int = Field(default=4, ge=1, le=32)
    embedding_max_length: int = Field(default=512, ge=32, le=512)
    reranker_max_length: int = Field(default=512, ge=32, le=512)
    lite_mode: bool = Field(default=False, validation_alias="LITE_MODE")
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    qdrant_url: str | None = Field(default=None, validation_alias="QDRANT_URL")
    qdrant_api_key: SecretStr | None = Field(default=None, validation_alias="QDRANT_API_KEY")
