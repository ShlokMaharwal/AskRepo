import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.memory import bounded_history


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class IndexRequest(APIModel):
    repo_url: str = Field(max_length=250)

    @field_validator("repo_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        # Restrict the entire input; no credentials, ports, queries or arbitrary hosts.
        match = re.fullmatch(
            r"https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
            r"([A-Za-z0-9_.-]{1,100})/?",
            value,
        )
        if not match:
            raise ValueError("Use a public https://github.com/owner/repo URL")
        owner, repo = match.groups()
        if repo.endswith(".git"):
            repo = repo[:-4]
        if not repo or repo in {".", ".."}:
            raise ValueError("Invalid repository name")
        return f"https://github.com/{owner}/{repo}"


class IndexResponse(APIModel):
    job_id: str
    repo_id: str


class JobStatus(APIModel):
    status: Literal["cloning", "parsing", "chunking", "embedding", "ready", "failed"]
    files_parsed: int = 0
    chunks_created: int = 0
    error: str | None = None
    queued: bool = False


class HistoryMessage(APIModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class AskRequest(APIModel):
    repo_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=8, ge=1, le=50)
    hybrid: bool = True
    rerank: bool = True
    retrieval_mode: Literal["bm25", "vector", "hybrid"] | None = None
    history: list[HistoryMessage] = Field(default_factory=list)
    agentic: bool = False
    request_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,100}$")

    @field_validator("history", mode="before")
    @classmethod
    def recent_history(cls, value):
        return value[-6:] if isinstance(value, list) else value

    @field_validator("history")
    @classmethod
    def cap_history(cls, value):
        return bounded_history(value)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank")
        return value.strip()


class AskStreamRequest(AskRequest):
    agentic: bool = True


class Citation(APIModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class RetrievedChunk(Citation):
    score: float = Field(ge=0, le=1)
    method: Literal["bm25", "vector", "hybrid", "reranked"]
    code: str


class Latency(APIModel):
    retrieve: float = 0
    rerank: float = 0
    generate: float = 0


class AskResponse(APIModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    not_found: bool
    latency_ms: Latency = Field(default_factory=Latency)
    generation_mode: str = "none"
    rerank_applied: bool = False
    llm_calls: int = Field(default=0, ge=0)
    rewritten_question: str | None = None
    rewrite_mode: str = "none"
    agentic_used: bool = False
    retried: bool = False
    total_ms: float = Field(default=0, ge=0)
    cached: bool = False


class FileResponse(APIModel):
    content: str
    language: str


class RepoSummary(APIModel):
    repo_id: str
    repo_url: str
    files: int
    chunks: int
    indexed_at: datetime
