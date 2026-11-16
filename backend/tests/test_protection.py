import asyncio
from contextlib import suppress
from types import SimpleNamespace

import pytest

from app.cache import AnswerCache, answer_key
from app.config import Settings
from app.errors import DemoLimitError
from app.generate.client import CallBudget, LLMClient, QuestionBudgets
from app.generate.llm import request_options
from app.generate.quota import ProviderQuota
from app.models import AskRequest, AskResponse, AskStreamRequest
from tests.test_contract import client as client
from tests.test_contract import index_fixture
from tests.test_streaming import parse_events


def test_provider_global_and_peer_limits_expire_and_wait_is_bounded():
    async def run():
        now = [0.0]

        async def sleep(seconds):
            now[0] += seconds
            await asyncio.sleep(0)

        settings = Settings(
            _env_file=None, llm_global_rpm=2, llm_per_ip_rpm=1, llm_queue_wait_seconds=0.1
        )
        quota = ProviderQuota(settings, clock=lambda: now[0], sleep=sleep)
        await quota.acquire("one")
        with pytest.raises(DemoLimitError):
            await quota.acquire("one")
        await quota.acquire("two")
        with pytest.raises(DemoLimitError):
            await quota.acquire("three")
        assert not quota.queue and len(quota.global_calls) == 2
        now[0] += 60
        await quota.acquire("one")

    asyncio.run(run())


def test_provider_queue_is_bounded_and_cancellation_removes_waiter():
    async def run():
        settings = Settings(_env_file=None, llm_global_rpm=1, llm_max_queued=1)
        quota = ProviderQuota(settings)
        await quota.acquire("one")
        waiting = asyncio.create_task(quota.acquire("two"))
        await asyncio.sleep(0)
        assert len(quota.queue) == 1
        with pytest.raises(DemoLimitError):
            await quota.acquire("three")
        waiting.cancel()
        with suppress(asyncio.CancelledError):
            await waiting
        assert not quota.queue

    asyncio.run(run())


class BusyError(Exception):
    code = 429


@pytest.mark.parametrize("limit,expected", [(1, 1), (2, 2), (3, 3), (10, 3)])
def test_backoff_never_bypasses_attempt_or_question_cap(limit, expected):
    async def run():
        calls, waits = [], []

        async def grade(*args):
            calls.append(1)
            raise BusyError("secret text must not escape")

        async def sleep(seconds):
            waits.append(seconds)

        settings = Settings(_env_file=None, llm_global_rpm=100, llm_per_ip_rpm=100)
        provider = SimpleNamespace(name="fake", grade=grade)
        wrapped = LLMClient(provider, settings, sleep=sleep)
        budget = CallBudget(limit)
        with pytest.raises(DemoLimitError, match="Demo limit reached"):
            await wrapped.call("grade", "question", [], budget=budget)
        assert len(calls) == budget.used == expected
        assert waits == [0.5, 1.0][: expected - 1]
        assert request_options().retry_options.attempts == 1

    asyncio.run(run())


def test_provider_stream_never_replays_text_after_partial_failure():
    async def run():
        calls = 0

        async def stream(*args):
            nonlocal calls
            calls += 1
            yield "partial"
            raise BusyError()

        wrapped = LLMClient(SimpleNamespace(name="fake", stream=stream), Settings(_env_file=None))
        budget = CallBudget(3)
        iterator = wrapped.stream(budget=budget)
        assert await anext(iterator) == "partial"
        with pytest.raises(DemoLimitError):
            await anext(iterator)
        assert calls == budget.used == 1

    asyncio.run(run())


def test_answer_cache_ttl_lru_and_copies():
    now = [0]
    cache = AnswerCache(2, 600, clock=lambda: now[0])
    answer = AskResponse(answer="evidence", not_found=False)
    cache.put("one", answer)
    cache.put("two", answer)
    cache.get("one").answer = "changed"
    assert cache.get("one").answer == "evidence"
    cache.put("three", answer)
    assert cache.get("two") is None
    now[0] = 600
    assert cache.get("one") is None


def test_cache_key_includes_history_settings_and_rewritten_query():
    settings = Settings(_env_file=None)
    first = AskRequest(repo_id="repo", question="Where is frontier?", request_id="first-123")
    another_id = first.model_copy(update={"request_id": "second-123"})
    assert answer_key(first, settings, "provider") == answer_key(another_id, settings, "provider")
    followup = AskRequest(
        repo_id="repo",
        question="Where is frontier?",
        history=[{"role": "assistant", "content": "another context"}],
    )
    assert answer_key(first, settings, "provider") != answer_key(followup, settings, "provider")
    assert answer_key(first, settings, "provider", rewritten="frontier.enqueue") != answer_key(
        first, settings, "provider"
    )


def test_complete_cached_answer_replays_without_provider_calls(client):
    repo_id = index_fixture(client)
    payload = {"repoId": repo_id, "question": "redis frontier", "agentic": False}
    first = client.post("/ask", json=payload).json()
    calls = client.app.state.answers.llm.calls
    events = parse_events(client.post("/ask/stream", json=payload).text)
    assert events[-1][1]["cached"] and events[-1][1]["llmCalls"] == 0
    assert next(data for name, data in events if name == "citations") == first["citations"]
    assert client.app.state.answers.llm.calls == calls


def test_logical_stream_fallback_shares_a_budget_and_returns_structured_error(client):
    repo_id = index_fixture(client)
    service = client.app.state.answers
    client.app.state.settings.max_llm_calls_per_question = 1

    async def broken(*args):
        service.llm.calls += 1
        yield "partial"
        raise BusyError()

    service.llm.stream = broken
    payload = {
        "repoId": repo_id,
        "question": "redis frontier",
        "agentic": False,
        "requestId": "same-question-123",
    }
    events = parse_events(client.post("/ask/stream", json=payload).text)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "demo_limit"
    fallback = client.post("/ask", json=payload)
    assert fallback.status_code == 429
    assert fallback.json()["detail"]["message"] == "Demo limit reached, try again in a minute"
    assert service.llm.calls == 1


def test_question_registry_is_bounded_and_expires():
    now = [0]
    registry = QuestionBudgets(max_size=1, ttl=10, clock=lambda: now[0])
    budget = registry.get("same", 3)
    budget.take()
    assert registry.get("same", 3).used == 1
    with pytest.raises(DemoLimitError):
        registry.get("other", 3)
    now[0] = 10
    assert registry.get("other", 3).used == 0


def test_cancelled_answer_is_not_cached(client):
    repo_id = index_fixture(client)
    service = client.app.state.answers
    closed = []

    async def slow(*args):
        try:
            yield "unfinished"
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    service.llm.stream = slow

    async def run():
        stream = service.stream(
            AskStreamRequest(repo_id=repo_id, question="redis frontier", agentic=False)
        )
        async for event in stream:
            if event.event == "token":
                break
        await stream.aclose()

    asyncio.run(run())
    assert closed and not service.cache.items
