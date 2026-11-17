"""Quota and cross-restart cache checks using fake Gemini and embedded Qdrant."""

import threading
from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient, models

from app.config import Settings
from app.index.embedding_cache import CloudEmbeddingCache, embedding_key
from app.index.embedding_quota import EmbeddingPacer, EmbeddingQuotaError, retry_delay
from app.index.vectors import GeminiEmbedder


def config(**kwargs):
    return Settings(_env_file=None, **kwargs)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "75"})), 75),
        (SimpleNamespace(response_json={"error": {"details": [{"retryDelay": "91.5s"}]}}), 91.5),
        (SimpleNamespace(message="Please retry in 22h13m35.2s."), 80015.2),
        (SimpleNamespace(message="Requests per day limit exceeded"), 86400),
        (SimpleNamespace(message="unavailable"), 0),
    ],
)
def test_provider_delay_formats(error, expected):
    assert retry_delay(error) == expected


def test_daily_quota_stops_even_when_retries_disabled():
    class Quota(Exception):
        code = 429
        message = "Please retry in 22h13m35.2s. private provider details"

    calls = []

    def exhausted(**kwargs):
        calls.append(kwargs)
        raise Quota()

    embedder = GeminiEmbedder(config(gemini_api_key="test", gemini_embedding_retries=0))
    embedder.client = SimpleNamespace(models=SimpleNamespace(embed_content=exhausted))
    with pytest.raises(EmbeddingQuotaError, match="daily embedding quota") as caught:
        embedder.encode(["a"])
    assert "private" not in str(caught.value)
    assert embedder.cooldown_remaining() > 80000
    with pytest.raises(EmbeddingQuotaError, match="cooling down"):
        embedder.encode(["b"])
    assert len(calls) == 1


def test_minute_budget_counts_inputs_and_tokens_instead_of_http_calls():
    now, waits = [0.0], []

    class ClockStop:
        def wait(self, seconds):
            waits.append(seconds)
            now[0] += seconds
            return False

    pacer = EmbeddingPacer(config(gemini_embedding_rpm=3), ClockStop(), lambda: now[0])
    pacer.acquire(["a", "b"])
    pacer.acquire(["c", "d"])
    assert waits == [60]
    waits.clear()
    pacer = EmbeddingPacer(config(gemini_embedding_tpm=2048), ClockStop(), lambda: now[0])
    pacer.acquire(["x" * 6000])
    pacer.acquire(["y" * 6000])
    assert waits == [60]


def test_pacer_stops_and_rejects_batches_over_budget():
    stop = threading.Event()
    stop.set()
    pacer = EmbeddingPacer(config(gemini_embedding_rpm=1), stop)
    pacer.acquire(["a"])
    with pytest.raises(EmbeddingQuotaError, match="stopped"):
        pacer.acquire(["b"])
    with pytest.raises(EmbeddingQuotaError, match="reduce batch size"):
        pacer.acquire(["a", "b"])


def test_remote_style_cache_survives_local_registry_loss_and_keeps_other_data(tmp_path):
    settings = config(
        lite_mode=True,
        qdrant_url="http://unused",
        qdrant_api_key="test",
        gemini_api_key="test",
        deployment_id="test-cache",
    )
    calls = []

    def fake_api(**kwargs):
        calls.append(kwargs["contents"])
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * 768) for _ in kwargs["contents"]]
        )

    def provider():
        embedder = GeminiEmbedder(settings)
        embedder.client = SimpleNamespace(models=SimpleNamespace(embed_content=fake_api))
        embedder.embedding_cache.client = QdrantClient(path=str(tmp_path / "cloud"))
        return embedder

    first = provider()
    client = first.embedding_cache.connection()
    client.create_collection(
        "unrelated", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE)
    )
    first.encode(["same code", "same code"])
    first.close()
    # Stop must not close a client while the indexing worker is still returning.
    assert client.collection_exists("unrelated")
    first.release()
    second = provider()
    try:
        assert len(second.encode(["same code"])[0]) == 768
        assert calls == [["same code"]]
        second.encode(["same code"], query=True)
        assert len(calls) == 2  # Retrieval tasks do not share a vector.
        assert second.embedding_cache.connection().collection_exists("unrelated")
        assert (
            second.embedding_cache.connection()
            .get_collection(second.embedding_cache.name)
            .points_count
            == 2
        )
    finally:
        second.close()
        second.release()


def test_bounded_cache_preserves_existing_vectors_and_checks_full_digest(tmp_path):
    cache = CloudEmbeddingCache(config(deployment_id="bounded", embedding_cache_max_points=1))
    cache.client = QdrantClient(path=str(tmp_path))
    one, two = (embedding_key("model", text, False) for text in ["a", "b"])
    try:
        cache.put({one: [0.1] * 768})
        cache.put({two: [0.2] * 768})
        assert set(cache.get([one, two])) == {one}
        assert embedding_key("other-model", "a", False) != one
        # A truncated UUID collision alone is insufficient to reuse a vector.
        from uuid import UUID

        cache.client.set_payload(
            cache.name, payload={"input_digest": "wrong"}, points=[str(UUID(one[:32]))]
        )
        assert cache.get([one]) == {}
        assert cache.client.get_collection(cache.name).points_count == 1
    finally:
        cache.close()
