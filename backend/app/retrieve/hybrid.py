import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter

from app.config import Settings
from app.errors import IndexConfigurationError, WorkCancelled
from app.index.bm25 import BM25
from app.index.vectors import Vectors
from app.ingest.chunker import Chunk
from app.models import RetrievedChunk
from app.storage import Storage


def rrf(rankings: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen = set()
        for rank, (identifier, _) in enumerate(ranking, 1):
            if identifier not in seen:
                scores[identifier] = scores.get(identifier, 0) + 1 / (k + rank)
                seen.add(identifier)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


@dataclass
class Retrieval:
    chunks: list[RetrievedChunk]
    sources: list[Chunk]
    context: list[Chunk]
    retrieve_ms: float
    rerank_ms: float = 0
    low_confidence: bool = False
    rerank_applied: bool = False
    candidates: list[tuple[str, float]] = field(default_factory=list)


class Retriever:
    def __init__(self, storage: Storage, vectors: Vectors, settings: Settings, reranker=None):
        self.storage, self.vectors, self.settings = storage, vectors, settings
        self.reranker = reranker
        self.cache: dict[str, tuple[list[Chunk], BM25]] = {}
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="askrepo-retrieve")

    def build(self, repo_id: str, chunks: list[Chunk]) -> str:
        keyword = BM25.build(chunks)
        keyword.save(self.storage.repo_dir(repo_id) / "bm25.json")
        self.vectors.build(repo_id, chunks)
        with self.lock:
            self.cache[repo_id] = (chunks, keyword)
            while len(self.cache) > (1 if self.settings.lite_mode else 4):
                del self.cache[next(iter(self.cache))]
        return self.vectors.embedder.name

    def load(self, repo_id: str):
        metadata = self.storage.metadata(repo_id)
        if metadata["status"] != "ready":
            raise ValueError("Repository is not ready; wait for indexing to finish")
        if metadata["embedding_model"] != self.vectors.embedder.name:
            raise IndexConfigurationError(
                "Embedding model differs from this index; re-index the repository"
            )
        with self.lock:
            if repo_id not in self.cache:
                self.cache[repo_id] = (
                    self.storage.chunks(repo_id),
                    BM25.load(self.storage.repo_dir(repo_id) / "bm25.json"),
                )
                # Bound RAM for long-lived, many-repository development sessions.
                if len(self.cache) > (1 if self.settings.lite_mode else 4):
                    del self.cache[next(iter(self.cache))]
            return self.cache[repo_id]

    def query(
        self,
        repo_id: str,
        question: str,
        top_k=8,
        mode="hybrid",
        rerank=False,
        *,
        on_stage=None,
        cancelled=None,
    ) -> Retrieval:
        def checkpoint():
            if cancelled is not None and cancelled.is_set():
                raise WorkCancelled()

        checkpoint()
        started = perf_counter()
        chunks, keyword = self.load(repo_id)
        by_id = {chunk.id: chunk for chunk in chunks}
        if mode == "hybrid":
            sparse = self.pool.submit(keyword.search, question, 50)
            dense = self.pool.submit(self.vectors.search, repo_id, question, 50)
            ranking = rrf([sparse.result(), dense.result()])
            ranking = [(identifier, min(1.0, score / (2 / 61))) for identifier, score in ranking]
            threshold = self.settings.fusion_threshold
        elif mode == "bm25":
            ranking = [
                (identifier, 1 - math.exp(-score / 8))
                for identifier, score in keyword.search(question, 50)
            ]
            threshold = self.settings.bm25_threshold
        elif mode == "vector":
            ranking = [
                (identifier, max(0.0, min(1.0, score)))
                for identifier, score in self.vectors.search(repo_id, question, 50)
            ]
            threshold = self.settings.vector_threshold
        else:
            raise ValueError("Unknown retrieval mode")
        checkpoint()
        retrieve_ms = (perf_counter() - started) * 1000
        return self.finish(
            question,
            chunks,
            by_id,
            ranking,
            top_k,
            rerank,
            mode,
            threshold,
            retrieve_ms,
            on_stage=on_stage,
            cancelled=cancelled,
        )

    def finish(
        self,
        question,
        chunks,
        by_id,
        ranking,
        top_k,
        rerank,
        method,
        threshold,
        retrieve_ms,
        *,
        on_stage=None,
        cancelled=None,
        previous_rerank_ms=0,
    ):
        def checkpoint():
            if cancelled is not None and cancelled.is_set():
                raise WorkCancelled()

        checkpoint()
        candidates_before_reranking = ranking[:50]
        rerank_ms = 0.0
        applied = bool(
            rerank and ranking and self.reranker is not None and not self.settings.lite_mode
        )
        if applied and ranking:
            if on_stage is not None:
                on_stage("reranking", "Reranking the strongest code matches")
            checkpoint()
            started = perf_counter()
            candidates = ranking[:20]
            scores = self.reranker.score(
                question, [by_id[identifier].text for identifier, _ in candidates]
            )
            checkpoint()
            ranking = sorted(
                zip([identifier for identifier, _ in candidates], scores, strict=True),
                key=lambda item: (-item[1], item[0]),
            )
            rerank_ms = (perf_counter() - started) * 1000
            threshold, method = self.settings.rerank_threshold, "reranked"
        final = ranking[:top_k]
        sources = [by_id[identifier] for identifier, _ in final]
        context = expand_neighbors(sources, chunks)
        return Retrieval(
            chunks=[
                RetrievedChunk(
                    path=by_id[identifier].path,
                    start_line=by_id[identifier].start_line,
                    end_line=by_id[identifier].end_line,
                    code=by_id[identifier].code,
                    score=score,
                    method=method,
                )
                for identifier, score in final
            ],
            sources=sources,
            context=context,
            retrieve_ms=retrieve_ms,
            rerank_ms=rerank_ms + previous_rerank_ms,
            low_confidence=not final or final[0][1] < threshold,
            rerank_applied=applied,
            candidates=candidates_before_reranking,
        )

    def retry(
        self,
        repo_id,
        question,
        queries,
        initial,
        top_k=8,
        *,
        mode="hybrid",
        rerank=False,
        on_stage=None,
        cancelled=None,
    ):
        started = perf_counter()
        rankings = [initial.candidates]
        for query in queries[:2]:
            if cancelled is not None and cancelled.is_set():
                raise WorkCancelled()
            rankings.append(
                self.query(
                    repo_id, query, 50, mode=mode, rerank=False, cancelled=cancelled
                ).candidates
            )
        ranking = [
            (identifier, min(1.0, score / (len(rankings) / 61)))
            for identifier, score in rrf(rankings)
        ]
        chunks, _ = self.load(repo_id)
        return self.finish(
            question,
            chunks,
            {chunk.id: chunk for chunk in chunks},
            ranking,
            top_k,
            rerank,
            "hybrid",
            self.settings.fusion_threshold,
            initial.retrieve_ms + (perf_counter() - started) * 1000,
            on_stage=on_stage,
            cancelled=cancelled,
            previous_rerank_ms=initial.rerank_ms,
        )

    def close(self):
        self.pool.shutdown(wait=True)
        self.vectors.close()


def expand_neighbors(selected: list[Chunk], all_chunks: list[Chunk]) -> list[Chunk]:
    chosen = {chunk.id for chunk in selected}
    context = []
    for chunk in selected:
        relevant = [
            candidate
            for candidate in all_chunks
            if candidate.path == chunk.path
            and (
                (candidate.kind == "class_header" and candidate.symbol_name == chunk.parent_symbol)
                or candidate.kind == "imports"
            )
        ]
        for candidate in relevant:
            if candidate.id not in chosen:
                chosen.add(candidate.id)
                context.append(candidate)
    return context
