import json
from types import SimpleNamespace

import pytest

from app.ingest.chunker import chunk_file
from eval.answer_quality import parse_rubric
from eval.deployed_lite import public_configuration
from eval.diagnose_lite import context_variant, diagnostic, distribution
from eval.lite_embeddings import MeasuredEmbeddings


def test_evaluation_configuration_excludes_all_credentials():
    from app.config import Settings

    value = public_configuration(
        Settings(
            _env_file=None,
            gemini_api_key="secret-gemini",
            qdrant_api_key="secret-qdrant",
            admin_token="secret-admin",
        )
    )
    assert "secret-" not in json.dumps(value)
    assert "max_context_chars" in value and "gemini_embedding_model" in value


def test_embedding_cache_separates_tasks_and_never_substitutes_local_vectors(tmp_path):
    calls = []

    def encode(texts, *, query=False):
        calls.append((texts, query))
        return [[float(query)] * 768 for _ in texts]

    measured = MeasuredEmbeddings(SimpleNamespace(name="test-gemini", encode=encode), tmp_path)
    assert measured.encode(["same"], query=True)[0] == [1.0] * 768
    assert measured.encode(["same"], query=True)[0] == [1.0] * 768
    assert measured.encode(["same"], query=False)[0] == [0.0] * 768
    assert calls == [(["same"], True), (["same"], False)]
    assert measured.new_texts == 2 and measured.cache_hits == 1


def test_context_experiment_preserves_exact_citable_source_ranges():
    chunks = chunk_file(
        "repo",
        "crawler.py",
        "import redis\n\nclass Crawl:\n"
        "    def enqueue(self, url):\n        return redis.add(url)\n",
    )
    enhanced = context_variant(chunks)
    assert [chunk.code for chunk in enhanced] == [chunk.code for chunk in chunks]
    assert [(c.path, c.start_line, c.end_line) for c in enhanced] == [
        (c.path, c.start_line, c.end_line) for c in chunks
    ]
    assert any("Context:" in chunk.text for chunk in enhanced)
    assert distribution(chunks)["missing_path_in_embedding"] == 0


@pytest.mark.parametrize("value", [True, -1, 5, "4", None])
def test_automated_judge_does_not_invent_scores_for_invalid_output(value):
    with pytest.raises(ValueError):
        parse_rubric(json.dumps({"score": value, "reason": "test", "unsupported_claims": []}))
    assert parse_rubric('{"score":4,"reason":"supported","unsupported_claims":[]}')["score"] == 4


def test_fixed_over_ast_diagnostics_include_relevance_labels_and_both_rankings():
    rows = [
        dict(
            repo="Seekr",
            id="q1",
            retrieval="hybrid",
            question="where?",
            relevant=[{"path": "a.py"}],
            ranked=[{"path": variant}],
            chunking=variant,
            metrics={"recall@10": score, "mrr": score},
        )
        for variant, score in [("fixed", 1), ("ast", 0)]
    ]
    case = diagnostic({"rows": rows})[0]
    assert case["relevant"] == [{"path": "a.py"}]
    assert case["fixed"][0]["path"] == "fixed" and case["ast"][0]["path"] == "ast"
