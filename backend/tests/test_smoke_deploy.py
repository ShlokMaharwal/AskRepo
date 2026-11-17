import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "smoke_deploy", Path(__file__).parents[2] / "scripts/smoke_deploy.py"
)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_smoke_checks_complete_json_and_stream_contract(capsys):
    names = ["Seekr", "CodeNest", "DPTrace"]
    citation = {"path": "a.py", "startLine": 1, "endLine": 1}

    def request(value):
        path = value.url.path
        if value.method == "OPTIONS":
            return httpx.Response(
                200, headers={"access-control-allow-origin": "https://front.test"}
            )
        if value.url.host == "front.test":
            return httpx.Response(200, text="AskRepo")
        if path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "demoRepos": [{"name": name, "status": "ready", "chunks": 1} for name in names],
                },
            )
        if path == "/repos":
            return httpx.Response(
                200,
                json=[
                    {"repoId": name, "repoUrl": "https://github.com/a/" + name} for name in names
                ],
            )
        if path == "/file":
            return httpx.Response(200, json={"content": "pass\n"})
        if path == "/ask":
            return httpx.Response(
                200, json={"answer": "Code", "notFound": False, "citations": [citation]}
            )
        if path == "/ask/stream":
            events = [
                ("status", {}),
                ("chunks", [citation]),
                ("token", {"text": "Code"}),
                ("citations", [citation]),
                ("done", {"notFound": False}),
            ]
            body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        raise AssertionError(path)

    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        smoke.smoke(
            "https://api.test", "https://front.test", client, delay_seconds=0, sleep=lambda _: None
        )
    assert "PASS deployment smoke checks" in capsys.readouterr().out


def test_smoke_rejects_truncated_streams_and_bad_source_ranges():
    with pytest.raises(smoke.SmokeFailure, match="truncated"):
        smoke.stream_answer(["event: token", 'data: {"text":"partial"}', ""])
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"content": "one line"}))
    ) as client:
        with pytest.raises(smoke.SmokeFailure, match="outside"):
            smoke.validate_citations(
                client, "https://api.test", "repo", [{"path": "a.py", "startLine": 1, "endLine": 2}]
            )


def test_smoke_rejects_urls_containing_credentials_or_paths():
    for value in ["https://user:secret@api.test", "https://api.test/docs", "file:///tmp/foo"]:
        with pytest.raises(smoke.SmokeFailure):
            smoke.origin(value)
