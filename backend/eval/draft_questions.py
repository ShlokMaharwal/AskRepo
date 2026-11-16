"""Draft labels inspected against public snapshots; all 45 require human review."""

import argparse
import json
from pathlib import Path

DRAFTS = {
    "Seekr": [
        (
            "How does the crawl frontier atomically reject duplicate URLs before scheduling them?",
            "apps/crawler/src/frontier.ts",
            "enqueue",
        ),
        (
            "How does the crawler recover work abandoned by a crashed worker?",
            "apps/crawler/src/frontier.ts",
            "reapStale",
        ),
        (
            "How are per-domain crawl delays enforced when a worker dequeues a URL?",
            "apps/crawler/src/frontier.ts",
            "dequeue",
        ),
        (
            "Which checks prevent HTTP fetching from accessing private network addresses?",
            "apps/crawler/src/fetcher.ts",
            "assertSafeUrl",
        ),
        (
            "How are HTML text, title and outgoing links extracted from a downloaded page?",
            "apps/crawler/src/parser.ts",
            "parseHtml",
        ),
        (
            "How does BM25 combine inverse document frequency, term saturation "
            "and document length?",
            "packages/core/src/ranker.ts",
            "scoreBM25",
        ),
        (
            "How is title weighting combined with body term frequency in BM25F?",
            "packages/core/src/ranker.ts",
            "scoreBM25F",
        ),
        (
            "How are quoted phrases and OR clauses parsed from a search query?",
            "packages/core/src/query-parser.ts",
            "parseQuery",
        ),
        (
            "How does autocomplete rank and cache completions for a prefix?",
            "packages/core/src/trie.ts",
            None,
        ),
        (
            "How is an inverted index encoded into a checksummed binary snapshot?",
            "packages/core/src/serializer.ts",
            "encodeIndex",
        ),
        (
            "What validation happens while a binary index snapshot is decoded?",
            "packages/core/src/serializer.ts",
            "decodeIndex",
        ),
        (
            "How are documents removed from the positional inverted index?",
            "packages/core/src/inverted-index.ts",
            "removeDocument",
        ),
        (
            "How are misspelled query terms converted into spelling suggestions?",
            "packages/core/src/typo.ts",
            "didYouMean",
        ),
        (
            "How does the snippet generator choose a window around query terms?",
            "packages/core/src/snippet.ts",
            "generateSnippet",
        ),
        (
            "How is SimHash used to represent a document for near-duplicate detection?",
            "packages/core/src/simhash.ts",
            "simHash",
        ),
    ],
    "CodeNest": [
        (
            "How are interview invitation tokens signed and checked for expiration?",
            "server/invites.js",
            "verifyInvite",
        ),
        (
            "How is an invite bound to a single candidate identity?",
            "server/invites.js",
            "consumeInvite",
        ),
        (
            "Which server checks restrict editor-control events to interviewers?",
            "server/socket-policy.js",
            "authorizeEvent",
        ),
        (
            "How are concurrent updates to the same interview room serialized?",
            "server/room-state.js",
            "createRoomQueue",
        ),
        (
            "How does reconnecting restore an interviewer's editor lock?",
            "server/room-state.js",
            "restoreRoomState",
        ),
        (
            "How are hint quotas reserved before calling the AI provider?",
            "server/hints.js",
            "reserveHint",
        ),
        (
            "Where are Socket.io payloads validated before handlers process them?",
            "server/socket-schemas.js",
            "validateSocketInput",
        ),
        (
            "How does the execution adapter run code and handle supported runtimes?",
            "src/lib/wandbox.ts",
            "executeCode",
        ),
        (
            "How are submitted solutions graded against test cases?",
            "src/lib/grading.ts",
            "gradeSolution",
        ),
        (
            "How are candidate code and user data delimited inside the AI hint prompt?",
            "src/lib/gemini.ts",
            "buildHintPrompt",
        ),
        (
            "How is an AI interview review validated and normalized?",
            "src/lib/gemini.ts",
            "generateReview",
        ),
        (
            "How does the HTTP JSON reader enforce input-size and schema constraints?",
            "src/lib/api.ts",
            "readJSON",
        ),
        (
            "How does Redis rate limiting enforce a request window?",
            "server/rate-limit.js",
            "consumeRateLimit",
        ),
        (
            "How does the application establish and reuse its MongoDB connection?",
            "src/lib/mongodb.ts",
            "connectDB",
        ),
        (
            "How are recorded session snapshots played back in the replay page?",
            "src/app/room/[roomId]/replay/page.tsx",
            None,
        ),
    ],
    "DPTrace": [
        (
            "How does memoized Fibonacci record a cache hit in its execution trace?",
            "src/algorithms/fibonacci/memoized.js",
            "run",
        ),
        (
            "Why does the space-optimized 0/1 knapsack loop through capacities backwards?",
            "src/algorithms/knapsack/spaceOptimized.js",
            "run",
        ),
        (
            "How does coin-change tabulation compute the minimum number of coins?",
            "src/algorithms/coinChange/tabulation.js",
            "run",
        ),
        (
            "How is the longest common subsequence DP table filled?",
            "src/algorithms/lcs/tabulation.js",
            "run",
        ),
        (
            "How does edit-distance memoization handle insertion, deletion and replacement?",
            "src/algorithms/editDistance/memoized.js",
            "run",
        ),
        (
            "How is the longest increasing subsequence computed with reduced space?",
            "src/algorithms/lis/spaceOptimized.js",
            "run",
        ),
        (
            "How does matrix-chain tabulation choose a split between matrix products?",
            "src/algorithms/mcm/tabulation.js",
            "run",
        ),
        (
            "How does the word-break algorithm use a dictionary to fill its DP table?",
            "src/algorithms/wordBreak/tabulation.js",
            "run",
        ),
        (
            "How does the grid-path algorithm handle obstacles?",
            "src/algorithms/gridPaths/tabulation.js",
            "run",
        ),
        (
            "Where are user inputs bounded before expensive recursive approaches can run?",
            "src/algorithms/validateInput.js",
            "validateInput",
        ),
        (
            "How is playback speed converted into an automatic step interval?",
            "src/hooks/usePlayback.js",
            "usePlayback",
        ),
        (
            "How are trace-based quiz questions generated deterministically from a seed?",
            "src/algorithms/quizGenerator.js",
            "generateQuizQuestions",
        ),
        (
            "How are quiz attempts and best scores updated for each difficulty?",
            "src/algorithms/quizProgress.js",
            "recordQuizScore",
        ),
        (
            "How is malformed saved quiz progress handled when loading browser storage?",
            "src/algorithms/quizProgress.js",
            "loadQuizProgress",
        ),
        (
            "How does the recurrence parser turn a custom recurrence into a trace?",
            "src/components/features/RecurrenceParser.jsx",
            None,
        ),
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Intentionally replace existing labels"
    )
    args = parser.parse_args()
    root = Path(__file__).parent / "questions"
    root.mkdir(exist_ok=True)
    if any(root.glob("*.jsonl")) and not args.force:
        raise SystemExit(
            "Question files exist. Edit them by hand; --force replaces reviewed labels."
        )
    for repo, rows in DRAFTS.items():
        questions = []
        for index, (question, path, symbol) in enumerate(rows, 1):
            relevant = {"path": path}
            if symbol:
                relevant["symbol"] = symbol
            questions.append(
                {
                    "id": f"{repo.lower()}-{index:02d}",
                    "question": question,
                    "relevant": [relevant],
                    "reviewed": False,
                }
            )
        (root / f"{repo.lower()}.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in questions) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
