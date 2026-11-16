import asyncio
import json
import threading
from contextlib import suppress
from types import SimpleNamespace

import pytest
from starlette.requests import ClientDisconnect

from app.config import Settings
from app.errors import WorkCancelled
from app.generate.llm import GeminiLLM
from app.models import AskRequest
from app.service import AnswerService
from app.streaming import EventStreamResponse, StreamEvent, format_event, heartbeat_events
from tests.fakes import FakeLLM
from tests.test_contract import client as client
from tests.test_contract import index_fixture


def parse_events(text):
    events = []
    for packet in text.split("\n\n"):
        lines = packet.splitlines()
        name = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = [line[6:] for line in lines if line.startswith("data: ")]
        if name:
            events.append((name, json.loads("\n".join(data))))
    return events


def test_sse_format_preserves_unicode_and_escapes_newlines():
    text = format_event(StreamEvent("token", {"text": "line 1\nline 2 →"}))
    assert text.endswith("\n\n")
    assert parse_events(text) == [("token", {"text": "line 1\nline 2 →"})]
    with pytest.raises(ValueError):
        format_event(StreamEvent("token\ndata", {}))


def test_stream_contract_ordering_and_legacy_ask(client):
    repo_id = index_fixture(client)
    payload = {"repoId": repo_id, "question": "redis frontier"}
    response = client.post("/ask/stream", json=payload, headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    events = parse_events(response.text)
    names = [name for name, _ in events]
    stages = [data["stage"] for name, data in events if name == "status"]
    assert stages == ["retrieving", "reranking", "generating"]
    assert (
        names.index("chunks")
        < names.index("token")
        < names.index("citations")
        < names.index("done")
    )
    assert names[-1] == "done" and events[-1][1]["llmCalls"] == 1
    citations = next(data for name, data in events if name == "citations")
    assert citations
    legacy = client.post("/ask", json=payload)
    assert legacy.status_code == 200 and legacy.json()["citations"] == citations


def test_invalid_streamed_citations_are_cleaned_after_generation(client):
    repo_id = index_fixture(client)

    async def stream(question, sources, context):
        source = sources[0]
        yield f"Valid [{source.path}:{source.start_line}-{source.end_line}]. "
        yield "Invented citation [secret.py:1-500]."

    client.app.state.answers.llm.stream = stream
    events = parse_events(
        client.post("/ask/stream", json={"repoId": repo_id, "question": "redis frontier"}).text
    )
    clean = next(data["answer"] for name, data in events if name == "answer_clean")
    assert "secret.py" not in clean
    assert all(
        item["path"] != "secret.py" for name, data in events if name == "citations" for item in data
    )
    assert events[-1][0] == "done" and not events[-1][1]["notFound"]


def test_stream_with_no_valid_citations_is_withheld(client):
    repo_id = index_fixture(client)

    async def stream(*args):
        yield "Unsupported claim [wrong.py:1-100]"

    client.app.state.answers.llm.stream = stream
    events = parse_events(
        client.post("/ask/stream", json={"repoId": repo_id, "question": "redis frontier"}).text
    )
    assert events[-1][1]["notFound"]
    assert next(data for name, data in events if name == "citations") == []
    assert "Unsupported" not in next(
        data["answer"] for name, data in events if name == "answer_clean"
    )


def test_low_confidence_stream_does_not_generate(client):
    repo_id = index_fixture(client)
    client.app.state.settings.rerank_threshold = 0.999
    events = parse_events(
        client.post(
            "/ask/stream", json={"repoId": repo_id, "question": "redis frontier", "agentic": False}
        ).text
    )
    assert events[-1][1]["notFound"] and events[-1][1]["llmCalls"] == 0
    assert client.app.state.answers.llm.calls == 0


def test_stream_errors_are_sanitized_and_share_limits_with_ask(client):
    repo_id = index_fixture(client)

    async def stream(*args):
        yield "A partial answer"
        raise RuntimeError("do-not-expose-this-key")

    client.app.state.answers.llm.stream = stream
    client.app.state.settings.ask_rate_per_minute = 1
    response = client.post("/ask/stream", json={"repoId": repo_id, "question": "redis frontier"})
    assert "do-not-expose-this-key" not in response.text
    events = parse_events(response.text)
    assert events[-1][0] == "error" and events[-2] == ("answer_clean", {"answer": ""})
    assert (
        client.post("/ask", json={"repoId": repo_id, "question": "redis frontier"}).status_code
        == 429
    )


def test_stream_body_cap_and_unknown_repo(client):
    assert (
        client.post("/ask/stream", json={"repoId": "missing", "question": "where"}).status_code
        == 404
    )
    assert (
        client.post(
            "/ask/stream", content=b"x" * (client.app.state.settings.max_request_bytes + 1)
        ).status_code
        == 413
    )


def test_idle_stream_sends_heartbeats_and_closes_iterator():
    async def run():
        closed = False

        async def source():
            nonlocal closed
            try:
                await asyncio.sleep(0.03)
                yield StreamEvent("token", {"text": "ready"})
            finally:
                closed = True

        packets = [packet async for packet in heartbeat_events(source(), interval=0.002)]
        assert packets[0] == ": heartbeat\n\n"
        assert parse_events("".join(packets)) == [("token", {"text": "ready"})]
        assert closed

    asyncio.run(run())


@pytest.mark.parametrize("version", ["2.0", "2.4"])
def test_disconnect_closes_work_on_both_asgi_paths(version):
    async def run():
        sent, closed = asyncio.Event(), asyncio.Event()

        async def source():
            try:
                yield StreamEvent("status", {"stage": "generating", "message": "working"})
                await asyncio.Event().wait()
            finally:
                closed.set()

        async def send(message):
            if message["type"] == "http.response.body":
                sent.set()
                if version == "2.4":
                    raise OSError("disconnected")

        async def receive():
            await sent.wait()
            return {"type": "http.disconnect"}

        response = EventStreamResponse(source(), heartbeat_seconds=0.01)
        with suppress(ClientDisconnect):
            await asyncio.wait_for(
                response({"type": "http", "asgi": {"spec_version": version}}, receive, send),
                timeout=1,
            )
        assert closed.is_set()

    asyncio.run(run())


def test_cancelling_retrieval_prevents_generation():
    started, stopped = threading.Event(), threading.Event()

    def query(*args, cancelled, **kwargs):
        started.set()
        cancelled.wait(timeout=2)
        stopped.set()
        raise WorkCancelled()

    async def run():
        llm = FakeLLM()
        service = AnswerService(SimpleNamespace(query=query), llm, Settings(_env_file=None))
        stream = service.stream(AskRequest(repo_id="repo", question="where"))
        assert (await anext(stream)).event == "status"
        pending = asyncio.create_task(anext(stream))
        assert await asyncio.to_thread(started.wait, 1)
        pending.cancel()
        with suppress(asyncio.CancelledError):
            await pending
        await stream.aclose()
        assert await asyncio.to_thread(stopped.wait, 1)
        assert llm.calls == 0

    asyncio.run(run())


def test_gemini_async_stream_is_closed_on_cancellation(monkeypatch):
    captured = {}

    class Provider:
        models = None

        def __init__(self):
            self.models = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            captured["client_closed"] = True

        async def generate_content_stream(self, **kwargs):
            captured.update(kwargs)

            async def response():
                try:
                    yield SimpleNamespace(text="hello ")
                    await asyncio.Event().wait()
                finally:
                    captured["response_closed"] = True

            return response()

    monkeypatch.setattr("google.genai.Client", lambda **kwargs: SimpleNamespace(aio=Provider()))

    async def run():
        stream = GeminiLLM(Settings(_env_file=None, gemini_api_key="test-key")).stream(
            "where", [], []
        )
        assert await anext(stream) == "hello "
        await stream.aclose()

    asyncio.run(run())
    assert captured["client_closed"] and captured["response_closed"]
    assert captured["config"].system_instruction and not captured["config"].tools
