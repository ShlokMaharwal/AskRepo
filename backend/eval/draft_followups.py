"""Initial authored follow-up cases. Never overwrite manually corrected labels silently."""

import argparse
import json
from pathlib import Path

CASES = {
    "Seekr": [
        (1, "and where is that called?"),
        (2, "How does it decide that a worker's work is stale?"),
        (4, "Which private addresses does that reject?"),
        (6, "What role does document length play in that score?"),
        (10, "What metadata does it include in the snapshot?"),
    ],
    "CodeNest": [
        (1, "How does it detect an expired token?"),
        (3, "Which role checks does that apply?"),
        (6, "What happens when that quota is already exhausted?"),
        (9, "How does it decide whether each test case passed?"),
        (10, "How does that separate instructions from candidate code?"),
    ],
    "DPTrace": [
        (1, "How does it record a repeated state in the trace?"),
        (2, "Why does it visit the capacities in reverse order?"),
        (10, "and where is that called?"),
        (11, "How does that change the interval when speed changes?"),
        (12, "How does it keep the quiz deterministic?"),
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).parent / "questions"
    destination = root / "followups.jsonl"
    if destination.exists() and not args.force:
        raise SystemExit(
            "Follow-ups already exist. Edit them directly; --force discards corrections."
        )
    rows = []
    for repo, cases in CASES.items():
        originals = [
            json.loads(line)
            for line in (root / f"{repo.lower()}.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        for number, (index, question) in enumerate(cases, 1):
            original = originals[index - 1]
            target = original["relevant"][0]
            symbol = target.get("symbol", target["path"])
            relevant = original["relevant"]
            if repo == "Seekr" and number == 1:
                relevant = [
                    {"path": "apps/crawler/src/worker.ts", "symbol": "processUrl"},
                    {"path": "apps/crawler/src/main.ts", "symbol": "main"},
                ]
            if repo == "DPTrace" and number == 3:
                relevant = [{"path": "src/algorithms/index.js"}]
            rows.append(
                {
                    "id": f"followup-{repo.lower()}-{number:02d}",
                    "repo": repo,
                    "history": [
                        {"role": "user", "content": original["question"]},
                        {
                            "role": "assistant",
                            "content": f"The earlier answer identified `{symbol}` "
                            f"in `{target['path']}`.",
                        },
                    ],
                    "question": question,
                    "relevant": relevant,
                    "reviewed": False,
                    "history_origin": "Authored draft, not recorded model output",
                }
            )
    destination.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} draft follow-up cases; all require human review.")


if __name__ == "__main__":
    main()
