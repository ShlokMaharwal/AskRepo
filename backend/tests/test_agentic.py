import json

import pytest

from app.errors import DemoLimitError
from app.generate.client import CallBudget
from app.models import AskRequest, AskStreamRequest
from app.retrieve.agentic import alternative_queries, parse_grade
from tests.test_contract import client as client
from tests.test_contract import index_fixture
from tests.test_streaming import parse_events


@pytest.mark.parametrize(
    "output",
    [None, "not JSON", "[]", '{"sufficient":"false"}', '{"missing":"code"}', "```json\nnope\n```"],
)
def test_bad_grader_output_defaults_to_sufficient(output):
    assert parse_grade(output).sufficient


def test_grader_limits_queries_and_retry_identifiers():
    grade = parse_grade(
        {
            "sufficient": False,
            "missing": "x" * 1000,
            "alternative_queries": [
                None,
                "frontier.enqueue",
                "frontier.enqueue",
                "enqueue callers",
                "third",
            ],
        }
    )
    assert not grade.sufficient and len(grade.missing) == 500
    assert grade.alternative_queries == ["frontier.enqueue", "enqueue callers"]
    assert (
        len(alternative_queries("Where is `frontier.enqueue` called?", grade.alternative_queries))
        <= 2
    )
    assert AskRequest(repo_id="x", question="where").agentic is False
    assert AskStreamRequest(repo_id="x", question="where").agentic is True


def test_budget_reserves_final_call_and_never_exceeds_limit():
    budget = CallBudget(3)
    budget.take(reserve=1)
    budget.take(reserve=1)
    with pytest.raises(DemoLimitError):
        budget.take(reserve=1)
    budget.take()
    with pytest.raises(DemoLimitError):
        budget.take()
    assert budget.used == 3


class ImprovingReranker:
    calls = 0

    def score(self, question, documents):
        self.calls += 1
        return [0.5 if self.calls == 1 else 0.98 for _ in documents]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_multiturn_stream_one_retry_and_hard_call_cap(client, limit):
    repo_id = index_fixture(client)
    service = client.app.state.answers
    client.app.state.settings.max_llm_calls_per_question = limit
    reranker = ImprovingReranker()
    client.app.state.retriever.reranker = reranker
    counts = {"rewrite": 0, "grade": 0}

    async def rewrite(*args):
        counts["rewrite"] += 1
        return "Where is redis frontier called?"

    async def grade(*args):
        counts["grade"] += 1
        return json.dumps(
            {
                "sufficient": False,
                "missing": "callers",
                "alternative_queries": ["redis frontier", "Crawl.frontier"],
            }
        )

    service.llm.rewrite, service.llm.grade = rewrite, grade
    response = client.post(
        "/ask/stream",
        json={
            "repoId": repo_id,
            "question": "and where is that called?",
            "history": [
                {"role": "user", "content": "Explain the redis frontier"},
                {"role": "assistant", "content": "`Crawl.frontier` [old.py:1-2]"},
            ],
        },
    )
    events = parse_events(response.text)
    assert events[-1][0] == "done", events
    done = events[-1][1]
    assert done["llmCalls"] == limit and done["retried"] and not done["notFound"]
    assert counts["rewrite"] + counts["grade"] + service.llm.calls == limit
    assert sum(name == "status" and data["stage"] == "retrying" for name, data in events) == 1
    assert reranker.calls == 2
    citations = next(data for name, data in events if name == "citations")
    assert citations and all(item["path"] != "old.py" for item in citations)


def test_strong_results_and_disabled_agentic_mode_skip_grader(client):
    repo_id = index_fixture(client)

    async def unexpected(*args):
        pytest.fail("Strong retrieval must not call the grader")

    client.app.state.answers.llm.grade = unexpected
    for enabled in (True, False):
        client.app.state.settings.agentic_enabled = enabled
        response = client.post(
            "/ask", json={"repoId": repo_id, "question": "redis frontier", "agentic": True}
        )
        assert response.status_code == 200
        assert response.json()["agenticUsed"] is enabled
        assert response.json()["llmCalls"] == 1 and not response.json()["retried"]


def test_still_weak_after_single_retry_returns_closest_sources_without_generation(client):
    repo_id = index_fixture(client)
    client.app.state.settings.agentic_good_score = 0.999

    async def weak(*args):
        return '{"sufficient":false,"missing":"code","alternative_queries":["redis frontier"]}'

    client.app.state.answers.llm.grade = weak
    response = client.post(
        "/ask", json={"repoId": repo_id, "question": "redis frontier", "agentic": True}
    )
    body = response.json()
    assert body["notFound"] and body["retried"] and body["chunks"] and not body["citations"]
    assert body["llmCalls"] == 1 and client.app.state.answers.llm.calls == 0
