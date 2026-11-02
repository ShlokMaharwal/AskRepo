import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None))) as test_client:
        yield test_client


def test_health_and_empty_registry(client):
    assert client.get("/health").json() == {
        "status": "ok", "service": "askrepo", "mode": "stub"
    }
    assert client.get("/repos").json() == []


def test_index_poll_and_ask_contract(client):
    response = client.post("/index", json={"repoUrl": "https://github.com/owner/example.git"})
    assert response.status_code == 200
    job = response.json()
    assert set(job) == {"repoId", "jobId"}
    status = client.get(f"/index/{job['jobId']}").json()
    assert status == {
        "status": "failed",
        "filesParsed": 0,
        "chunksCreated": 0,
        "error": "Indexing is not implemented yet (milestone 2).",
    }
    answer = client.post("/ask", json={"repoId": job["repoId"], "question": "Where is main?"})
    assert answer.status_code == 200
    assert answer.json() == {
        "answer": "AskRepo retrieval is not implemented yet. No repository evidence is available.",
        "citations": [], "chunks": [], "notFound": True,
        "latencyMs": {"retrieve": 0, "rerank": 0, "generate": 0},
    }
    assert client.get("/repos").json() == []  # Failed jobs are never called indexed.


@pytest.mark.parametrize("url", [
    "http://github.com/owner/repo", "https://github.com.evil.test/owner/repo",
    "https://github.com@evil.test/owner/repo", "https://localhost/owner/repo",
    "https://github.com:443/owner/repo", "https://github.com/owner/repo/tree/main",
    "https://github.com/owner/repo?url=https://localhost", "https://github.com/owner/..",
    "https://github.com/owner/.git", "https://github.com/owner/repo\n",
])
def test_rejects_unsafe_urls(client, url):
    assert client.post("/index", json={"repoUrl": url}).status_code == 422


@pytest.mark.parametrize("question", ["", "   ", "q" * 501])
def test_question_limits(client, question):
    response = client.post("/ask", json={"repoId": "unknown", "question": question})
    assert response.status_code == 422


def test_unknown_resources_and_no_file_access(client):
    assert client.get("/index/missing").status_code == 404
    assert client.post("/ask", json={"repoId": "missing", "question": "Why?"}).status_code == 404
    for path in ["README.md", "../.env", "C:\\Windows\\win.ini", "/etc/passwd"]:
        assert client.get("/file", params={"repoId": "missing", "path": path}).status_code == 404


def test_cors(client):
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    response = client.options("/index", headers=headers)
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    headers["Origin"] = "https://untrusted.example"
    assert client.options("/index", headers=headers).status_code == 400


def test_settings_env_and_secret_redaction(monkeypatch):
    monkeypatch.setenv("ASKREPO_CORS_ORIGINS", '["https://askrepo.example"]')
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-secret")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://askrepo.example"]
    assert settings.gemini_api_key.get_secret_value() == "test-only-secret"
    assert "test-only-secret" not in repr(settings)
