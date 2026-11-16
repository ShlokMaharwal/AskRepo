import threading
from typing import Protocol
from uuid import UUID

from app.config import Settings
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

    def encode(self, texts: list[str], *, query=False) -> list[list[float]]:
        from google import genai
        from google.genai import types

        with self.lock:
            if (
                not self.settings.gemini_api_key
                or not self.settings.gemini_api_key.get_secret_value()
            ):
                raise ValueError("LITE_MODE requires GEMINI_API_KEY for embeddings")
            if self.client is None:
                self.client = genai.Client(
                    api_key=self.settings.gemini_api_key.get_secret_value(),
                    http_options=types.HttpOptions(timeout=60000),
                )
            result = []
            for offset in range(0, len(texts), 32):
                response = self.client.models.embed_content(
                    model=self.name,
                    contents=texts[offset : offset + 32],
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                        output_dimensionality=768,
                    ),
                )
                if not response.embeddings:
                    raise ValueError("Embedding provider returned no embeddings")
                for item in response.embeddings:
                    if not item.values:
                        raise ValueError("Embedding provider returned an empty vector")
                    result.append(item.values)
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
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset : offset + 64]
            embeddings = self.embedder.encode([chunk.text for chunk in batch])
            if len(embeddings) != len(batch):
                raise ValueError("Embedding count does not match chunk count")
            with self.lock:
                client = self._client()
                if offset == 0:
                    if client.collection_exists(name):
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
