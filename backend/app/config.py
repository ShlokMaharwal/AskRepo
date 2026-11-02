from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASKREPO_", env_file=".env", extra="ignore"
    )

    data_dir: Path = Path("data")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    indexing_concurrency: int = Field(default=1, ge=1)
    max_file_bytes: int = Field(default=300 * 1024, ge=1)
    max_repo_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    max_files: int = Field(default=10000, ge=1)
    lite_mode: bool = Field(default=False, validation_alias="LITE_MODE")
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    qdrant_url: str | None = Field(default=None, validation_alias="QDRANT_URL")
    qdrant_api_key: SecretStr | None = Field(default=None, validation_alias="QDRANT_API_KEY")
