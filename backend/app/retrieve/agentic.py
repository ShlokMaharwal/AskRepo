"""One bounded retrieval retry, with optional inexpensive model controls."""

import asyncio
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field

from app.errors import WorkCancelled
from app.memory import contextual_rewrite, normalize_rewrite, should_rewrite
from app.retrieve.hybrid import Retrieval


@dataclass
class Grade:
    sufficient: bool = True
    missing: str = ""
    alternative_queries: list[str] = field(default_factory=list)


def parse_grade(text):
    try:
        if isinstance(text, str):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
            text = json.loads(text)
        if not isinstance(text, dict) or type(text.get("sufficient")) is not bool:
            return Grade()
        raw = text.get("alternative_queries", [])
        queries = (
            list(
                dict.fromkeys(
                    value.strip()
                    for value in raw
                    if isinstance(value, str) and 0 < len(value.strip()) <= 500
                )
            )[:2]
            if isinstance(raw, list)
            else []
        )
        missing = text.get("missing", "")
        return Grade(text["sufficient"], missing[:500] if isinstance(missing, str) else "", queries)
    except (ValueError, TypeError):
        # Invalid grader output must not trigger additional paid calls or retries.
        return Grade()


def good_results(result, settings):
    return bool(
        not result.low_confidence
        and result.chunks
        and result.chunks[0].score >= settings.agentic_good_score
        and sum(chunk.score >= settings.agentic_lower_score for chunk in result.chunks) >= 2
    )


def alternative_queries(question, proposed):
    output = []
    identifiers = re.findall(r"`([^`]+)`|\b([A-Za-z_]\w*(?:[./:]\w+)+)\b", question)
    names = list(dict.fromkeys(part for pair in identifiers for part in pair if part))
    words = [
        word
        for word in re.findall(r"[A-Za-z_][\w.-]*", question)
        if word.lower()
        not in {
            "how",
            "does",
            "where",
            "what",
            "the",
            "this",
            "that",
            "and",
            "about",
            "called",
            "context",
            "which",
            "are",
            "for",
            "with",
            "can",
            "from",
        }
    ]
    for query in [*proposed, " ".join(names or words), " ".join(words) + " implementation"]:
        query = " ".join(query.split())[:500]
        if query and query != question and query not in output:
            output.append(query)
        if len(output) == 2:
            break
    return output


@dataclass
class RetrievalTrace:
    result: Retrieval
    question: str
    rewrite_mode: str = "none"
    agentic_used: bool = False
    retried: bool = False


class RetrievalPlanner:
    def __init__(self, retriever, client, settings):
        self.retriever, self.client, self.settings = retriever, client, settings

    async def run(
        self,
        request,
        budget,
        *,
        on_stage,
        cancelled,
        ip="local",
        rewrite=True,
        on_chunks=None,
        initial_result=None,
    ):
        question, rewrite_mode = request.question, "none"
        history = [message.model_dump() for message in request.history]
        if rewrite and should_rewrite(question, request.history):
            on_stage("rewriting", "Resolving the follow-up question")
            if self.client.provider.name == "extractive" or not budget.available(reserve=1):
                question = contextual_rewrite(question, request.history)
                rewrite_mode = "context"
            else:
                question = normalize_rewrite(
                    await self.client.call(
                        "rewrite", question, history, budget=budget, reserve=1, ip=ip
                    ),
                    request.question,
                )
                rewrite_mode = "llm"
        on_stage(
            "retrieving",
            "Searching your repository"
            if question == request.question
            else f"Searching for: {question}",
        )
        mode = request.retrieval_mode or ("hybrid" if request.hybrid else "bm25")
        if initial_result is not None:
            if question != request.question:
                raise ValueError("Cannot share an initial retrieval after rewriting")
            result = deepcopy(initial_result)
        else:
            result = await asyncio.to_thread(
                self.retriever.query,
                request.repo_id,
                question,
                request.top_k,
                mode=mode,
                rerank=request.rerank,
                on_stage=on_stage,
                cancelled=cancelled,
            )
        trace = RetrievalTrace(
            result, question, rewrite_mode, bool(request.agentic and self.settings.agentic_enabled)
        )
        if on_chunks is not None:
            on_chunks(result.chunks)
        if not trace.agentic_used or good_results(result, self.settings):
            return trace
        if cancelled.is_set():
            raise WorkCancelled()
        grade = Grade(False)
        if self.client.provider.name != "extractive" and budget.available(reserve=1):
            grade = parse_grade(
                await self.client.call(
                    "grade",
                    question,
                    [chunk.model_dump(by_alias=True) for chunk in result.chunks[:8]],
                    budget=budget,
                    reserve=1,
                    ip=ip,
                )
            )
        if grade.sufficient:
            return trace
        queries = alternative_queries(question, grade.alternative_queries)
        if queries:
            on_stage("retrying", "Trying alternative identifier and code searches")
            trace.result = await asyncio.to_thread(
                self.retriever.retry,
                request.repo_id,
                question,
                queries,
                result,
                request.top_k,
                mode=mode,
                rerank=request.rerank,
                on_stage=on_stage,
                cancelled=cancelled,
            )
            trace.retried = True
            if on_chunks is not None:
                on_chunks(trace.result.chunks)
        if not good_results(trace.result, self.settings):
            trace.result.low_confidence = True
        return trace
