# Review all 60 draft standalone and follow-up cases

These are provisional relevance labels, not independently verified ground truth.
Check the question and inspect the source snapshot/commit in the results JSON. Correct or add relevant paths/symbols, and set `reviewed:true` in the JSONL row.
Edit the JSONL files, then rerun this checklist generator and `run_eval --require-reviewed`.
The 15 follow-up histories are authored drafts, not recorded model responses. Verify both the context and the expected targets; call-site and path-only labels deserve particular scrutiny. Use `--suite advanced --require-reviewed` for that suite.

| ID | Question | Draft relevant target | Human review |
| --- | --- | --- | --- |
| codenest-01 | How are interview invitation tokens signed and checked for expiration? | `server/invites.js :: verifyInvite` | REQUIRED |
| codenest-02 | How is an invite bound to a single candidate identity? | `server/invites.js :: consumeInvite` | REQUIRED |
| codenest-03 | Which server checks restrict editor-control events to interviewers? | `server/socket-policy.js :: authorizeEvent` | REQUIRED |
| codenest-04 | How are concurrent updates to the same interview room serialized? | `server/room-state.js :: createRoomQueue` | REQUIRED |
| codenest-05 | How does reconnecting restore an interviewer's editor lock? | `server/room-state.js :: restoreRoomState` | REQUIRED |
| codenest-06 | How are hint quotas reserved before calling the AI provider? | `server/hints.js :: reserveHint` | REQUIRED |
| codenest-07 | Where are Socket.io payloads validated before handlers process them? | `server/socket-schemas.js :: validateSocketInput` | REQUIRED |
| codenest-08 | How does the execution adapter run code and handle supported runtimes? | `src/lib/wandbox.ts :: executeCode` | REQUIRED |
| codenest-09 | How are submitted solutions graded against test cases? | `src/lib/grading.ts :: gradeSolution` | REQUIRED |
| codenest-10 | How are candidate code and user data delimited inside the AI hint prompt? | `src/lib/gemini.ts :: buildHintPrompt` | REQUIRED |
| codenest-11 | How is an AI interview review validated and normalized? | `src/lib/gemini.ts :: generateReview` | REQUIRED |
| codenest-12 | How does the HTTP JSON reader enforce input-size and schema constraints? | `src/lib/api.ts :: readJSON` | REQUIRED |
| codenest-13 | How does Redis rate limiting enforce a request window? | `server/rate-limit.js :: consumeRateLimit` | REQUIRED |
| codenest-14 | How does the application establish and reuse its MongoDB connection? | `src/lib/mongodb.ts :: connectDB` | REQUIRED |
| codenest-15 | How are recorded session snapshots played back in the replay page? | `src/app/room/[roomId]/replay/page.tsx (path only)` | REQUIRED |
| dptrace-01 | How does memoized Fibonacci record a cache hit in its execution trace? | `src/algorithms/fibonacci/memoized.js :: run` | REQUIRED |
| dptrace-02 | Why does the space-optimized 0/1 knapsack loop through capacities backwards? | `src/algorithms/knapsack/spaceOptimized.js :: run` | REQUIRED |
| dptrace-03 | How does coin-change tabulation compute the minimum number of coins? | `src/algorithms/coinChange/tabulation.js :: run` | REQUIRED |
| dptrace-04 | How is the longest common subsequence DP table filled? | `src/algorithms/lcs/tabulation.js :: run` | REQUIRED |
| dptrace-05 | How does edit-distance memoization handle insertion, deletion and replacement? | `src/algorithms/editDistance/memoized.js :: run` | REQUIRED |
| dptrace-06 | How is the longest increasing subsequence computed with reduced space? | `src/algorithms/lis/spaceOptimized.js :: run` | REQUIRED |
| dptrace-07 | How does matrix-chain tabulation choose a split between matrix products? | `src/algorithms/mcm/tabulation.js :: run` | REQUIRED |
| dptrace-08 | How does the word-break algorithm use a dictionary to fill its DP table? | `src/algorithms/wordBreak/tabulation.js :: run` | REQUIRED |
| dptrace-09 | How does the grid-path algorithm handle obstacles? | `src/algorithms/gridPaths/tabulation.js :: run` | REQUIRED |
| dptrace-10 | Where are user inputs bounded before expensive recursive approaches can run? | `src/algorithms/validateInput.js :: validateInput` | REQUIRED |
| dptrace-11 | How is playback speed converted into an automatic step interval? | `src/hooks/usePlayback.js :: usePlayback` | REQUIRED |
| dptrace-12 | How are trace-based quiz questions generated deterministically from a seed? | `src/algorithms/quizGenerator.js :: generateQuizQuestions` | REQUIRED |
| dptrace-13 | How are quiz attempts and best scores updated for each difficulty? | `src/algorithms/quizProgress.js :: recordQuizScore` | REQUIRED |
| dptrace-14 | How is malformed saved quiz progress handled when loading browser storage? | `src/algorithms/quizProgress.js :: loadQuizProgress` | REQUIRED |
| dptrace-15 | How does the recurrence parser turn a custom recurrence into a trace? | `src/components/features/RecurrenceParser.jsx (path only)` | REQUIRED |
| followup-seekr-01 | and where is that called? | `apps/crawler/src/worker.ts :: processUrl; apps/crawler/src/main.ts :: main` | REQUIRED |
| followup-seekr-02 | How does it decide that a worker's work is stale? | `apps/crawler/src/frontier.ts :: reapStale` | REQUIRED |
| followup-seekr-03 | Which private addresses does that reject? | `apps/crawler/src/fetcher.ts :: assertSafeUrl` | REQUIRED |
| followup-seekr-04 | What role does document length play in that score? | `packages/core/src/ranker.ts :: scoreBM25` | REQUIRED |
| followup-seekr-05 | What metadata does it include in the snapshot? | `packages/core/src/serializer.ts :: encodeIndex` | REQUIRED |
| followup-codenest-01 | How does it detect an expired token? | `server/invites.js :: verifyInvite` | REQUIRED |
| followup-codenest-02 | Which role checks does that apply? | `server/socket-policy.js :: authorizeEvent` | REQUIRED |
| followup-codenest-03 | What happens when that quota is already exhausted? | `server/hints.js :: reserveHint` | REQUIRED |
| followup-codenest-04 | How does it decide whether each test case passed? | `src/lib/grading.ts :: gradeSolution` | REQUIRED |
| followup-codenest-05 | How does that separate instructions from candidate code? | `src/lib/gemini.ts :: buildHintPrompt` | REQUIRED |
| followup-dptrace-01 | How does it record a repeated state in the trace? | `src/algorithms/fibonacci/memoized.js :: run` | REQUIRED |
| followup-dptrace-02 | Why does it visit the capacities in reverse order? | `src/algorithms/knapsack/spaceOptimized.js :: run` | REQUIRED |
| followup-dptrace-03 | and where is that called? | `src/algorithms/index.js (path only)` | REQUIRED |
| followup-dptrace-04 | How does that change the interval when speed changes? | `src/hooks/usePlayback.js :: usePlayback` | REQUIRED |
| followup-dptrace-05 | How does it keep the quiz deterministic? | `src/algorithms/quizGenerator.js :: generateQuizQuestions` | REQUIRED |
| seekr-01 | How does the crawl frontier atomically reject duplicate URLs before scheduling them? | `apps/crawler/src/frontier.ts :: enqueue` | REQUIRED |
| seekr-02 | How does the crawler recover work abandoned by a crashed worker? | `apps/crawler/src/frontier.ts :: reapStale` | REQUIRED |
| seekr-03 | How are per-domain crawl delays enforced when a worker dequeues a URL? | `apps/crawler/src/frontier.ts :: dequeue` | REQUIRED |
| seekr-04 | Which checks prevent HTTP fetching from accessing private network addresses? | `apps/crawler/src/fetcher.ts :: assertSafeUrl` | REQUIRED |
| seekr-05 | How are HTML text, title and outgoing links extracted from a downloaded page? | `apps/crawler/src/parser.ts :: parseHtml` | REQUIRED |
| seekr-06 | How does BM25 combine inverse document frequency, term saturation and document length? | `packages/core/src/ranker.ts :: scoreBM25` | REQUIRED |
| seekr-07 | How is title weighting combined with body term frequency in BM25F? | `packages/core/src/ranker.ts :: scoreBM25F` | REQUIRED |
| seekr-08 | How are quoted phrases and OR clauses parsed from a search query? | `packages/core/src/query-parser.ts :: parseQuery` | REQUIRED |
| seekr-09 | How does autocomplete rank and cache completions for a prefix? | `packages/core/src/trie.ts (path only)` | REQUIRED |
| seekr-10 | How is an inverted index encoded into a checksummed binary snapshot? | `packages/core/src/serializer.ts :: encodeIndex` | REQUIRED |
| seekr-11 | What validation happens while a binary index snapshot is decoded? | `packages/core/src/serializer.ts :: decodeIndex` | REQUIRED |
| seekr-12 | How are documents removed from the positional inverted index? | `packages/core/src/inverted-index.ts :: removeDocument` | REQUIRED |
| seekr-13 | How are misspelled query terms converted into spelling suggestions? | `packages/core/src/typo.ts :: didYouMean` | REQUIRED |
| seekr-14 | How does the snippet generator choose a window around query terms? | `packages/core/src/snippet.ts :: generateSnippet` | REQUIRED |
| seekr-15 | How is SimHash used to represent a document for near-duplicate detection? | `packages/core/src/simhash.ts :: simHash` | REQUIRED |
