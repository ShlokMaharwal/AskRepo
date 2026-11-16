"""Shared answer pipeline for JSON and cancellable streaming clients."""

import asyncio
import re
import threading
from contextlib import aclosing, suppress
from time import perf_counter

from app.cache import AnswerCache, answer_key
from app.config import Settings
from app.errors import DemoLimitError, IndexConfigurationError
from app.generate.client import CallBudget, LLMClient, QuestionBudgets
from app.generate.llm import LLM
from app.generate.prompt import budget_context, validate_citations
from app.models import AskRequest, AskResponse, Latency
from app.retrieve.agentic import RetrievalPlanner
from app.retrieve.hybrid import Retriever
from app.streaming import StreamEvent

NOT_FOUND = (
    "This repository does not appear to contain enough relevant evidence to answer that question."
)
INSUFFICIENT = "The retrieved context was insufficient to produce a cited answer."
UNAVAILABLE = "Answer service unavailable. Check provider configuration and model availability."


class AnswerService:
    def __init__(self, retriever: Retriever, llm: LLM, settings: Settings):
        self.retriever, self.llm, self.settings = retriever, llm, settings
        self.client = LLMClient(llm, settings)
        self.planner = RetrievalPlanner(retriever, self.client, settings)
        self.cache = AnswerCache(settings.answer_cache_size, settings.answer_cache_ttl_seconds)
        self.budgets = QuestionBudgets()

    def ask(
        self, request: AskRequest, *, ip="local", rewrite=True, initial_result=None, initial_ms=0
    ) -> AskResponse:
        async def collect():
            response = AskResponse(answer="", not_found=False)
            async for event in self.events(
                request,
                streaming=False,
                ip=ip,
                rewrite=rewrite,
                initial_result=initial_result,
                initial_ms=initial_ms,
            ):
                if event.event == "chunks":
                    response.chunks = event.data
                elif event.event == "token":
                    response.answer += event.data["text"]
                elif event.event == "answer_clean":
                    response.answer = event.data["answer"]
                elif event.event == "citations":
                    response.citations = event.data
                elif event.event == "done":
                    response = AskResponse.model_validate(
                        dict(response.model_dump(by_alias=True), **event.data)
                    )
            return response

        return asyncio.run(collect())

    async def stream(self, request: AskRequest, *, ip="local"):
        try:
            async with aclosing(self.events(request, streaming=True, ip=ip)) as events:
                async for event in events:
                    yield event
        except DemoLimitError as error:
            yield StreamEvent("answer_clean", {"answer": ""})
            yield StreamEvent(
                "error", {"code": "demo_limit", "message": str(error), "retryAfter": 60}
            )
        except IndexConfigurationError:
            yield StreamEvent(
                "error", {"message": "Index configuration changed; re-index this repository"}
            )
        except Exception:
            yield StreamEvent("answer_clean", {"answer": ""})
            yield StreamEvent("error", {"message": UNAVAILABLE})

    async def events(
        self,
        request: AskRequest,
        *,
        streaming: bool,
        ip="local",
        rewrite=True,
        initial_result=None,
        initial_ms=0,
    ):
        if initial_result is not None and self.settings.answer_cache_size:
            raise ValueError("Paired evaluation requires answer caching disabled")
        started_total = perf_counter()
        key = answer_key(request, self.settings, self.llm.name, rewrite=rewrite)
        budget_key = (ip, request.request_id, key)
        budget = (
            self.budgets.get(budget_key, self.settings.max_llm_calls_per_question)
            if request.request_id
            else CallBudget(self.settings.max_llm_calls_per_question)
        )
        cached = self.cache.get(key) if self.settings.answer_cache_size else None
        if cached is not None:
            yield StreamEvent("status", {"stage": "retrieving", "message": "Using a cached answer"})
            yield StreamEvent("chunks", cached.chunks)
            for text in re.findall(r"\S+\s*|\s+", cached.answer):
                await asyncio.sleep(0)
                yield StreamEvent("token", {"text": text})
            yield StreamEvent("citations", cached.citations)
            metadata = cached.model_dump(by_alias=True, exclude={"answer", "chunks", "citations"})
            yield StreamEvent(
                "done",
                dict(
                    metadata,
                    cached=True,
                    llmCalls=budget.used,
                    latencyMs={"retrieve": 0, "rerank": 0, "generate": 0},
                    totalMs=(perf_counter() - started_total) * 1000,
                ),
            )
            return
        cancelled = threading.Event()
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        history = [message.model_dump() for message in request.history]

        def on_stage(stage, message):
            if not cancelled.is_set():
                loop.call_soon_threadsafe(
                    queue.put_nowait, StreamEvent("status", {"stage": stage, "message": message})
                )

        async def retrieve():
            try:
                trace = await self.planner.run(
                    request,
                    budget,
                    on_stage=on_stage,
                    cancelled=cancelled,
                    ip=ip,
                    rewrite=rewrite,
                    on_chunks=lambda chunks: queue.put_nowait(StreamEvent("chunks", chunks)),
                    initial_result=initial_result,
                )
                await queue.put(trace)
            except Exception as error:
                await queue.put(error)

        task = None
        try:
            task = asyncio.create_task(retrieve())
            while True:
                item = await queue.get()
                if isinstance(item, StreamEvent):
                    yield item
                elif isinstance(item, Exception):
                    raise item
                else:
                    trace = item
                    result = trace.result
                    break
            latency = Latency(retrieve=result.retrieve_ms, rerank=result.rerank_ms)
            mode = "none"
            not_found = result.low_confidence
            if not_found:
                raw = answer = NOT_FOUND + (
                    " Try naming a specific file, function, or behavior." if trace.retried else ""
                )
                citations = []
                yield StreamEvent("token", {"text": answer})
            else:
                sources, context = budget_context(
                    result.sources, result.context, self.settings.max_context_chars
                )
                yield StreamEvent(
                    "status",
                    {"stage": "generating", "message": "Answering from the retrieved code"},
                )
                started = perf_counter()
                mode = self.llm.name
                raw = ""
                arguments = (request.question, sources, context)
                kwargs = {"history": history} if history else {}
                if streaming:
                    async with aclosing(
                        self.client.stream(*arguments, budget=budget, ip=ip, **kwargs)
                    ) as pieces:
                        async for piece in pieces:
                            raw += piece
                            if len(raw) > 50000:
                                raise ValueError("Answer exceeds the response limit")
                            yield StreamEvent("token", {"text": piece})
                else:
                    raw = await self.client.call(
                        "generate", *arguments, budget=budget, ip=ip, **kwargs
                    )
                    yield StreamEvent("token", {"text": raw})
                answer, citations = validate_citations(raw, sources)
                if not citations:
                    answer, not_found = INSUFFICIENT, True
                latency.generate = (perf_counter() - started) * 1000
            if answer != raw:
                yield StreamEvent("answer_clean", {"answer": answer})
            yield StreamEvent("citations", citations)
            metadata = {
                "notFound": not_found,
                "latencyMs": latency.model_dump(by_alias=True),
                "llmCalls": budget.used,
                "generationMode": mode,
                "rerankApplied": result.rerank_applied,
                "rewrittenQuestion": trace.question,
                "rewriteMode": trace.rewrite_mode,
                "agenticUsed": trace.agentic_used,
                "retried": trace.retried,
                "totalMs": (perf_counter() - started_total) * 1000 + initial_ms,
                "cached": False,
            }
            if self.settings.answer_cache_size:
                response = AskResponse(
                    answer=answer, citations=citations, chunks=result.chunks, **metadata
                )
                self.cache.put(key, response)
                self.cache.put(
                    answer_key(
                        request,
                        self.settings,
                        self.llm.name,
                        rewritten=trace.question,
                        rewrite=rewrite,
                    ),
                    response,
                )
            yield StreamEvent("done", metadata)
        finally:
            cancelled.set()
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
