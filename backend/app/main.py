"""Milestone 1 contract server. No repository content is fetched or executed."""

from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.models import (
    AskRequest,
    AskResponse,
    FileResponse,
    IndexRequest,
    IndexResponse,
    JobStatus,
    RepoSummary,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    application = FastAPI(title="AskRepo", version="0.1.0")
    application.state.settings = settings
    application.state.jobs = {}
    application.state.repo_ids = set()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "askrepo", "mode": "stub"}

    def finish_stub(job_id: str) -> None:
        application.state.jobs[job_id] = JobStatus(
            status="failed", error="Indexing is not implemented yet (milestone 2)."
        )

    @application.post("/index", response_model=IndexResponse)
    def start_index(request: IndexRequest, tasks: BackgroundTasks) -> IndexResponse:
        job_id, repo_id = uuid4().hex, uuid4().hex
        application.state.jobs[job_id] = JobStatus(status="cloning")
        application.state.repo_ids.add(repo_id)
        tasks.add_task(finish_stub, job_id)
        return IndexResponse(job_id=job_id, repo_id=repo_id)

    @application.get("/index/{job_id}", response_model=JobStatus, response_model_exclude_none=True)
    def index_status(job_id: str) -> JobStatus:
        job = application.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Indexing job not found")
        return job

    @application.post("/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        if request.repo_id not in application.state.repo_ids:
            raise HTTPException(404, "Repository not found")
        return AskResponse(
            answer="AskRepo retrieval is not implemented yet. No repository evidence is available.",
            not_found=True,
        )

    @application.get("/file", response_model=FileResponse)
    def get_file(repo_id: str = Query(alias="repoId"), path: str = Query(min_length=1)):
        # No file store exists yet. Never open a client-supplied path in this milestone.
        raise HTTPException(404, "No indexed file is available yet")

    @application.get("/repos", response_model=list[RepoSummary])
    def repos() -> list[RepoSummary]:
        return []

    return application


app = create_app()
