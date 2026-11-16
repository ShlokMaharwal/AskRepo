import pytest

from app.config import Settings
from eval.metrics import aggregate, measure, recall_at_k, reciprocal_rank
from eval.run_eval import load_questions


def test_metrics_count_targets_once_and_use_symbol_overlap():
    relevant = [{"path": "a.py", "symbol": "run", "ranges": [(10, 20)]}, {"path": "b.py"}]
    ranked = [
        {"path": "a.py", "start_line": 1, "end_line": 5},
        {"path": "a.py", "start_line": 15, "end_line": 25},
        {"path": "a.py", "start_line": 10, "end_line": 20},
        {"path": "b.py", "start_line": 1, "end_line": 4},
    ]
    assert recall_at_k(ranked, relevant, 1) == 0
    assert recall_at_k(ranked, relevant, 3) == 0.5
    assert recall_at_k(ranked, relevant, 5) == 1
    assert reciprocal_rank(ranked, relevant) == 0.5
    result = measure(ranked, relevant, 123)
    assert result["hit_rate@10"] == 1 and result["latency_ms"] == 123
    assert aggregate([result, result]) == result
    with pytest.raises(ValueError):
        recall_at_k([], [], 1)
    with pytest.raises(ValueError):
        aggregate([])


def test_draft_question_sets_have_fifteen_unique_ids_each():
    import json
    from pathlib import Path

    root = Path(__file__).parents[1] / "eval" / "questions"
    original = [path for path in root.glob("*.jsonl") if path.stem != "followups"]
    assert len(original) == 3
    for path in original:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == len({row["id"] for row in rows}) == 15
        assert all(row["question"].strip() and row["relevant"] for row in rows)


def test_review_gate_refuses_unreviewed_rows(tmp_path):
    with pytest.raises(ValueError, match="Review required"):
        load_questions("Seekr", tmp_path, Settings(_env_file=None), require_reviewed=True)
