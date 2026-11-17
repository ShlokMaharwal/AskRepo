import hashlib
import json
import threading
import time
from typing import Protocol
from uuid import UUID

from app.config import Settings
from app.index.embedding_cache import CloudEmbeddingCache, embedding_key
from app.index.embedding_quota import EmbeddingPacer, EmbeddingQuotaError, retry_delay
from app.ingest.chunker import Chunk


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


class LocalEmbedder:
    def __init__(self, settings: Settings):
        profile = "@dynamic-int8" if settings.quantize_linears else "@embedding-int8"
        self.name = settings.embedding_model + (profile if settings.quantize_models else "")
        if settings.embedding_max_length != 512:
            self.name += f"@tokens{settings.embedding_max_length}"
        self.settings = settings
        self.model = None
        self.lock = threading.RLock()

    def encode(self, texts: list[str], *, query=False) -> list[list[float]]:
        with self.lock:
            if self.model is None:
                import torch
                from sentence_transformers import SentenceTransformer

                torch.set_num_threads(self.settings.model_threads)
                self.model = SentenceTransformer(
                    self.settings.embedding_model,
                    device="cpu",
                    trust_remote_code=False,
                    cache_folder=str(self.settings.model_cache),
                )
                self.model.max_seq_length = min(
                    self.model.max_seq_length, self.settings.embedding_max_length
                )
                if self.settings.quantize_models:
                    from app.index.quantize import quantize_cpu_model

                    self.model[0].auto_model = quantize_cpu_model(
                        self.model[0].auto_model, linears=self.settings.quantize_linears
                    )
            if query and "bge-" in self.name.lower():
                texts = [
                    "Represent this sentence for searching relevant passages: " + text
                    for text in texts
                ]
            return self.model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=self.settings.embedding_batch_size,
                show_progress_bar=False,
            ).tolist()


class GeminiEmbedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.name = settings.gemini_embedding_model
        self.client = None
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.requests = 0
        self.cooldown_until = 0.0
        self.pacer = EmbeddingPacer(settings, self.stop)
        self.embedding_cache = (
            CloudEmbeddingCache(settings)
            if (settings.lite_mode and settings.qdrant_url and settings.embedding_cache_enabled)
            else None
        )

    def close(self):
        self.stop.set()

    def release(self):
        """Release clients only after indexing and retrieval workers have stopped."""
        if self.embedding_cache:
            self.embedding_cache.close()
        if self.client is not None and hasattr(self.client, "close"):
            self.client.close()

    def cooldown_remaining(self):
        return max(0, self.cooldown_until - time.monotonic())

    def embed_batch(self, texts, query):
        from google.genai import types

        for attempt in range(self.settings.gemini_embedding_retries + 1):
            if self.cooldown_remaining() > 0:
                raise EmbeddingQuotaError(
                    "Gemini embedding quota is cooling down; "
                    "background recovery will resume automatically."
                )
            if self.stop.is_set():
                raise RuntimeError("Embedding work stopped")
            self.pacer.acquire(texts)
            try:
                self.requests += 1
                return self.client.models.embed_content(
                    model=self.name,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                        output_dimensionality=768,
                    ),
                )
            except Exception as error:
                code = getattr(error, "code", None) or getattr(
                    getattr(error, "response", None), "status_code", 0
                )
                try:
                    retryable = int(code) == 429 or 500 <= int(code) <= 599
                except (TypeError, ValueError):
                    retryable = False
                wait = retry_delay(error)
                if retryable and wait > 300:
                    self.cooldown_until = time.monotonic() + wait
                    raise EmbeddingQuotaError(
                        "Gemini daily embedding quota is exhausted; "
                        "background recovery will resume after the provider reset."
                    ) from None
                if not retryable or attempt == self.settings.gemini_embedding_retries:
                    raise RuntimeError(
                        "Embedding provider unavailable or quota exhausted; retry later"
                    ) from None
                delay = max(
                    wait, min(300, self.settings.gemini_embedding_backoff_seconds * 2**attempt)
                )
                if self.stop.wait(delay):
                    raise RuntimeError("Embedding work stopped") from None

    def encode(self, texts: list[str], *, query=False) -> list[list[float]]:
        from google import genai

        with self.lock:
            if (
                not self.settings.gemini_api_key
                or not self.settings.gemini_api_key.get_secret_value()
            ):
                raise ValueError("LITE_MODE requires GEMINI_API_KEY for embeddings")
            if self.client is None:
                self.client = genai.Client(
                    api_key=self.settings.gemini_api_key.get_secret_value(),
                    http_options={"timeout": 60000, "retry_options": {"attempts": 1}},
                )
            result = []
            batch_size = self.settings.gemini_embedding_batch_size
            for offset in range(0, len(texts), batch_size):
                batch = texts[offset : offset + batch_size]
                keys = [embedding_key(self.name, text, query) for text in batch]
                cached = self.embedding_cache.get(keys) if self.embedding_cache else {}
                missing = {
                    key: text for key, text in zip(keys, batch, strict=True) if key not in cached
                }
                if missing:
                    response = self.embed_batch(list(missing.values()), query)
                    if not response.embeddings or len(response.embeddings) != len(missing):
                        raise ValueError("Embedding provider returned an incorrect vector count")
                    values = {}
                    for key, item in zip(missing, response.embeddings, strict=True):
                        if not item.values or len(item.values) != 768:
                            raise ValueError(
                                "Embedding provider must return 768-dimensional vectors"
                            )
                        values[key] = item.values
                    if self.embedding_cache:
                        self.embedding_cache.put(values)
                    cached.update(values)
                result.extend(cached[key] for key in keys)
            return result


