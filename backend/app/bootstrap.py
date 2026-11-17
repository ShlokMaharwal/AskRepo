"""Recover configured demo snapshots without blocking startup or deleting unknown data."""

import logging
import threading
from uuid import NAMESPACE_URL, uuid5

from app.models import IndexRequest

logger = logging.getLogger(__name__)


class DemoBootstrap:
    def __init__(self, settings, storage, jobs, vectors):
        self.settings, self.storage, self.jobs, self.vectors = settings, storage, jobs, vectors
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.urls = (
            list(dict.fromkeys(IndexRequest(repo_url=url).repo_url for url in settings.demo_repos))
            if settings.bootstrap_demos
            else []
        )
        self.states = {
            url: {"name": url.rsplit("/", 1)[-1], "status": "queued", "chunks": 0}
            for url in self.urls
        }
        self.thread = None

    def snapshot(self):
        with self.lock:
            return [dict(self.states[url]) for url in self.urls]

    def update(self, url, status, chunks=0, error=None):
        with self.lock:
            self.states[url].update(status=status, chunks=chunks)
            if error:
                self.states[url]["error"] = error
            else:
                self.states[url].pop("error", None)

    def start(self):
        if self.urls:
            self.thread = threading.Thread(target=self.run, name="askrepo-bootstrap", daemon=True)
            self.thread.start()

    def ensure(self, url):
        entries = [entry for entry in self.storage.entries() if entry["url"].lower() == url.lower()]
        for entry in entries:
            if self.storage.healthy_local(entry["id"], self.vectors.embedder.name):
                if self.vectors.healthy(entry["id"], entry["chunks"]):
                    self.update(url, "ready", entry["chunks"])
                    return
            if entry["status"] == "ready":
                self.storage.stale(entry["id"])
        # After disk loss, only this configured demo's stable collection is replaced
        # by the index builder. Never enumerate/delete unrelated remote collections.
        repo_id = (
            entries[-1]["id"]
            if entries
            else uuid5(
                NAMESPACE_URL, "askrepo:demo:" + self.settings.deployment_id + ":" + url.lower()
            ).hex
        )
        if not entries:
            # A checkpoint is meaningful only together with its local registry entry.
            (self.storage.repo_dir(repo_id) / "vector-progress.json").unlink(missing_ok=True)
        job_id, _ = self.jobs.submit(url, repo_id=repo_id)
        while not self.stop.is_set():
            job = self.jobs.get(job_id)
            self.update(url, "queued" if job.queued else "indexing", job.chunks_created)
            if job.status == "ready":
                self.update(url, "ready", job.chunks_created)
                return
            if job.status == "failed":
                self.update(url, "failed", job.chunks_created, job.error)
                return
            self.stop.wait(0.1)

    def run(self):
        attempt = 0
        while not self.stop.is_set():
            for url in self.urls:
                if self.stop.is_set():
                    return
                if self.states[url]["status"] == "ready":
                    continue
                try:
                    self.ensure(url)
                except Exception:
                    logger.warning("Demo preparation unavailable; a bounded retry is scheduled")
                    self.update(url, "failed")
            if all(row["status"] == "ready" for row in self.snapshot()):
                return
            delay = min(3600, self.settings.bootstrap_retry_seconds * 2 ** min(attempt, 6))
            cooldown = getattr(self.vectors.embedder, "cooldown_remaining", lambda: 0)()
            delay = max(delay, cooldown)
            attempt += 1
            self.stop.wait(delay)

    def close(self):
        self.stop.set()
        close = getattr(self.vectors.embedder, "close", None)
        if close:
            close()
        if self.thread:
            self.thread.join(timeout=2)
