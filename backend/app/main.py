"""AskRepo FastAPI application. Model downloads and ingestion are always explicit."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import DemoBootstrap
from app.config import Settings
from app.errors import DemoLimitError, IndexConfigurationError
from app.generate.llm import get_llm
from app.index.vectors import Vectors, get_embedder
from app.jobs import Jobs
from app.models import (
    AskRequest,
    AskResponse,
    AskStreamRequest,
    FileResponse,
    IndexRequest,
    IndexResponse,
    JobStatus,
    RepoSummary,
)
from app.retrieve.hybrid import Retriever
from app.retrieve.reranker import Reranker
from app.security import RateLimiter, RequestGuard
from app.service import AnswerService
from app.storage import Storage
from app.streaming import EventStreamResponse


def create_app(
    settings: Settings | None = None, *, embedder=None, llm=None, reranker=None, cloner=None
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application):
        storage = Storage(settings.data_dir)
        storage.recover_interrupted()
        vectors = Vectors(settings, embedder or get_embedder(settings))
        rerank_provider = None if settings.lite_mode else (reranker or Reranker(settings))
        retriever = Retriever(storage, vectors, settings, rerank_provider)
        jobs = Jobs(settings, storage, retriever.build, cloner)
        provider = llm or get_llm(settings)
        application.state.storage, application.state.jobs = storage, jobs
        application.state.retriever = retriever
        application.state.answers = AnswerService(retriever, provider, settings)
        bootstrap = DemoBootstrap(settings, storage, jobs, vectors)
        application.state.bootstrap = bootstrap
        bootstrap.start()
        try:
            yield
        finally:
            bootstrap.close()
            jobs.close()
            retriever.close()

    application = FastAPI(title="AskRepo", version="1.0.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.limiter = RateLimiter()
    application.add_middleware(RequestGuard, settings=settings, limiter=application.state.limiter)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def require_repo(repo_id):
        try:
            metadata = application.state.storage.metadata(repo_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(404, "Repository not found") from error
        if metadata["status"] != "ready":
            raise HTTPException(409, "Repository is not ready; wait for indexing to finish")
        return metadata

    @application.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "askrepo",
            "mode": "ready",
            "generation": application.state.answers.llm.name,
            "liteMode": settings.lite_mode,
            "agenticEnabled": settings.agentic_enabled,
            "maxLlmCalls": settings.max_llm_calls_per_question,
            "bootstrapEnabled": settings.bootstrap_demos,
            "demoRepos": application.state.bootstrap.snapshot(),
        }

    @application.post("/index", response_model=IndexResponse)
    def start_index(request: IndexRequest):
        try:
            job_id, repo_id = application.state.jobs.submit(request.repo_url)
        except OverflowError as error:
            raise HTTPException(429, str(error), headers={"Retry-After": "60"}) from error
        return IndexResponse(job_id=job_id, repo_id=repo_id)

    @application.get("/index/{job_id}", response_model=JobStatus, response_model_exclude_none=True)
    def index_status(job_id: str):
        try:
            return application.state.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(404, "Indexing job not found") from error

    @application.post("/ask", response_model=AskResponse)
    def ask(request: AskRequest, http_request: Request):
        require_repo(request.repo_id)
        try:
            return application.state.answers.ask(
                request, ip=http_request.client.host if http_request.client else "unknown"
            )
        except DemoLimitError as error:
            raise HTTPException(
                429,
                {"code": "demo_limit", "message": str(error), "retryAfter": 60},
                headers={"Retry-After": "60"},
            ) from error
        except IndexConfigurationError as error:
            raise HTTPException(
                409, "Index configuration changed; re-index this repository"
            ) from error
        except Exception as error:
            # Provider exception text may contain credentials or internal endpoints.
            raise HTTPException(
                503,
                "Answer service unavailable. Check provider configuration and model availability.",
            ) from error

    @application.post("/compare")
    def compare(request: AskRequest):
        require_repo(request.repo_id)
        try:
            return {
                mode: [
                    chunk.model_dump(by_alias=True)
                    for chunk in application.state.retriever.query(
                        request.repo_id, request.question, request.top_k, mode=mode, rerank=False
                    ).chunks
                ]
                for mode in ("bm25", "vector", "hybrid")
            }
        except Exception as error:
            raise HTTPException(503, "Retrieval comparison unavailable") from error

    @application.post("/ask/stream")
    def ask_stream(request: AskStreamRequest, http_request: Request):
        require_repo(request.repo_id)
        return EventStreamResponse(
            application.state.answers.stream(
                request, ip=http_request.client.host if http_request.client else "unknown"
            )
        )

    @application.get("/file", response_model=FileResponse)
    def get_file(
        repo_id: str = Query(alias="repoId"), path: str = Query(min_length=1, max_length=1024)
    ):
        require_repo(repo_id)
        try:
            content, language = application.state.storage.file(repo_id, path)
            return FileResponse(content=content, language=language)
        except ValueError as error:
            raise HTTPException(400, "Invalid repository file path") from error
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(404, "File not found") from error

    @application.get("/files")
    def get_files(repo_id: str = Query(alias="repoId")):
        require_repo(repo_id)
        return application.state.storage.files(repo_id)

    @application.get("/repos", response_model=list[RepoSummary])
    def repos():
        return application.state.storage.repos()

    return application


app = create_app()
