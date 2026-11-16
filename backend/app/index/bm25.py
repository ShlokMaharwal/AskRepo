import json
import math
import re
from collections import Counter
from pathlib import Path

from app.ingest.chunker import Chunk


def tokenize(text: str) -> list[str]:
    result = []
    for original in re.findall(r"[A-Za-z_][A-Za-z_0-9]*|\d+", text):
        expanded = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", original)
        expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", expanded)
        parts = expanded.replace("_", " ").lower().split()
        result.extend(dict.fromkeys([original.lower(), *parts]))
    return result


class BM25:
    def __init__(self, ids: list[str], documents: list[list[str]], k1=1.5, b=0.75):
        self.ids, self.documents = ids, documents
        self.k1, self.b = k1, b
        self.frequencies = [Counter(document) for document in documents]
        self.lengths = [len(document) for document in documents]
        self.average = sum(self.lengths) / max(len(documents), 1)
        self.document_frequency = Counter(
            token for frequency in self.frequencies for token in frequency
        )
        self.postings: dict[str, list[int]] = {}
        for index, frequency in enumerate(self.frequencies):
            for token in frequency:
                self.postings.setdefault(token, []).append(index)

    @classmethod
    def build(cls, chunks: list[Chunk]):
        return cls([chunk.id for chunk in chunks], [tokenize(chunk.text) for chunk in chunks])

    def search(self, question: str, limit=50) -> list[tuple[str, float]]:
        scores: dict[int, float] = {}
        total = len(self.ids)
        for token in set(tokenize(question)):
            df = self.document_frequency[token]
            if not df:
                continue
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            for index in self.postings[token]:
                tf = self.frequencies[index][token]
                norm = tf + self.k1 * (
                    1 - self.b + self.b * self.lengths[index] / max(self.average, 1)
                )
                scores[index] = scores.get(index, 0) + idf * tf * (self.k1 + 1) / norm
        ranked = sorted(scores.items(), key=lambda pair: (-pair[1], self.ids[pair[0]]))[:limit]
        return [(self.ids[index], score) for index, score in ranked]

    def save(self, path: Path):
        path.write_text(
            json.dumps({"ids": self.ids, "documents": self.documents}), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["ids"], data["documents"])
