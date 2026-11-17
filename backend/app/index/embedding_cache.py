"""Bounded, non-destructive cloud cache for exact Gemini model/task/text inputs."""

import hashlib
import json
from uuid import UUID


def embedding_key(model, text, query):
    return hashlib.sha256(json.dumps([model, query, text]).encode()).hexdigest()


class CloudEmbeddingCache:
    def __init__(self, settings):
        self.settings = settings
        self.name = "askrepo_embedding_cache_" + settings.deployment_id
        self.client = None
        self.prepared = False

    def connection(self):
        from qdrant_client import QdrantClient, models

        if self.client is None:
            if not self.settings.qdrant_api_key:
                raise ValueError("Qdrant credentials are required for the embedding cache")
            self.client = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key.get_secret_value(),
                timeout=30,
            )
        if not self.prepared:
            if not self.client.collection_exists(self.name):
                self.client.create_collection(
                    self.name,
                    vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
                )
            self.prepared = True
        return self.client

    def get(self, keys):
        if not keys:
            return {}
        client = self.connection()
        rows = client.retrieve(
            self.name,
            ids=[str(UUID(key[:32])) for key in keys],
            with_vectors=True,
            with_payload=True,
        )
        result = {}
        for row in rows:
            payload = row.payload or {}
            key = payload.get("input_digest")
            if (
                key in keys
                and payload.get("owner") == self.settings.deployment_id
                and isinstance(row.vector, list)
                and len(row.vector) == 768
            ):
                result[key] = row.vector
        return result

    def put(self, values):
        from qdrant_client import models

        if not values:
            return
        client = self.connection()
        count = client.get_collection(self.name).points_count or 0
        remaining = max(0, self.settings.embedding_cache_max_points - count)
        if remaining == 0:
            return
        points = [
            models.PointStruct(
                id=str(UUID(key[:32])),
                vector=vector,
                payload={"input_digest": key, "owner": self.settings.deployment_id},
            )
            for key, vector in list(values.items())[:remaining]
        ]
        client.upsert(self.name, points=points, wait=True)

    def close(self):
        if self.client is not None:
            self.client.close()
