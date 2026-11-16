"""Measured agentic and follow-up ablations against immutable real source indexes."""

import hashlib
import json
import platform
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.generate.llm import ExtractiveLLM, get_llm
from app.index.vectors import Vectors, get_embedder
from app.models import AskRequest
from app.retrieve.hybrid import Retriever
from app.retrieve.reranker import Reranker
from app.service import AnswerService
from app.storage import Storage
from eval.metrics import aggregate, measure
from eval.run_eval import load_questions


def load_followups(sources, settings, *, require_reviewed=False):
    path = Path(__file__).parent / "questions" / "followups.jsonl"
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Follow-up IDs must be unique")
    for row in rows:
        if row["repo"] not in {"Seekr", "CodeNest", "DPTrace"}:
            raise ValueError("Unknown follow-up repository")
        AskRequest(repo_id="validation", question=row["question"], history=row["history"])
        load_questions(row["repo"], sources / row["repo"], settings, require_reviewed, rows=[row])
    return rows


def summarize(rows):
    groups = list(dict.fromkeys((row["suite"], row["mode"]) for row in rows))
    return [
        {
            "suite": suite,
            "mode": mode,
            "count": sum(row["suite"] == suite and row["mode"] == mode for row in rows),
            "metrics": aggregate(
                [row["metrics"] for row in rows if row["suite"] == suite and row["mode"] == mode]
            ),
        }
        for suite, mode in groups
    ]


