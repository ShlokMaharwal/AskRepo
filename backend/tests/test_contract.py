import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import RateLimiter
from tests.fakes import FakeEmbedder, FakeLLM, FakeReranker


def fixture_clone(url, path, settings):
    path.mkdir()
    (path / "frontier.py").write_text(
        "import redis\n\nclass Crawl:\n    def frontier(self):\n        return 'redis crawler'\n"
    )
    (path / "README.md").write_text("# Crawler\nRedis frontier queues crawl URLs.\n")
    return "fixture-commit"


def wait_ready(client, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/index/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"ready", "failed"}:
            assert job["status"] == "ready", job
            return job
        time.sleep(0.01)
    pytest.fail("Fixture indexing did not finish")


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        _env_file=None, data_dir=tmp_path, index_rate_per_minute=100, ask_rate_per_minute=100
    )
    with TestClient(
        create_app(
            settings,
            embedder=FakeEmbedder(),
            llm=FakeLLM(),
            reranker=FakeReranker(),
            cloner=fixture_clone,
        )
    ) as test_client:
        yield test_client


def index_fixture(client):
    response = client.post("/index", json={"repoUrl": "https://github.com/owner/example.git"})
    assert response.status_code == 200
    indexed = response.json()
    assert set(indexed) == {"jobId", "repoId"}
    wait_ready(client, indexed["jobId"])
    return indexed["repoId"]


def test_health_and_empty_registry(client):
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "askrepo",
        "mode": "ready",
        "generation": "test-stub",
        "liteMode": False,
        "agenticEnabled": True,
        "maxLlmCalls": 3,
        "bootstrapEnabled": False,
        "demoRepos": [],
        "indexingMode": "open",
    }
    assert client.get("/repos").json() == []


def test_index_ask_cited_file_and_comparison_integration(client):
    repo_id = index_fixture(client)
    response = client.post(
        "/ask", json={"repoId": repo_id, "question": "How does the Redis frontier crawl?"}
    )
    assert response.status_code == 200
    answer = response.json()
    assert not answer["notFound"] and answer["citations"]
    assert answer["rerankApplied"] and answer["generationMode"] == "test-stub"
    assert set(answer["latencyMs"]) == {"retrieve", "rerank", "generate"}
    for citation in answer["citations"]:
        file = client.get("/file", params={"repoId": repo_id, "path": citation["path"]})
        assert file.status_code == 200
        assert (
            1
            <= citation["startLine"]
            <= citation["endLine"]
            <= len(file.json()["content"].splitlines())
        )
    assert len(client.get("/repos").json()) == 1
    assert len(client.get("/files", params={"repoId": repo_id}).json()) == 2
    comparison = client.post(
        "/compare", json={"repoId": repo_id, "question": "redis frontier", "topK": 3}
    )
    assert set(comparison.json()) == {"bm25", "vector", "hybrid"}
    assert not (client.app.state.storage.root / "tmp" / repo_id).exists()


def test_low_confidence_never_calls_llm(client):
    repo_id = index_fixture(client)
    client.app.state.settings.rerank_threshold = 0.999
    llm = client.app.state.answers.llm
    response = client.post("/ask", json={"repoId": repo_id, "question": "redis frontier"})
    assert response.json()["notFound"] and llm.calls == 0
    assert response.json()["latencyMs"]["generate"] == 0


def test_index_survives_application_restart(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)

    def app():
        return create_app(
            settings,
            embedder=FakeEmbedder(),
            llm=FakeLLM(),
            reranker=FakeReranker(),
            cloner=fixture_clone,
        )

    with TestClient(app()) as first:
        repo_id = index_fixture(first)
    with TestClient(app()) as second:
        assert second.get("/repos").json()[0]["repoId"] == repo_id
        response = second.post("/ask", json={"repoId": repo_id, "question": "redis frontier"})
        assert response.status_code == 200 and response.json()["citations"]


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://github.com.evil.test/owner/repo",
        "https://github.com@evil.test/owner/repo",
        "https://localhost/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner/repo?url=https://localhost",
        "https://github.com/owner/..",
        "https://github.com/owner/.git",
        "https://github.com/owner/repo\n",
    ],
)
def test_rejects_unsafe_urls(client, url):
    assert client.post("/index", json={"repoUrl": url}).status_code == 422


@pytest.mark.parametrize("question", ["", "   ", "q" * 501])
def test_question_limits(client, question):
    assert client.post("/ask", json={"repoId": "missing", "question": question}).status_code == 422


def test_path_traversal_is_rejected_for_an_existing_repository(client):
    repo_id = index_fixture(client)
    for path in ["../.env", "C:/Windows/win.ini", "/etc/passwd", "a/../../.env", "a\\b"]:
        assert client.get("/file", params={"repoId": repo_id, "path": path}).status_code == 400
    assert client.get("/file", params={"repoId": repo_id, "path": "missing.py"}).status_code == 404


def test_unknown_resources(client):
    assert client.get("/index/missing").status_code == 404
    assert client.post("/ask", json={"repoId": "missing", "question": "Why?"}).status_code == 404
    assert client.get("/file", params={"repoId": "missing", "path": "app.py"}).status_code == 404


def test_cors(client):
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    response = client.options("/index", headers=headers)
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    headers["Origin"] = "https://untrusted.example"
    assert client.options("/index", headers=headers).status_code == 400


def test_request_size_and_rate_limits(client):
    assert (
        client.post(
            "/ask", content="x" * (client.app.state.settings.max_request_bytes + 1)
        ).status_code
        == 413
    )
    client.app.state.settings.index_rate_per_minute = 1
    assert (
        client.post("/index", json={"repoUrl": "https://github.com/owner/repo"}).status_code == 200
    )
    assert (
        client.post("/index", json={"repoUrl": "https://github.com/owner/repo"}).status_code == 429
    )


def test_rate_limit_window_and_bucket_bound():
    now = [0.0]
    limiter = RateLimiter(max_buckets=2, clock=lambda: now[0])
    assert limiter.allow("ip", "ask", 1)
    assert not limiter.allow("ip", "ask", 1)
    now[0] = 61
    assert limiter.allow("ip", "ask", 1)
    assert limiter.allow("other", "ask", 1)
    assert not limiter.allow("third", "ask", 1)


def test_settings_env_and_secret_redaction(monkeypatch):
    monkeypatch.setenv("ASKREPO_CORS_ORIGINS", '["https://askrepo.example"]')
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-secret")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://askrepo.example"]
    assert settings.gemini_api_key.get_secret_value() == "test-only-secret"
    assert "test-only-secret" not in repr(settings)


def test_forwarded_headers_cannot_bypass_ip_limits(client):
    client.app.state.settings.ask_rate_per_minute = 1
    body = {"repoId": "missing", "question": "Where?"}
    assert client.post("/ask", json=body, headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 404
    assert client.post("/ask", json=body, headers={"X-Forwarded-For": "5.6.7.8"}).status_code == 429


def test_provider_error_is_sanitized_and_is_not_a_reindex_error(client):
    repo_id = index_fixture(client)

    def fail(*args):
        raise ValueError("provider rejected secret-example-key")

    client.app.state.answers.llm.generate = fail
    response = client.post("/ask", json={"repoId": repo_id, "question": "redis frontier"})
    assert response.status_code == 503
    assert "secret-example-key" not in response.text
