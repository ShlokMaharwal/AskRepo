import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.memory import should_rewrite
from app.models import AskRequest, RetrievedChunk
from app.retrieve.hybrid import Retrieval
from app.service import AnswerService
from eval.advanced import load_followups, summarize, update_readme
from eval.metrics import measure
from tests.fakes import FakeLLM


def test_followup_set_has_five_authored_cases_per_repo():
    path = Path(__file__).parents[1] / "eval/questions/followups.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len({row["id"] for row in rows}) == 15
    assert Counter(row["repo"] for row in rows) == {"Seekr": 5, "CodeNest": 5, "DPTrace": 5}
    for row in rows:
        request = AskRequest(repo_id="fixture", question=row["question"], history=row["history"])
        assert should_rewrite(request.question, request.history)
        assert row["relevant"] and "Authored draft" in row["history_origin"]


def test_followup_review_gate_runs_before_source_access(tmp_path):
    with pytest.raises(ValueError, match="Review required"):
        load_followups(tmp_path, Settings(_env_file=None), require_reviewed=True)


def test_advanced_tables_preserve_original_results_and_report_non_improvement(tmp_path):
    metric = dict(measure([], [{"path": "a.py"}], 10), llm_calls=0, retried=0, answered=0)
    rows = [
        {"suite": "standalone", "mode": mode, "metrics": metric}
        for mode in ("single-pass hybrid + rerank", "agentic retrieval")
    ]
    report = {
        "summaries": summarize(rows),
        "provider": "extractive",
        "shared_initial": True,
        "followup_rerank": False,
        "gemini_evaluated": False,
        "ground_truth_status": "draft—human review required",
    }
    readme = tmp_path / "README.md"
    original = (
        "Original results remain here.\n<!-- ASKREPO:EVAL:START -->\n"
        "old measured table\n<!-- ASKREPO:EVAL:END -->\n"
    )
    readme.write_text(original, encoding="utf-8")
    for _ in range(2):
        update_readme(readme, report, Path("measured-advanced.json"))
    text = readme.read_text(encoding="utf-8")
    assert text.startswith(original)
    assert text.count("<!-- ASKREPO:ADVANCED:EVAL:START -->") == 1
    assert "did not improve Recall@10" in text and "No Gemini key was used" in text
    assert "initial model work is not executed twice" in text


def test_paired_initial_search_is_not_rerun_or_mutated():
    initial = Retrieval(
        chunks=[
            RetrievedChunk(
                path="a.py", start_line=1, end_line=1, code="x", score=0.1, method="hybrid"
            )
        ],
        sources=[],
        context=[],
        retrieve_ms=1,
    )

    def unexpected(*args, **kwargs):
        pytest.fail("A paired branch must not rerun its shared initial search")

    def retry(*args, **kwargs):
        return args[3]

    llm = FakeLLM()

    async def grade(*args):
        return '{"sufficient":false,"alternative_queries":["frontier.enqueue"]}'

    llm.grade = grade
    service = AnswerService(
        SimpleNamespace(query=unexpected, retry=retry),
        llm,
        Settings(_env_file=None, answer_cache_size=0),
    )
    answer = service.ask(
        AskRequest(repo_id="fixture", question="redis frontier", agentic=True),
        initial_result=initial,
        initial_ms=12.5,
    )
    assert answer.not_found and answer.retried and not initial.low_confidence
    assert answer.total_ms >= 12.5 and answer.llm_calls == 1 and llm.calls == 0
