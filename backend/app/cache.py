"""Bounded TTL cache for complete, validated answers, including prompt context."""

import hashlib
import json
import threading
import time
from collections import OrderedDict


class AnswerCache:
    def __init__(self, max_size=128, ttl=600, *, clock=time.monotonic):
        self.max_size, self.ttl, self.clock = max_size, ttl, clock
        self.items = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            item = self.items.get(key)
            if item is None:
                return None
            expires, answer = item
            if expires <= self.clock():
                del self.items[key]
                return None
            self.items.move_to_end(key)
            return answer.model_copy(deep=True)

    def put(self, key, answer):
        if not self.max_size:
            return
        with self.lock:
            now = self.clock()
            for stale in [key for key, (expiry, _) in self.items.items() if expiry <= now]:
                del self.items[stale]
            self.items[key] = (now + self.ttl, answer.model_copy(deep=True))
            self.items.move_to_end(key)
            while len(self.items) > self.max_size:
                self.items.popitem(last=False)


def answer_key(request, settings, provider, *, rewritten=None, rewrite=True):
    payload = request.model_dump(by_alias=True, exclude={"request_id"})
    payload["question"] = " ".join(request.question.split())
    fields = (
        "embedding_model",
        "reranker_model",
        "quantize_models",
        "quantize_linears",
        "embedding_max_length",
        "reranker_max_length",
        "fusion_threshold",
        "bm25_threshold",
        "vector_threshold",
        "rerank_threshold",
        "agentic_good_score",
        "agentic_lower_score",
        "agentic_enabled",
        "max_llm_calls_per_question",
        "gemini_fast_model",
        "gemini_answer_model",
        "gemini_model",
        "max_context_chars",
    )
    fingerprint = {name: getattr(settings, name) for name in fields}
    digest = hashlib.sha256(
        json.dumps([payload, fingerprint, provider, rewrite], sort_keys=True).encode()
    ).hexdigest()
    return request.repo_id, " ".join((rewritten or request.question).split()), digest
