"""Render the complete human review checklist from the JSONL source of truth."""

import json
from pathlib import Path


def main():
    root = Path(__file__).parent
    lines = [
        "# Review all 60 draft standalone and follow-up cases",
        "",
        "These are provisional relevance labels, not independently verified ground truth.",
        "Check the question and inspect the source snapshot/commit in the results JSON. "
        "Correct or add relevant paths/symbols, and set `reviewed:true` in the JSONL row.",
        "Edit the JSONL files, then rerun this checklist generator "
        "and `run_eval --require-reviewed`.",
        "The 15 follow-up histories are authored drafts, not recorded model responses. "
        "Verify both the context and the expected targets; call-site and path-only labels "
        "deserve particular scrutiny. Use `--suite advanced --require-reviewed` for that suite.",
        "",
        "| ID | Question | Draft relevant target | Human review |",
        "| --- | --- | --- | --- |",
    ]
    for filename in sorted((root / "questions").glob("*.jsonl")):
        for raw in filename.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            target = "; ".join(
                item["path"] + (" :: " + item["symbol"] if item.get("symbol") else " (path only)")
                for item in row["relevant"]
            )
            lines.append(
                f"| {row['id']} | {row['question']} | `{target}` | "
                + ("Reviewed" if row.get("reviewed") else "REQUIRED")
                + " |"
            )
    (root / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
