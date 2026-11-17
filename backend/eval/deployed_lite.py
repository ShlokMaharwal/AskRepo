"""Measure actual Gemini embeddings with fresh local Qdrant snapshots and no reranker."""

import hashlib
import json
import platform
import re
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import mean
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.config import Settings
from app.index.vectors import GeminiEmbedder, Vectors
from app.ingest.chunker import chunk_file
from app.ingest.clone import source_files
from app.retrieve.hybrid import Retriever
from app.storage import Storage
from eval.answer_quality import audit_samples
from eval.diagnose_lite import context_variant, diagnostic, distribution, render
from eval.lite_embeddings import MeasuredEmbeddings
from eval.metrics import aggregate, measure
from eval.run_eval import load_questions

MODES = ("bm25", "vector", "hybrid")
VARIANTS = ("fixed", "ast", "ast-context")


def fingerprint():
    root = Path(__file__).parents[1]
    return hashlib.sha256(
        b"".join(path.read_bytes() for path in sorted((root / "app").rglob("*.py")))
    ).hexdigest()


def public_configuration(settings):
    return settings.model_dump(
        mode="json", exclude={"gemini_api_key", "qdrant_api_key", "admin_token"}
    )


def table(summaries):
    lines = [
        "| Chunking | Retrieval | N | Recall@1 | Recall@5 | Recall@10 | MRR@10 | Warm query ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summaries:
        m = row["metrics"]
        lines.append(
            f"| {row['chunking']} | {row['retrieval']} | {row['n']} | "
            + " | ".join(f"{m[key]:.4f}" for key in ["recall@1", "recall@5", "recall@10", "mrr"])
            + f" | {m['latency_ms']:.2f} |"
        )
    return "\n".join(lines)


def replace_section(path, marker, body):
    start, end = f"<!-- {marker}:START -->", f"<!-- {marker}:END -->"
    text = path.read_text(encoding="utf-8")
    section = start + "\n" + body + "\n" + end
    if start in text:
        text = re.sub(
            re.escape(start) + ".*?" + re.escape(end), lambda _: section, text, flags=re.S
        )
    else:
        text += "\n\n## Deployed-lite measurements\n\n" + section + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def summarize(rows):
    return [
        {
            "chunking": variant,
            "retrieval": mode,
            "n": len(selected),
            "metrics": aggregate([row["metrics"] for row in selected]),
        }
        for variant in VARIANTS
        for mode in MODES
        if (
            selected := [
                row for row in rows if row["chunking"] == variant and row["retrieval"] == mode
            ]
        )
    ]


def evaluate_deployed_lite(args):
    if set(args.repos) != {"Seekr", "CodeNest", "DPTrace"}:
        raise ValueError("The deployed-lite profile evaluates all three demo repositories")
    settings = Settings().model_copy(
        update={
            "lite_mode": True,
            "qdrant_url": None,
            "qdrant_api_key": None,
            "bootstrap_demos": False,
            "agentic_enabled": False,
            "answer_cache_size": 0,
        }
    )
    if not settings.gemini_api_key:
        raise ValueError(
            "A Gemini key is required for deployed-lite; no offline substitute is used"
        )
    questions = {
        repo: load_questions(repo, args.sources / repo, settings, args.require_reviewed)
        for repo in args.repos
    }
    if args.validate_only:
        print(f"Validated {sum(map(len, questions.values()))} draft questions for deployed-lite")
        return
    started = perf_counter()
    output = (
        Path(__file__).parent
        / "results"
        / (datetime.now(UTC).date().isoformat() + "-deployed-lite.json")
    )
    if output.exists():
        raise ValueError("A completed report already exists; do not overwrite measured evidence")
    implementation = fingerprint()
    revisions = {
        repo: subprocess.check_output(
            ["git", "-C", str(args.sources / repo), "rev-parse", "HEAD"], text=True
        ).strip()
        for repo in args.repos
    }
    root = args.data_dir / "deployed-lite"
    root.mkdir(parents=True, exist_ok=True)
    signature = hashlib.sha256(
        json.dumps(
            [
                revisions,
                settings.gemini_embedding_model,
                settings.gemini_answer_model,
                settings.gemini_fast_model,
                settings.max_chunk_chars,
                settings.max_context_chars,
            ]
        ).encode()
    ).hexdigest()[:16]
    provider = GeminiEmbedder(settings)
    measured = MeasuredEmbeddings(provider, root / "embedding-cache")
    query_started = perf_counter()
    query_texts = [q["question"] for repo in args.repos for q in questions[repo]]
    for offset in range(0, len(query_texts), settings.gemini_embedding_batch_size):
        print(f"Gemini query embedding batch starting at {offset + 1}/45", flush=True)
        measured.encode(
            query_texts[offset : offset + settings.gemini_embedding_batch_size], query=True
        )
    query_prepare_ms = (perf_counter() - query_started) * 1000
    rows, indexes, ids = [], [], {}
    for variant in VARIANTS:
        config = settings.model_copy(update={"data_dir": root / variant})
        storage = Storage(config.data_dir)
        retriever = Retriever(storage, Vectors(config, measured), config)
        try:
            for repo in args.repos:
                repo_id = uuid5(
                    NAMESPACE_URL, f"askrepo:eval:lite:{repo}:{revisions[repo]}:{signature}"
                ).hex
                ids[(variant, repo)] = repo_id
                files = source_files(args.sources / repo, config)
                chunks = [
                    chunk
                    for path, code in files
                    for chunk in chunk_file(
                        repo_id,
                        path,
                        code,
                        "fixed" if variant == "fixed" else "ast",
                        config.max_chunk_chars,
                    )
                ]
                if variant == "ast-context":
                    chunks = context_variant(chunks)
                print(f"Indexing {variant} / {repo}: {len(chunks)} chunks", flush=True)
                storage.save(
                    repo_id,
                    f"https://github.com/ShlokMaharwal/{repo}",
                    files,
                    chunks,
                    revisions[repo],
                )
                model = retriever.build(repo_id, chunks)
                storage.ready(repo_id, model)
                indexes.append(
                    {
                        "repo": repo,
                        "repo_id": repo_id,
                        "chunking": variant,
                        "distribution": distribution(chunks),
                        "source_revision": revisions[repo],
                        "files": len(files),
                    }
                )
                for mode in MODES:
                    print(f"Measuring {variant} / {repo} / {mode}", flush=True)
                    for question in questions[repo]:
                        result = retriever.query(
                            repo_id, question["question"], 10, mode=mode, rerank=False
                        )
                        ranked = [
                            dict(
                                path=chunk.path,
                                start_line=chunk.start_line,
                                end_line=chunk.end_line,
                                symbol_name=chunk.symbol_name,
                                parent_symbol=chunk.parent_symbol,
                                kind=chunk.kind,
                                score=hit.score,
                                code_chars=len(chunk.code),
                                embedding_chars=len(chunk.text),
                            )
                            for chunk, hit in zip(result.sources, result.chunks, strict=True)
                        ]
                        rows.append(
                            {
                                "repo": repo,
                                "id": question["id"],
                                "question": question["question"],
                                "relevant": question["relevant"],
                                "chunking": variant,
                                "retrieval": mode,
                                "ranked": ranked,
                                "metrics": measure(
                                    ranked, question["relevant"], result.retrieve_ms
                                ),
                            }
                        )
        finally:
            retriever.close()
    summaries = summarize(rows)
    config = settings.model_copy(update={"data_dir": root / "ast"})
    storage = Storage(config.data_dir)
    retriever = Retriever(storage, Vectors(config, measured), config)
    try:
        quality = audit_samples(
            config,
            retriever,
            storage,
            {repo: ids[("ast", repo)] for repo in args.repos},
            questions,
            delay=20 if args.delay_seconds is None else args.delay_seconds,
            output=root / (signature + "-quality.json"),
        )
    finally:
        retriever.close()
        provider.close()
    checks = [check for row in quality for check in row["citation_checks"]]
    scores = [row["automated_rubric"]["score"] for row in quality if row["automated_rubric"]]
    quality_summary = {
        "sample_size": len(quality),
        "seed": 20261117,
        "answered": sum(not row["not_found"] for row in quality),
        "citations_checked": len(checks),
        "citations_valid": sum(checks),
        "validity_rate": sum(checks) / len(checks) if checks else None,
        "automated_rubric_scored": len(scores),
        "automated_rubric_mean_0_to_4": mean(scores) if scores else None,
        "answer_llm_calls": sum(row["answer_llm_calls"] for row in quality),
        "judge_llm_calls": sum(row["judge_llm_calls"] for row in quality),
        "note": "Same-family automated Gemini rubric, not human-validated faithfulness; "
        "abstentions and failed judge outputs have no invented score.",
    }
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "profile": "deployed-lite",
        "status": "complete",
        "ground_truth_status": "draft—human review required",
        "embedding_model": measured.name,
        "dimensions": 768,
        "reranker": None,
        "answer_model": settings.gemini_answer_model or settings.gemini_model,
        "judge_model": settings.gemini_fast_model,
        "source_revisions": revisions,
        "source_directory": str(args.sources.resolve()),
        "implementation_sha256": implementation,
        "question_sha256": {
            repo: hashlib.sha256(
                (Path(__file__).parent / "questions" / (repo.lower() + ".jsonl")).read_bytes()
            ).hexdigest()
            for repo in args.repos
        },
        "config": {
            "chunk_chars": settings.max_chunk_chars,
            "context_variant_chars": 800,
            "context_budget": settings.max_context_chars,
            "top_k": 10,
            "vector_backend": "fresh local Qdrant snapshots; no production collections",
            "embedding_rpm": settings.gemini_embedding_rpm,
            "embedding_batch": settings.gemini_embedding_batch_size,
            "answer_cache_size": 0,
            "agentic": False,
        },
        "full_configuration": public_configuration(settings.model_copy(update={"data_dir": root})),
        "latency_protocol": "Warm content-addressed query embeddings shared across modes/variants. "
        "Reported retrieval milliseconds exclude Gemini query preparation and quota waits; "
        "these are local diagnostic timings, not hosted end-to-end latency.",
        "embedding_cache": "Exact model/task/text hashes only; newly encoded texts saved for "
        "resumption. No BGE vectors or generated answers reused.",
        "query_preparation_ms": query_prepare_ms,
        "embedding_provider_attempts_this_process": provider.requests,
        "new_embedding_texts_this_process": measured.new_texts,
        "embedding_cache_hits": measured.cache_hits,
        "wall_elapsed_ms": (perf_counter() - started) * 1000,
        "python": platform.python_version(),
        "versions": {
            name: version(name)
            for name in ["google-genai", "qdrant-client", "tree-sitter-language-pack"]
        },
        "indexes": indexes,
        "questions": questions,
        "summaries": summaries,
        "rows": rows,
        "answer_quality_summary": quality_summary,
        "answer_quality": quality,
    }
    output = (
        Path(__file__).parent
        / "results"
        / (datetime.now(UTC).date().isoformat() + "-deployed-lite.json")
    )
    if output.exists():
        raise ValueError("A completed report already exists; do not overwrite measured evidence")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    docs = Path(__file__).parents[2] / "docs"
    (docs / "AST_DIAGNOSTICS.md").write_text(render(report), encoding="utf-8")
    indexed = {(row["chunking"], row["retrieval"]): row["metrics"] for row in summaries}
    fixed, ast, context = (indexed[(v, "hybrid")] for v in VARIANTS)
    conclusion = (
        "AST underperformed fixed windows in hybrid Recall@10."
        if ast["recall@10"] < fixed["recall@10"]
        else "AST did not underperform fixed windows in hybrid Recall@10 in this run."
    )
    experiment = (
        "The context-prefix experiment improved hybrid Recall@10."
        if context["recall@10"] > ast["recall@10"]
        else "The context-prefix experiment did not improve hybrid Recall@10; it was not promoted."
    )
    body = (
        f"Measured {report['created_at']}: **deployed-lite**, Gemini `{measured.name}`, "
        f"768 dimensions, no reranker, fresh local Qdrant. Labels remain **drafts**.\n\n"
        + table(summaries)
        + "\n\n"
        + conclusion
        + " "
        + experiment
        + "\n\n"
        + "Warm-query timings exclude embedding preparation and do not represent Render latency. "
        + f"The {len(quality)}-question Gemini answer audit checked {len(checks)} citations "
        + f"({sum(checks)} structurally valid). Automated rubric scored {len(scores)} answers; "
        + f"mean on a 0–4 scale: {quality_summary['automated_rubric_mean_0_to_4']}. "
        + "This is automated evidence, not human validation.\n\n"
        + f"[Full report](../backend/eval/results/{output.name}) · "
        + "[AST diagnostics](AST_DIAGNOSTICS.md)"
    )
    replace_section(docs / "EVALUATION.md", "ASKREPO:DEPLOYED:EVAL", body)
    compact = body.replace("../backend/", "backend/").replace(
        "(AST_DIAGNOSTICS.md)", "(docs/AST_DIAGNOSTICS.md)"
    )
    replace_section(Path(__file__).parents[2] / "README.md", "ASKREPO:DEPLOYED:EVAL", compact)
    print(table(summaries), flush=True)
    print(conclusion, experiment, flush=True)
    print("Fixed-over-AST diagnostic cases:", len(diagnostic(report)), flush=True)
    print("Saved", output, flush=True)
