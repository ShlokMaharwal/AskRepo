"""Print every fixed-over-AST case and chunk distributions from a measured report."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from statistics import median


def context_variant(chunks, limit=800):
    """Experimental embedding/keyword context; source code/ranges remain unchanged."""
    result = []
    by_file = {}
    for chunk in chunks:
        if chunk.kind in {"imports", "class_header"}:
            by_file.setdefault(chunk.path, []).append(chunk)
    for chunk in chunks:
        context = "\n".join(
            candidate.code
            for candidate in by_file.get(chunk.path, [])
            if candidate.id != chunk.id
            and (candidate.kind == "imports" or candidate.symbol_name == chunk.parent_symbol)
        )[:limit]
        text = (
            chunk.text
            if not context
            else chunk.text.split("\n", 1)[0] + "\nContext:\n" + context + "\nCode:\n" + chunk.code
        )
        result.append(replace(chunk, text=text))
    return result


def distribution(chunks):
    sizes = sorted(len(chunk.code) for chunk in chunks)
    return {
        "count": len(sizes),
        "min": min(sizes, default=0),
        "median": median(sizes) if sizes else 0,
        "max": max(sizes, default=0),
        "tiny_below_120": sum(size < 120 for size in sizes),
        "large_above_4500": sum(size > 4500 for size in sizes),
        "missing_path_in_embedding": sum(chunk.path not in chunk.text for chunk in chunks),
    }


def diagnostic(report):
    groups = {}
    for row in report["rows"]:
        groups.setdefault((row["repo"], row["id"], row["retrieval"]), {})[row["chunking"]] = row
    cases = []
    for (repo, identifier, mode), modes in groups.items():
        fixed, ast = modes["fixed"], modes["ast"]
        if (fixed["metrics"]["recall@10"], fixed["metrics"]["mrr"]) > (
            ast["metrics"]["recall@10"],
            ast["metrics"]["mrr"],
        ):
            cases.append(
                {
                    "repo": repo,
                    "id": identifier,
                    "mode": mode,
                    "question": fixed["question"],
                    "relevant": fixed["relevant"],
                    "fixed": fixed["ranked"],
                    "ast": ast["ranked"],
                }
            )
    return cases


def render(report):
    lines = [
        "# AST diagnostics: deployed-lite",
        "",
        "Labels remain drafts. A hit means file match plus overlap with a resolved",
        "symbol range; path-only targets accept any chunk in that file. Broad",
        "fixed windows can therefore benefit from the label-resolution rule.",
        "These cases are diagnostic evidence, not human-validated relevance.",
        "",
        "The baseline embedding text already includes path, language and qualified",
        "symbol. The context experiment also prefixes imports/class headers,",
        "affecting BM25 and vector text while preserving citable source ranges.",
        "",
        "## Chunk sizes (source characters)",
        "",
        "| Variant | Repo | Count | Min | Median | Max | <120 | >4500 | Missing path prefix |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["indexes"]:
        d = item["distribution"]
        lines.append(
            f"| {item['chunking']} | {item['repo']} | {d['count']} | {d['min']} | "
            f"{d['median']} | {d['max']} | {d['tiny_below_120']} | "
            f"{d['large_above_4500']} | {d['missing_path_in_embedding']} |"
        )
    for case in diagnostic(report):
        lines += [
            "",
            f"## {case['id']} / {case['mode']}",
            "",
            case["question"],
            "",
            "Draft labels: `" + json.dumps(case["relevant"]) + "`",
            "",
            "| Rank | Fixed result | AST result |",
            "| ---: | --- | --- |",
        ]
        for index in range(10):
            cells = []
            for mode in ["fixed", "ast"]:
                ranked = case[mode]
                chunk = ranked[index] if index < len(ranked) else None
                cells.append(
                    "—"
                    if chunk is None
                    else f"`{chunk['path']}:{chunk['start_line']}-{chunk['end_line']}` "
                    f"{chunk['symbol_name']} ({chunk['score']:.4f})"
                )
            lines.append(f"| {index + 1} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = render(json.loads(args.report.read_text(encoding="utf-8")))
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
