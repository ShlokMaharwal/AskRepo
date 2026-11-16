import pytest

from app.config import Settings
from app.index.bm25 import BM25, tokenize
from app.index.vectors import Vectors
from app.ingest.chunker import chunk_file
from app.retrieve.hybrid import Retriever, expand_neighbors, rrf
from app.storage import Storage
from tests.fakes import FakeEmbedder, FakeReranker


def test_identifier_tokenization():
    tokens = tokenize("URLFrontier get_user_id camelCase HTTPServer")
    assert {
        "urlfrontier",
        "url",
        "frontier",
        "get_user_id",
        "get",
        "user",
        "id",
        "camelcase",
        "camel",
        "case",
        "httpserver",
        "http",
        "server",
    } <= set(tokens)
    assert tokenize("redis redis") == ["redis", "redis"]


def test_bm25_persistence_and_unknown_query(tmp_path):
    chunks = chunk_file("repo", "frontier.py", "def URLFrontier():\n    return 'redis crawler'\n")
    index = BM25.build(chunks)
    index.save(tmp_path / "bm25.json")
    restored = BM25.load(tmp_path / "bm25.json")
    assert restored.search("url frontier")[0][0] == chunks[0].id
    assert restored.search("nonexistentxyz") == []
    assert BM25([], []).search("anything") == []


def test_rrf_deduplicates_and_rewards_agreement():
    ranked = rrf([[("a", 8), ("b", 6)], [("b", 0.9), ("c", 0.8)]])
    assert ranked[0][0] == "b"
    assert dict(ranked)["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert dict(rrf([[("a", 3), ("a", 2)]]))["a"] == pytest.approx(1 / 61)


@pytest.fixture
def indexed(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    storage = Storage(tmp_path)
    repo_id = "a" * 32
    files = [
        (
            "frontier.py",
            "import redis\n\nclass Crawl:\n    def frontier(self):\n        return 'redis crawl'\n",
        ),
        ("rank.py", "def rank_score():\n    return 'rank score'\n"),
    ]
    chunks = [chunk for path, code in files for chunk in chunk_file(repo_id, path, code)]
    storage.save(repo_id, "https://github.com/owner/repo", files, chunks, "test-revision")
    vectors = Vectors(settings, FakeEmbedder())
    retriever = Retriever(storage, vectors, settings)
    model_name = retriever.build(repo_id, chunks)
    storage.ready(repo_id, model_name)
    yield retriever, storage, repo_id, settings
    retriever.close()


@pytest.mark.parametrize("mode", ["bm25", "vector", "hybrid"])
def test_real_local_qdrant_and_hybrid_path(indexed, mode):
    retriever, storage, repo_id, settings = indexed
    result = retriever.query(repo_id, "redis crawl frontier", top_k=2, mode=mode)
    assert result.chunks[0].path == "frontier.py"
    assert all(0 <= chunk.score <= 1 for chunk in result.chunks)
    assert all(chunk.method == mode for chunk in result.chunks)
    assert not result.low_confidence


def test_local_qdrant_survives_restart(indexed):
    retriever, storage, repo_id, settings = indexed
    expected = retriever.vectors.search(repo_id, "redis frontier")
    retriever.vectors.close()
    restored = Vectors(settings, FakeEmbedder())
    try:
        actual = restored.search(repo_id, "redis frontier")
        assert [item[0] for item in actual] == [item[0] for item in expected]
        assert [item[1] for item in actual] == pytest.approx([item[1] for item in expected])
    finally:
        restored.close()


def test_neighbors_do_not_duplicate_selected_chunks():
    source = "import redis\n\nclass Crawl:\n    def frontier(self):\n        return redis\n"
    chunks = chunk_file("repo", "frontier.py", source)
    method = next(chunk for chunk in chunks if chunk.symbol_name == "frontier")
    neighbors = expand_neighbors([method], chunks)
    assert {chunk.kind for chunk in neighbors} == {"imports", "class_header"}
    assert len({chunk.id for chunk in neighbors}) == len(neighbors)
    assert method.id not in {chunk.id for chunk in neighbors}


def test_reranker_and_low_confidence_rule(indexed):
    retriever, storage, repo_id, settings = indexed
    retriever.reranker = FakeReranker()
    result = retriever.query(repo_id, "redis frontier", rerank=True)
    assert result.rerank_applied and not result.low_confidence
    assert result.chunks[0].method == "reranked"
    settings.rerank_threshold = 0.99
    assert retriever.query(repo_id, "redis frontier", rerank=True).low_confidence
    settings.lite_mode = True
    assert not retriever.query(repo_id, "redis frontier", rerank=True).rerank_applied


def test_empty_keyword_results_and_model_mismatch(indexed):
    retriever, storage, repo_id, settings = indexed
    assert retriever.query(repo_id, "nonexistentxyz", mode="bm25").low_confidence
    storage.ready(repo_id, "different-model")
    with pytest.raises(ValueError, match="differs"):
        retriever.query(repo_id, "frontier")
