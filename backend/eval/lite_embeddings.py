"""Content-addressed Gemini embeddings for a quota-conscious paired experiment."""

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter


class MeasuredEmbeddings:
    def __init__(self, provider, root: Path):
        self.provider, self.name, self.root = provider, provider.name, root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.cache_hits = 0
        self.new_texts = 0

    def key(self, text, query):
        return hashlib.sha256(json.dumps([self.name, query, text]).encode()).hexdigest()

    def encode(self, texts, *, query=False):
        with self.lock:
            records = {}
            missing = {}
            for text in texts:
                key = self.key(text, query)
                path = self.root / (key + ".json")
                if path.exists():
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if record["model"] != self.name or len(record["vector"]) != 768:
                        raise ValueError("Cached embedding profile mismatch")
                    records[key] = record
                    self.cache_hits += 1
                else:
                    missing[key] = text
            if missing:
                started = perf_counter()
                vectors = self.provider.encode(list(missing.values()), query=query)
                elapsed = (perf_counter() - started) * 1000
                for (key, _), vector in zip(missing.items(), vectors, strict=True):
                    if len(vector) != 768:
                        raise ValueError("Gemini embedding output must have 768 dimensions")
                    record = {
                        "model": self.name,
                        "vector": vector,
                        "query": query,
                        "created_at": datetime.now(UTC).isoformat(),
                        "batch_ms": elapsed,
                        "batch_texts": len(missing),
                    }
                    temporary = self.root / (key + ".tmp")
                    temporary.write_text(json.dumps(record), encoding="utf-8")
                    temporary.replace(self.root / (key + ".json"))
                    records[key] = record
                    self.new_texts += 1
            return [records[self.key(text, query)]["vector"] for text in texts]