def get_embedder(settings: Settings) -> Embedder:
    return GeminiEmbedder(settings) if settings.lite_mode else LocalEmbedder(settings)


class Vectors:
    def __init__(self, settings: Settings, embedder: Embedder):
        self.settings, self.embedder = settings, embedder
        self.client = None
        self.lock = threading.RLock()

    def _client(self):
        if self.client is None:
            from qdrant_client import QdrantClient

            if self.settings.qdrant_url:
                if (
                    not self.settings.qdrant_api_key
                    or not self.settings.qdrant_api_key.get_secret_value()
                ):
                    raise ValueError("QDRANT_URL requires QDRANT_API_KEY")
                self.client = QdrantClient(
                    url=self.settings.qdrant_url,
                    api_key=self.settings.qdrant_api_key.get_secret_value(),
                    timeout=60,
                )
            else:
                path = self.settings.data_dir.resolve() / "qdrant"
                path.mkdir(parents=True, exist_ok=True)
                self.client = QdrantClient(path=str(path), force_disable_check_same_thread=True)
        return self.client

    @staticmethod
    def collection(repo_id: str) -> str:
        return "askrepo_" + repo_id

    def build(self, repo_id: str, chunks: list[Chunk]):
        from qdrant_client import models

        name = self.collection(repo_id)
        checkpoint = self.settings.data_dir / "repos" / repo_id / "vector-progress.json"
        digest = hashlib.sha256(
            json.dumps([self.embedder.name, [(chunk.id, chunk.text) for chunk in chunks]]).encode()
        ).hexdigest()
        start = 0
        with self.lock:
            client = self._client()
            try:
                previous = json.loads(checkpoint.read_text(encoding="utf-8"))
                if previous["digest"] == digest and client.collection_exists(name):
                    start = previous["offset"]
                    if not isinstance(start, int) or not 0 <= start <= len(chunks):
                        start = 0
                    elif client.get_collection(name).points_count != start:
                        start = 0
            except (OSError, ValueError, KeyError, TypeError):
                pass
        batch_size = self.settings.gemini_embedding_batch_size if self.settings.lite_mode else 64
        for offset in range(start, len(chunks), batch_size):
            batch = chunks[offset : offset + batch_size]
            embeddings = self.embedder.encode([chunk.text for chunk in batch])
            if len(embeddings) != len(batch):
                raise ValueError("Embedding count does not match chunk count")
            with self.lock:
                client = self._client()
                if offset == 0:
                    if client.collection_exists(name):
                        if not self.settings.qdrant_url:
                            # Embedded Qdrant on Windows can retain an open SQLite
                            # handle while deleting its directory. Clear only this
                            # rebuild target through the public API before recreation.
                            client.delete(name, points_selector=models.Filter(), wait=True)
                        client.delete_collection(name)
                    client.create_collection(
                        name,
                        vectors_config=models.VectorParams(
                            size=len(embeddings[0]), distance=models.Distance.COSINE
                        ),
                    )
                client.upsert(
                    name,
                    wait=True,
                    points=[
                        models.PointStruct(
                            id=str(UUID(chunk.id[:32])),
                            vector=vector,
                            payload={"chunk_id": chunk.id},
                        )
                        for chunk, vector in zip(batch, embeddings, strict=True)
                    ],
                )
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                temporary = checkpoint.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps({"digest": digest, "offset": min(offset + batch_size, len(chunks))}),
                    encoding="utf-8",
                )
                temporary.replace(checkpoint)

    def healthy(self, repo_id, expected_chunks):
        with self.lock:
            client = self._client()
            name = self.collection(repo_id)
            return (
                client.collection_exists(name)
                and client.get_collection(name).points_count == expected_chunks
            )

    def search(self, repo_id: str, question: str, limit=50) -> list[tuple[str, float]]:
        vector = self.embedder.encode([question], query=True)[0]
        with self.lock:
            response = self._client().query_points(
                self.collection(repo_id), query=vector, limit=limit, with_payload=True
            )
        return [(point.payload["chunk_id"], float(point.score)) for point in response.points]

    def delete(self, repo_id: str):
        with self.lock:
            client = self._client()
            name = self.collection(repo_id)
            if client.collection_exists(name):
                client.delete_collection(name)

    def close(self):
        with self.lock:
            if self.client is not None:
                self.client.close()
                self.client = None
