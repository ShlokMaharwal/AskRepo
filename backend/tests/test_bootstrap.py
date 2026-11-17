import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import Storage
from tests.fakes import FakeEmbedder, FakeLLM
from tests.test_contract import fixture_clone

URL = "https://github.com/owner/example"


def app(settings, cloner=fixture_clone):
    return create_app(settings, embedder=FakeEmbedder(), llm=FakeLLM(), cloner=cloner)


def ready(client):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        health = client.get("/health").json()
        if health["demoRepos"][0]["status"] == "ready":
            return client.get("/repos").json()[0]
        time.sleep(0.02)
    pytest.fail("Demo preparation did not complete")


def config(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        bootstrap_demos=True,
        demo_repos=[URL],
        bootstrap_retry_seconds=0.1,
    )


def test_health_does_not_wait_for_background_indexing(tmp_path):
    release = threading.Event()
    entered = threading.Event()

    def slow(*args):
        entered.set()
        assert release.wait(10)
        return fixture_clone(*args)

    with TestClient(app(config(tmp_path), slow)) as client:
        try:
            assert entered.wait(5)
            start = time.monotonic()
            data = client.get("/health").json()
            assert time.monotonic() - start < 1
            assert data["status"] == "ok"
            assert data["demoRepos"][0]["status"] in {"queued", "indexing"}
        finally:
            release.set()
        assert ready(client)["chunks"] > 0


@pytest.mark.parametrize("missing", ["files", "bm25", "vectors"])
def test_restart_repairs_stale_indexes_and_preserves_healthy_ones(tmp_path, missing):
    settings = config(tmp_path)
    calls = []

    def clone(*args):
        calls.append(args[0])
        return fixture_clone(*args)

    first = app(settings, clone)
    with TestClient(first) as client:
        repo = ready(client)
        repo_id = repo["repoId"]
        if missing == "vectors":
            first.state.retriever.vectors.delete(repo_id)
    root = Storage(tmp_path).repo_dir(repo_id)
    if missing == "files":
        (root / "files/frontier.py").unlink()
    if missing == "bm25":
        (root / "bm25.json").unlink()
    with TestClient(app(settings, clone)) as client:
        assert ready(client)["repoId"] == repo_id
    assert len(calls) == 2
    with TestClient(app(settings, clone)) as client:
        assert ready(client)["repoId"] == repo_id
    assert len(calls) == 2


def test_lost_registry_replaces_only_its_configured_demo_collection(tmp_path):
    from qdrant_client import QdrantClient, models

    settings = config(tmp_path)
    with TestClient(app(settings)) as client:
        repo_id = ready(client)["repoId"]
    with Storage(tmp_path).connect() as db:
        db.execute("delete from repos where id=?", (repo_id,))
    vectors = QdrantClient(path=str(tmp_path / "qdrant"))
    vectors.create_collection(
        "unrelated", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE)
    )
    vectors.upsert(
        "askrepo_" + repo_id,
        points=[
            models.PointStruct(id=123, vector=[0.0] * 8 + [1.0], payload={"chunk_id": "old-orphan"})
        ],
    )
    vectors.close()
    application = app(settings)
    with TestClient(application) as client:
        repo = ready(client)
        assert repo["repoId"] == repo_id
        vector_client = application.state.retriever.vectors._client()
        assert vector_client.collection_exists("unrelated")
        assert vector_client.get_collection("askrepo_" + repo_id).points_count == repo["chunks"]


def test_bootstrap_resumes_after_transient_failure(tmp_path):
    calls = []

    def flaky(*args):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary failure")
        return fixture_clone(*args)

    with TestClient(app(config(tmp_path), flaky)) as client:
        assert ready(client)["chunks"] > 0
    assert len(calls) == 2


def test_repair_removes_obsolete_files_and_next_restart_skips_rebuild(tmp_path):
    calls = []

    def clone(url, path, settings):
        revision = fixture_clone(url, path, settings)
        calls.append(1)
        if len(calls) == 1:
            (path / "removed.py").write_text("def obsolete():\n    return 1\n")
        return revision

    settings = config(tmp_path)
    with TestClient(app(settings, clone)) as client:
        repo_id = ready(client)["repoId"]
    sources = Storage(tmp_path).repo_dir(repo_id) / "files"
    (sources / "frontier.py").unlink()
    with TestClient(app(settings, clone)) as client:
        assert ready(client)["repoId"] == repo_id
        assert not (sources / "removed.py").exists()
    with TestClient(app(settings, clone)) as client:
        assert ready(client)["repoId"] == repo_id
    assert len(calls) == 2


def test_vector_build_resumes_completed_batches_after_failure(tmp_path):
    from app.index.vectors import Vectors
    from app.ingest.chunker import chunk_file

    class Flaky(FakeEmbedder):
        sizes = []

        def encode(self, texts, **kwargs):
            self.sizes.append(len(texts))
            if len(self.sizes) == 2:
                raise RuntimeError("quota")
            return super().encode(texts, **kwargs)

    repo_id = "a" * 32
    chunks = [
        chunk_file(repo_id, f"file{i}.py", f"def redis{i}():\n    return 1\n")[0] for i in range(70)
    ]
    embedder = Flaky()
    vectors = Vectors(Settings(_env_file=None, data_dir=tmp_path), embedder)
    try:
        with pytest.raises(RuntimeError, match="quota"):
            vectors.build(repo_id, chunks)
        vectors.build(repo_id, chunks)
        assert embedder.sizes == [64, 6, 6]
        assert vectors.healthy(repo_id, 70)
    finally:
        vectors.close()


def test_embedding_retries_429_and_batches_without_sleeping(monkeypatch):
    from types import SimpleNamespace

    from app.index.vectors import GeminiEmbedder

    calls = []

    class QuotaError(Exception):
        code = 429

    def embed_content(**kwargs):
        calls.append(kwargs["contents"])
        if len(calls) == 1:
            raise QuotaError("secret must not be surfaced")
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[1.0] * 768) for _ in kwargs["contents"]]
        )

    embedder = GeminiEmbedder(
        Settings(_env_file=None, gemini_api_key="test", gemini_embedding_batch_size=2)
    )
    embedder.client = SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))
    waits = []
    monkeypatch.setattr(embedder.stop, "wait", lambda seconds: waits.append(seconds) or False)
    assert embedder.encode(["a", "b", "c"]) == [[1.0] * 768] * 3
    assert calls == [["a", "b"], ["a", "b"], ["c"]]
    assert max(waits) > 0
