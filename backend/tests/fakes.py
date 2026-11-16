import asyncio
import math
import re


class FakeEmbedder:
    name = "test-semantic-v1"
    words = ["frontier", "redis", "crawl", "rank", "score", "snapshot", "disk", "trie"]

    def encode(self, texts, *, query=False):
        vectors = []
        for text in texts:
            values = [float(text.lower().count(word)) for word in self.words] + [0.1]
            norm = math.sqrt(sum(value * value for value in values))
            vectors.append([value / norm for value in values])
        return vectors


class FakeReranker:
    def score(self, question, documents):
        return [0.95 if "frontier" in text.lower() else 0.1 for text in documents]


class FakeLLM:
    name = "test-stub"
    calls = 0

    def generate(self, question, sources, context, history=None):
        self.calls += 1
        source = sources[0]
        return (
            f"The implementation is `{source.symbol_name}`. "
            f"[{source.path}:{source.start_line}-{source.end_line}]"
        )

    async def rewrite(self, question, history):
        return "Where is the redis frontier called?"

    async def grade(self, question, chunks):
        return '{"sufficient":true,"missing":"","alternative_queries":[]}'

    async def stream(self, question, sources, context, history=None):
        for piece in re.findall(r"\S+\s*", self.generate(question, sources, context, history)):
            await asyncio.sleep(0)
            yield piece
