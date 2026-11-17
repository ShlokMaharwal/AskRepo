"""Bounded in-process indexing queue, with durable completion in Storage."""

import os
import shutil
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.ingest.chunker import chunk_file
from app.ingest.clone import IngestError, clone_repository, source_files
from app.models import JobStatus
from app.storage import Storage


def cleanup_clone(path: Path, temporary_root: Path):
    if path.resolve() == temporary_root.resolve() or not path.resolve().is_relative_to(
        temporary_root.resolve()
    ):
        raise ValueError("Unsafe clone cleanup path")

    def writable(function, filename, error):
        os.chmod(filename, stat.S_IWRITE | stat.S_IREAD)
        function(filename)

    if path.exists():
        shutil.rmtree(path, onerror=writable)


class Jobs:
    def __init__(self, settings: Settings, storage: Storage, build_index=None, cloner=None):
        self.settings, self.storage = settings, storage
        self.build_index = build_index
        self.cloner = cloner or clone_repository
        self.executor = ThreadPoolExecutor(
            max_workers=settings.indexing_concurrency, thread_name_prefix="askrepo-index"
        )
        self.lock = threading.RLock()
        self.jobs: dict[str, JobStatus] = {}
        self.pending = 0
        self.active_urls = {}
        self.temporary_root = storage.root / "tmp"
        self.temporary_root.mkdir(exist_ok=True)

    def submit(self, url: str, *, repo_id=None) -> tuple[str, str]:
        with self.lock:
            if url.lower() in self.active_urls:
                return self.active_urls[url.lower()]
            if self.pending >= self.settings.indexing_concurrency + self.settings.max_queued_jobs:
                raise OverflowError("Indexing queue is full; try again later")
            # Keep the registry bounded, retaining active jobs and the most recent outcomes.
            for key in list(self.jobs):
                if len(self.jobs) < 500:
                    break
                if self.jobs[key].status in {"ready", "failed"}:
                    del self.jobs[key]
            job_id, repo_id = uuid4().hex, repo_id or uuid4().hex
            self.jobs[job_id] = JobStatus(status="cloning", queued=True)
            self.pending += 1
            self.active_urls[url.lower()] = (job_id, repo_id)
            self.executor.submit(self.run, job_id, repo_id, url)
            return job_id, repo_id

    def get(self, job_id: str) -> JobStatus:
        with self.lock:
            return self.jobs[job_id].model_copy()

    def update(self, job_id: str, **updates):
        with self.lock:
            self.jobs[job_id] = self.jobs[job_id].model_copy(update=updates)

    def run(self, job_id: str, repo_id: str, url: str):
        clone_path = self.temporary_root / repo_id
        try:
            self.update(job_id, queued=False)
            revision = self.cloner(url, clone_path, self.settings)
            self.update(job_id, status="parsing")
            files = source_files(clone_path, self.settings)
            self.update(job_id, status="chunking", files_parsed=len(files))
            chunks = []
            for path, content in files:
                chunks.extend(
                    chunk_file(
                        repo_id,
                        path,
                        content,
                        self.settings.chunk_strategy,
                        self.settings.max_chunk_chars,
                    )
                )
                self.update(job_id, chunks_created=len(chunks))
            if not chunks:
                raise IngestError("No supported text or source files were found in the repository")
            self.storage.save(repo_id, url, files, chunks, revision)
            # Remove checkout and Git metadata before expensive model inference.
            cleanup_clone(clone_path, self.temporary_root)
            self.update(job_id, status="embedding")
            embedding_model = self.build_index(repo_id, chunks) if self.build_index else ""
            self.storage.ready(repo_id, embedding_model)
            self.update(job_id, status="ready")
        except (IngestError, ValueError) as error:
            self.storage.fail(repo_id)
            self.update(job_id, status="failed", error=str(error))
        except Exception:
            self.storage.fail(repo_id)
            self.update(
                job_id,
                status="failed",
                error="Indexing failed. Check model availability and storage configuration.",
            )
        finally:
            try:
                cleanup_clone(clone_path, self.temporary_root)
            finally:
                with self.lock:
                    self.pending -= 1
                    self.active_urls.pop(url.lower(), None)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=False)
