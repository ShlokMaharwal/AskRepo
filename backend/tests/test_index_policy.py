import io
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ingest.clone import IngestError, source_files, tree_entries
from app.main import create_app
from tests.fakes import FakeEmbedder, FakeLLM, FakeReranker
from tests.test_contract import fixture_clone, wait_ready

URL = "https://github.com/owner/example"


def application(tmp_path, **options):
    settings = Settings(
        _env_file=None, data_dir=tmp_path, demo_repos=[URL], index_rate_per_minute=100, **options
    )
    return create_app(
        settings,
        embedder=FakeEmbedder(),
        llm=FakeLLM(),
        reranker=FakeReranker(),
        cloner=fixture_clone,
    )


@pytest.mark.parametrize(
    ("mode", "token", "allowed"),
    [
        ("open", None, True),
        ("allowlist", None, True),
        ("token", None, False),
        ("token", "wrong", False),
        ("token", "test-admin", True),
    ],
)
def test_indexing_modes_and_public_queries(tmp_path, mode, token, allowed):
    with TestClient(application(tmp_path, indexing_mode=mode, admin_token="test-admin")) as client:
        assert client.get("/health").json()["indexingMode"] == mode
        response = client.post(
            "/index", json={"repoUrl": URL}, headers={"X-Admin-Token": token} if token else {}
        )
        assert response.status_code == (200 if allowed else 403)
        if allowed:
            wait_ready(client, response.json()["jobId"])
            result = client.post(
                "/ask", json={"repoId": response.json()["repoId"], "question": "redis frontier"}
            )
            assert result.status_code == 200
            if mode != "open":
                again = client.post("/index", json={"repoUrl": URL})
                assert again.json()["repoId"] == response.json()["repoId"]
                assert client.get("/index/" + again.json()["jobId"]).json()["status"] == "ready"


def test_allowlist_rejects_arbitrary_repositories(tmp_path):
    with TestClient(application(tmp_path, indexing_mode="allowlist")) as client:
        response = client.post("/index", json={"repoUrl": "https://github.com/owner/other"})
        assert response.status_code == 403 and "demo repositories" in response.json()["detail"]


def test_daily_cap_is_shared_across_clients_and_persists_with_registry(tmp_path):
    with TestClient(application(tmp_path, max_new_repos_per_day=1)) as client:
        first = client.post("/index", json={"repoUrl": URL})
        wait_ready(client, first.json()["jobId"])
        second = client.post(
            "/index",
            json={"repoUrl": "https://github.com/owner/other"},
            headers={"X-Forwarded-For": "198.51.100.2"},
        )
        assert second.status_code == 429 and "Daily" in second.json()["detail"]
    with TestClient(application(tmp_path, max_new_repos_per_day=1)) as client:
        assert (
            client.post("/index", json={"repoUrl": "https://github.com/owner/new"}).status_code
            == 429
        )
        retry = client.post("/index", json={"repoUrl": URL})
        assert retry.status_code == 200
        wait_ready(client, retry.json()["jobId"])


@pytest.mark.parametrize("limit", ["files", "bytes"])
def test_lite_limits_fail_with_readable_job_errors(tmp_path, limit):
    options = {"lite_max_files": 1} if limit == "files" else {"lite_max_repo_bytes": 5}
    with TestClient(application(tmp_path, lite_mode=True, **options)) as client:
        result = client.post("/index", json={"repoUrl": URL}).json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = client.get("/index/" + result["jobId"]).json()
            if job["status"] == "failed":
                assert "lightweight hosting limits" in job["error"]
                return
            time.sleep(0.01)
        pytest.fail("Expected a lite hosting limit error")


def test_lite_limits_apply_before_checkout_and_leave_full_mode_unchanged(tmp_path):
    settings = Settings(_env_file=None, lite_mode=True, lite_max_repo_bytes=5)
    entry = b"100644 blob " + b"a" * 40 + b" 6\ta.py\0"
    with pytest.raises(IngestError, match="lightweight hosting limits"):
        list(tree_entries(io.BytesIO(entry), settings))
    (tmp_path / "a.py").write_text("123456")
    with pytest.raises(IngestError, match="lightweight hosting limits"):
        source_files(tmp_path, settings)
    assert source_files(tmp_path, settings.model_copy(update={"lite_mode": False}))