def markdown_table(summaries):
    lines = [
        "| Suite | Mode | N | Recall@1 | Recall@5 | Recall@10 | MRR@10 "
        "| Avg measured ms | Avg LLM calls | Retry rate | Answer rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summaries:
        metrics = row["metrics"]
        values = [f"{metrics[key]:.4f}" for key in ("recall@1", "recall@5", "recall@10", "mrr")]
        lines.append(
            f"| {row['suite']} | {row['mode']} | {row['count']} | "
            + " | ".join(values)
            + f" | {metrics['latency_ms']:.2f} | {metrics['llm_calls']:.2f} "
            + f"| {metrics['retried']:.4f} | {metrics['answered']:.4f} |"
        )
    return "\n".join(lines)


def update_readme(path, report, output):
    start, end = "<!-- ASKREPO:ADVANCED:EVAL:START -->", "<!-- ASKREPO:ADVANCED:EVAL:END -->"
    baseline, agentic = report["summaries"][:2]
    improved = agentic["metrics"]["recall@10"] > baseline["metrics"]["recall@10"]
    conclusion = (
        "Agentic retrieval improved Recall@10 in this draft run; "
        "it remains opt-in pending reviewed labels."
        if improved
        else "Agentic retrieval did not improve Recall@10 in this run. It remains opt-in in the UI."
    )
    protocol = (
        "Paired modes share a freshly measured initial search. Latency is that measured stage "
        "plus each measured continuation; the initial model work is not executed twice."
        if report["shared_initial"]
        else "Modes execute independent complete answer pipelines; "
        "latency is measured server elapsed time."
    )
    section = (
        f"{start}\nActual run: `{output.name}`. "
        f"Ground truth: **{report['ground_truth_status']}**. "
        f"Provider: **{report['provider']}**.\n\n"
        f"{protocol}\n\n{markdown_table(report['summaries'])}\n\n{conclusion}\n\n"
    )
    section += (
        f"Follow-up reranking: **{report['followup_rerank']}** in both rewrite modes. "
        "Answer caching is disabled. LLM calls count actual provider attempts, "
        "including retries.\n\n"
    )
    if not report["gemini_evaluated"]:
        section += (
            "**No Gemini key was used.** Rewriting uses prior identifiers and agentic retries "
            "use ranking rules and lexical query variants. These are real CPU/no-key results, "
            "not measured Gemini rewrite/grader quality or free-tier Gemini cost.\n\n"
        )
    section += end
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    text = (
        pattern.sub(lambda _: section, text)
        if pattern.search(text)
        else text + "\n\n## Streaming, memory, and agentic evaluation\n\n" + section + "\n"
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def evaluate_advanced(args):
    settings = Settings()
    settings = settings.model_copy(
        update={"data_dir": args.advanced_data_dir or settings.data_dir, "answer_cache_size": 0}
    )
    if settings.lite_mode:
        raise ValueError(
            "This full reranker benchmark needs local CPU models; "
            "lightweight deployment remains supported"
        )
    if not settings.agentic_enabled:
        raise ValueError("Enable AGENTIC_ENABLED explicitly before benchmarking agentic retrieval")
    questions = {
        repo: load_questions(repo, args.sources / repo, settings, args.require_reviewed)
        for repo in args.repos
    }
    followups = [
        row
        for row in load_followups(args.sources, settings, require_reviewed=args.require_reviewed)
        if row["repo"] in args.repos
    ]
    if args.validate_only:
        print(
            f"Validated {sum(map(len, questions.values()))} standalone questions "
            f"and {len(followups)} follow-ups. Human review remains required."
        )
        return
    provider = ExtractiveLLM() if args.provider == "extractive" else get_llm(settings)
    pacing = (
        args.delay_seconds
        if args.delay_seconds is not None
        else (20 if provider.name != "extractive" else 0)
    )
    if pacing < 0:
        raise ValueError("Evaluation pacing cannot be negative")
    storage = Storage(settings.data_dir)
    implementation_hash = hashlib.sha256(
        b"".join(
            path.read_bytes()
            for path in sorted((Path(__file__).parent.parent / "app").rglob("*.py"))
        )
    ).hexdigest()
    embedder, reranker = get_embedder(settings), Reranker(settings)
    revisions, indexes = {}, {}
    for repo in args.repos:
        revision = subprocess.run(
            ["git", "-C", str(args.sources / repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        revisions[repo] = revision
        matches = [
            item
            for item in storage.repos()
            if item.repo_url.lower() == f"https://github.com/ShlokMaharwal/{repo}".lower()
            and storage.metadata(item.repo_id)["embedding_model"] == embedder.name
            and storage.metadata(item.repo_id)["revision"] == revision
        ]
        if not matches:
            raise ValueError(
                f"No compatible ready snapshot for {repo}; "
                "explicitly pre-index it with matching models first"
            )
        repo_id = matches[0].repo_id
        indexes[repo] = dict(
            storage.metadata(repo_id),
            chunks_sha256=hashlib.sha256(
                (storage.repo_dir(repo_id) / "chunks.json").read_bytes()
            ).hexdigest(),
        )
    retriever = Retriever(storage, Vectors(settings, embedder), settings, reranker)
    service = AnswerService(retriever, provider, settings)
    root = Path(__file__).parent
    output_dir = root / "results"
    output_dir.mkdir(exist_ok=True)
    journal = output_dir / f"advanced-{uuid4().hex}.partial.jsonl"
    rows = []
    started_run = time.perf_counter()

    def record(suite, mode, repo, question, response, initial_ms=0):
        ranked = [chunk.model_dump(exclude={"code"}) for chunk in response.chunks]
        metrics = dict(
            measure(ranked, question["relevant"], response.total_ms),
            llm_calls=response.llm_calls,
            retried=float(response.retried),
            answered=float(not response.not_found),
        )
        row = {
            "suite": suite,
            "mode": mode,
            "repo": repo,
            "id": question["id"],
            "ranked": ranked,
            "metrics": metrics,
            "initial_ms": initial_ms,
            "continuation_ms": response.total_ms - initial_ms,
            "rewritten_question": response.rewritten_question,
            "rewrite_mode": response.rewrite_mode,
            "answer": response.answer,
            "citations": [item.model_dump(by_alias=True) for item in response.citations],
        }
        rows.append(row)
        with journal.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"{len(rows):03d} {repo} {question['id']} / {mode} / "
            f"recall@10={metrics['recall@10']:.3f} calls={response.llm_calls} "
            f"retry={response.retried}",
            flush=True,
        )
        if pacing:
            time.sleep(pacing)

    try:
        embedder.encode(["Repository retrieval warmup"], query=True)
        reranker.score("Repository retrieval warmup", ["A function searches a repository."])
        for repo, group in questions.items():
            repo_id = indexes[repo]["id"]
            for question in group:
                print(f"Retrieving {repo} / {question['id']}", flush=True)
                initial, elapsed = None, 0
                if args.share_initial:
                    started = time.perf_counter()
                    initial = retriever.query(
                        repo_id, question["question"], 10, mode="hybrid", rerank=True
                    )
                    elapsed = (time.perf_counter() - started) * 1000
                for enabled, mode in (
                    (False, "single-pass hybrid + rerank"),
                    (True, "agentic retrieval"),
                ):
                    response = service.ask(
                        AskRequest(
                            repo_id=repo_id,
                            question=question["question"],
                            top_k=10,
                            agentic=enabled,
                            rerank=True,
                        ),
                        initial_result=initial,
                        initial_ms=elapsed,
                    )
                    record("standalone", mode, repo, question, response, elapsed)
        for question in followups:
            repo = question["repo"]
            for rewrite, mode in ((False, "rewrite off"), (True, "rewrite on")):
                response = service.ask(
                    AskRequest(
                        repo_id=indexes[repo]["id"],
                        question=question["question"],
                        history=question["history"],
                        top_k=10,
                        agentic=False,
                        rerank=args.followup_rerank,
                    ),
                    rewrite=rewrite,
                )
                record("follow-up", mode, repo, question, response)
    finally:
        retriever.close()
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    report = {
        "created_at": now.isoformat(),
        "provider": provider.name,
        "gemini_evaluated": provider.name != "extractive",
        "ground_truth_status": "reviewed"
        if all(row.get("reviewed") for group in questions.values() for row in group)
        and all(row.get("reviewed") for row in followups)
        else "draft—human review required",
        "shared_initial": args.share_initial,
        "latency_protocol": "measured initial stage + measured continuation"
        if args.share_initial
        else "independent complete pipelines",
        "wall_elapsed_ms": (time.perf_counter() - started_run) * 1000,
        "pacing_seconds": pacing,
        "followup_rerank": args.followup_rerank,
        "answer_cache_size": 0,
        "embedding_model": embedder.name,
        "reranker_model": settings.reranker_model,
        "device": "cpu",
        "model_profile": {
            key: getattr(settings, key)
            for key in (
                "quantize_models",
                "quantize_linears",
                "model_threads",
                "embedding_batch_size",
                "reranker_batch_size",
                "embedding_max_length",
                "reranker_max_length",
                "max_llm_calls_per_question",
                "agentic_good_score",
                "agentic_lower_score",
            )
        },
        "fast_model": settings.gemini_fast_model,
        "answer_model": settings.gemini_answer_model or settings.gemini_model,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {
            name: version(name)
            for name in ("torch", "sentence-transformers", "qdrant-client", "google-genai")
        },
        "implementation_sha256": implementation_hash,
        "question_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "questions").glob("*.jsonl"))
        },
        "revisions": revisions,
        "data_directory": str(settings.data_dir.resolve()),
        "index_snapshot": json.loads(
            (settings.data_dir / "snapshot.json").read_text(encoding="utf-8")
        )
        if (settings.data_dir / "snapshot.json").exists()
        else None,
        "indexes": indexes,
        "questions": questions,
        "followups": followups,
        "summaries": summarize(rows),
        "rows": rows,
    }
    expected = sum(map(len, questions.values())) * 2 + len(followups) * 2
    assert len(rows) == expected and all(
        row["metrics"]["llm_calls"] <= settings.max_llm_calls_per_question for row in rows
    )
    output = output_dir / f"{now.date()}-advanced.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(markdown_table(report["summaries"]))
    print("Follow-up cases per repo:", dict(Counter(row["repo"] for row in followups)))
    update_readme(args.readme, report, output)
    journal.unlink()
    print(f"Saved {output}")
