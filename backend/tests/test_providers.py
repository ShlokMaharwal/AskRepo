from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.index.vectors import GeminiEmbedder, Vectors
from app.main import create_app
from tests.fakes import FakeEmbedder, FakeLLM, FakeReranker
from tests.test_contract import fixture_clone, index_fixture


def test_lightweight_mode_skips_the_local_reranker(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, lite_mode=True)
    with TestClient(
        create_app(
            settings,
            embedder=FakeEmbedder(),
            llm=FakeLLM(),
            reranker=FakeReranker(),
            cloner=fixture_clone,
        )
    ) as client:
        repo_id = index_fixture(client)
        response = client.post(
            "/ask", json={"repoId": repo_id, "question": "redis frontier", "rerank": True}
        )
        assert response.status_code == 200 and not response.json()["rerankApplied"]
        assert client.get("/health").json()["liteMode"]


def test_gemini_embeddings_use_distinct_retrieval_task_types(monkeypatch):
    captured = []

    def embed_content(**kwargs):
        captured.append(kwargs["config"].task_type)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3]) for _ in kwargs["contents"]]
        )

    monkeypatch.setattr(
        "google.genai.Client",
        lambda **kwargs: SimpleNamespace(models=SimpleNamespace(embed_content=embed_content)),
    )
    embedder = GeminiEmbedder(Settings(_env_file=None, gemini_api_key="test-only"))
    assert len(embedder.encode(["source code", "another file"])) == 2
    assert len(embedder.encode(["question"], query=True)) == 1
    assert captured == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


def test_gemini_embedding_key_is_required():
    with pytest.raises(ValueError, match="requires GEMINI_API_KEY"):
        GeminiEmbedder(Settings(_env_file=None)).encode(["code"])


def test_cloud_vectors_use_configured_url_and_secret_without_local_path(monkeypatch, tmp_path):
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("qdrant_client.QdrantClient", client)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        qdrant_url="https://cluster.example",
        qdrant_api_key="test-secret",
    )
    vectors = Vectors(settings, FakeEmbedder())
    assert vectors._client() is not None
    assert captured["url"] == "https://cluster.example" and captured["api_key"] == "test-secret"
    assert "path" not in captured
