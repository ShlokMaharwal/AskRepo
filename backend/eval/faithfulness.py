"""Structural citation audit, not a semantic-accuracy or entailment judge."""

import argparse
import json
import random
from pathlib import Path

from app.config import Settings
from app.generate.llm import ExtractiveLLM, get_llm
from app.index.vectors import Vectors, get_embedder
from app.models import AskRequest
from app.retrieve.hybrid import Retriever
from app.retrieve.reranker import Reranker
from app.service import AnswerService
from app.storage import Storage


def audit_answer(answer, storage, repo_id):
    checks = []
    for citation in answer.citations:
        try:
            content, _ = storage.file(repo_id, citation.path)
            exists = 1 <= citation.start_line <= citation.end_line <= len(content.splitlines())
            retrieved = any(
                chunk.path == citation.path
                and chunk.start_line <= citation.start_line
                and citation.end_line <= chunk.end_line
                for chunk in answer.chunks
            )
            checks.append(exists and retrieved)
        except (ValueError, KeyError, FileNotFoundError):
            checks.append(False)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/eval-indexes/ast"))
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--provider", choices=("extractive", "configured"), default="extractive")
    args = parser.parse_args()
    if args.samples < 1:
        raise ValueError("Sample count must be positive")
    report = json.loads(args.results.read_text(encoding="utf-8"))
    settings = Settings().model_copy(update={"data_dir": args.data_dir})
    storage = Storage(settings.data_dir)
    provider = ExtractiveLLM() if args.provider == "extractive" else get_llm(settings)
    retriever = Retriever(
        storage,
        Vectors(settings, get_embedder(settings)),
        settings,
        None if settings.lite_mode else Reranker(settings),
    )
    indexes = {row["repo"]: row["repo_id"] for row in report["indexes"] if row["chunking"] == "ast"}
    choices = [(repo, row) for repo, rows in report["questions"].items() for row in rows]
    samples = random.Random(args.seed).sample(choices, min(args.samples, len(choices)))
    checks, rows = [], []
    try:
        service = AnswerService(retriever, provider, settings)
        for repo, question in samples:
            repo_id = indexes[repo]
            response = service.ask(
                AskRequest(repo_id=repo_id, question=question["question"], top_k=8, rerank=False)
            )
            valid = audit_answer(response, storage, repo_id)
            checks.extend(valid)
            rows.append(
                {
                    "id": question["id"],
                    "repo": repo,
                    "notFound": response.not_found,
                    "answer": response.answer,
                    "citations": [item.model_dump(by_alias=True) for item in response.citations],
                    "valid": valid,
                }
            )
    finally:
        retriever.close()
    output = args.results.with_name(args.results.stem + "-citation-audit.json")
    result = {
        "provider": provider.name,
        "sampled_answers": len(rows),
        "seed": args.seed,
        "cited_answers": sum(bool(row["citations"]) for row in rows),
        "not_found_answers": sum(row["notFound"] for row in rows),
        "citations_checked": len(checks),
        "citations_valid": sum(checks),
        "citation_validity_rate": sum(checks) / len(checks) if checks else None,
        "note": "Structural range validity only; this does not establish semantic faithfulness.",
        "rows": rows,
    }
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
