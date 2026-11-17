"""Run actual CPU retrieval benchmarks across both chunkers and all four modes."""

import argparse
import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.config import Settings
from app.index.vectors import Vectors, get_embedder
from app.ingest.chunker import chunk_file
from app.ingest.clone import source_files
from app.retrieve.hybrid import Retriever
from app.retrieve.reranker import Reranker
from app.storage import Storage, contained_path
from eval.metrics import aggregate, measure
from eval.prepare import DEMO_REPOS

CONFIGS = (("bm25", False), ("vector", False), ("hybrid", False), ("hybrid", True))


def load_questions(repo, source, settings, require_reviewed=False, rows=None):
    filename = Path(__file__).parent / "questions" / f"{repo.lower()}.jsonl"
    rows = (
        rows
        if rows is not None
        else [
            json.loads(line)
            for line in filename.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    )
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError(f"Question IDs must be nonempty and unique: {repo}")
    for row in rows:
        if require_reviewed and not row.get("reviewed"):
            raise ValueError(f"Review required: {row['id']}")
        if not row["question"].strip() or not row["relevant"]:
            raise ValueError(f"Incomplete question: {row['id']}")
        for target in row["relevant"]:
            file = contained_path(source, target["path"])
            if not file.is_file():
                raise ValueError(f"Ground-truth path does not exist: {row['id']} {target['path']}")
            if target.get("symbol"):
                chunks = chunk_file(
                    "truth",
                    target["path"],
                    file.read_text(encoding="utf-8-sig"),
                    max_chars=settings.max_chunk_chars,
                )
                found = [
                    chunk
                    for chunk in chunks
                    if target["symbol"]
                    in {chunk.symbol_name, f"{chunk.parent_symbol}.{chunk.symbol_name}"}
                ]
                if not found:
                    raise ValueError(
                        f"Ground-truth symbol does not exist: {row['id']} {target['symbol']}"
                    )
                target["ranges"] = [(chunk.start_line, chunk.end_line) for chunk in found]
    return rows


def markdown_table(summaries):
    lines = [
        "| Chunking | Retrieval | Recall@1 | Recall@5 | Recall@10 "
        "| MRR@10 | Hit rate@10 | Avg ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summaries:
        metrics = row["metrics"]
        values = [
            f"{metrics[key]:.4f}"
            for key in ("recall@1", "recall@5", "recall@10", "mrr", "hit_rate@10")
        ]
        lines.append(
            f"| {row['chunking']} | {row['retrieval']} | "
            + " | ".join(values)
            + f" | {metrics['latency_ms']:.2f} |"
        )
    return "\n".join(lines)


def update_readme(path, table, output, status):
    start, end = "<!-- ASKREPO:EVAL:START -->", "<!-- ASKREPO:EVAL:END -->"
    section = (
        f"{start}\nGround truth: **{status}**. Actual CPU run: `{output.name}`.\n\n{table}\n{end}"
    )
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    text = (
        pattern.sub(lambda _: section, text)
        if pattern.search(text)
        else text + "\n\n## Measured retrieval results\n\n" + section + "\n"
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def evaluate(args):
    settings = Settings()
    if settings.lite_mode:
        raise ValueError(
            "Use local CPU models for the complete four-mode benchmark; LITE_MODE skips reranking"
        )
    questions = {
        repo: load_questions(repo, args.sources / repo, settings, args.require_reviewed)
        for repo in args.repos
    }
    if args.validate_only:
        print(
            f"Validated {sum(map(len, questions.values()))} question paths/symbols. "
            "Human review is still required."
        )
        return
    embedder, reranker = get_embedder(settings), Reranker(settings)
    embedder.encode(["Repository search warmup"], query=True)
    reranker.score("Repository search warmup", ["This function searches a repository."])
    rows, indexes = [], []
    implementation_hash = hashlib.sha256(
        b"".join(
            path.read_bytes() for path in sorted((Path(__file__).parents[1] / "app").rglob("*.py"))
        )
    ).hexdigest()
    revisions = {
        repo: subprocess.run(
            ["git", "-C", str(args.sources / repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for repo in args.repos
    }
    for strategy in ("fixed", "ast"):
        config = settings.model_copy(
            update={"data_dir": args.data_dir / strategy, "chunk_strategy": strategy}
        )
        storage = Storage(config.data_dir)
        retriever = Retriever(storage, Vectors(config, embedder), config, reranker)
        try:
            for repo in args.repos:
                repo_id = uuid5(
                    NAMESPACE_URL,
                    f"{repo}:{revisions[repo]}:{strategy}:{settings.max_chunk_chars}:"
                    f"{embedder.name}:{implementation_hash}",
                ).hex
                started = perf_counter()
                if repo_id not in {item.repo_id for item in storage.repos()}:
                    files = source_files(args.sources / repo, config)
                    chunks = [
                        chunk
                        for path, code in files
                        for chunk in chunk_file(
                            repo_id, path, code, strategy, config.max_chunk_chars
                        )
                    ]
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
                        "chunking": strategy,
                        "indexing_or_load_ms": (perf_counter() - started) * 1000,
                        "stats": storage.metadata(repo_id),
                    }
                )
                for mode, rerank in CONFIGS:
                    label = mode + (" + rerank" if rerank else "")
                    print(f"{strategy} / {repo} / {label}", flush=True)
                    for question in questions[repo]:
                        result = retriever.query(
                            repo_id, question["question"], 10, mode=mode, rerank=rerank
                        )
                        ranked = [
                            dict(chunk.to_dict(), score=score.score)
                            for chunk, score in zip(result.sources, result.chunks, strict=True)
                        ]
                        for chunk in ranked:
                            chunk.pop("code")
                            chunk.pop("text")
                        rows.append(
                            {
                                "repo": repo,
                                "id": question["id"],
                                "chunking": strategy,
                                "retrieval": label,
                                "ranked": ranked,
                                "metrics": measure(
                                    ranked,
                                    question["relevant"],
                                    result.retrieve_ms + result.rerank_ms,
                                ),
                            }
                        )
        finally:
            retriever.close()
    summaries = [
        {
            "chunking": strategy,
            "retrieval": mode + (" + rerank" if rerank else ""),
            "metrics": aggregate(
                [
                    row["metrics"]
                    for row in rows
                    if row["chunking"] == strategy
                    and row["retrieval"] == mode + (" + rerank" if rerank else "")
                ]
            ),
        }
        for strategy in ("fixed", "ast")
        for mode, rerank in CONFIGS
    ]
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    output = Path(__file__).parent / "results" / f"{now.date()}.json"
    output.parent.mkdir(exist_ok=True)
    status = (
        "reviewed"
        if all(row.get("reviewed") for group in questions.values() for row in group)
        else "draft—human review required"
    )
    report = {
        "created_at": now.isoformat(),
        "ground_truth_status": status,
        "question_count": sum(map(len, questions.values())),
        "revisions": revisions,
        "embedding_model": embedder.name,
        "reranker_model": settings.reranker_model,
        "device": "cpu",
        "quantize_models": settings.quantize_models,
        "quantize_linears": settings.quantize_linears,
        "model_threads": settings.model_threads,
        "embedding_batch_size": settings.embedding_batch_size,
        "reranker_batch_size": settings.reranker_batch_size,
        "embedding_max_length": settings.embedding_max_length,
        "reranker_max_length": settings.reranker_max_length,
        "implementation_sha256": implementation_hash,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {
            name: version(name)
            for name in (
                "torch",
                "sentence-transformers",
                "qdrant-client",
                "tree-sitter-language-pack",
            )
        },
        "question_sha256": {
            repo: hashlib.sha256(
                (Path(__file__).parent / "questions" / f"{repo.lower()}.jsonl").read_bytes()
            ).hexdigest()
            for repo in args.repos
        },
        "summaries": summaries,
        "indexes": indexes,
        "questions": questions,
        "rows": rows,
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    table = markdown_table(summaries)
    print(table)
    update_readme(args.readme, table, output, status)
    print(f"Saved {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("data/eval-sources"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/eval-indexes"))
    parser.add_argument("--repos", nargs="+", choices=DEMO_REPOS, default=list(DEMO_REPOS))
    parser.add_argument("--require-reviewed", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--readme", type=Path, default=Path("../docs/EVALUATION.md"))
    parser.add_argument("--suite", choices=("retrieval", "advanced"), default="retrieval")
    parser.add_argument("--provider", choices=("extractive", "configured"), default="extractive")
    parser.add_argument("--advanced-data-dir", type=Path)
    parser.add_argument(
        "--share-initial",
        action="store_true",
        help="Pair modes on one freshly measured initial search; "
        "report cumulative measured stage latency",
    )
    parser.add_argument(
        "--followup-rerank",
        action="store_true",
        help="Enable reranking in both follow-up ablations",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        help="Pause between records; configured Gemini defaults to 20 seconds, extractive to zero",
    )
    args = parser.parse_args()
    if args.suite == "advanced":
        from eval.advanced import evaluate_advanced

        evaluate_advanced(args)
    else:
        evaluate(args)


if __name__ == "__main__":
    main()
