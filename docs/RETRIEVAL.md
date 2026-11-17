# Retrieval and streaming reference

## Chunking, retrieval, and safety

- Python, JavaScript/JSX, TypeScript/TSX, Java, C and C++ use tree-sitter. Functions, methods, classes, nested functions, import/docstring context and oversized overlapping pieces retain inclusive one-based source ranges. Large classes expose headers and separate methods. Markdown is split at headings. Other text uses 60-line windows with 10-line overlap.
- Chunk records include ID, repo, path, language, line range, symbol, parent, code, kind and enriched `path | language | parent.symbol` text. BM25 splits camelCase/acronyms/snake_case and retains each original identifier.
- BM25 top 50 and vector top 50 run in parallel. RRF uses k=60. Optional reranking scores the top 20 candidates. Context expansion adds matching class headers and imports without turning those extra context chunks into citations.
- A low-confidence result returns `notFound=true` without an LLM call. Generation uses a separate system instruction that treats repository code/comments as untrusted data. Invalid model citations are removed; an answer with no valid evidence citation is withheld. Ranges are checked against the exact prompt evidence. Markdown HTML is escaped and remote images are not rendered.
- Clone URLs must match public `https://github.com/owner/repo` syntax; credentials, alternate hosts, ports, queries and redirects are rejected. Git uses isolated configuration, no credential helper, no repository hooks, no submodule recursion, and HTTPS only. Cloning is time/disk bounded and checkout size is checked before materialization.
- Dependencies/build folders, lockfiles, binary/image/minified/oversized files, symlinks, and environment-secret files are excluded. Repository code is never executed. File reads reject absolute/drive/UNC paths, backslashes, traversal, nulls and symlink escapes after resolution.
- Request bodies, questions, queues, cached repositories, and IP buckets are bounded. Rate limiting uses the actual ASGI peer, not untrusted forwarding headers. Docker disables proxy-header trust by default. A future reverse-proxy setup must explicitly configure trusted proxy addresses.


## Streaming, chat memory, and free-tier controls

See [the transport and deployment guide](../backend/STREAMING.md) for event payloads and exact behavior. The frontend calls the backend URL directly using POST fetch and ReadableStream, including when hosted on Vercel. The server sends 15-second heartbeat comments and disables response buffering. Sources arrive before generation; citation objects arrive only after validation. Stop aborts the request, and an interrupted response stays marked as incomplete after reload.

Requests can include `history: [{role,content}]`, `agentic`, and an optional `requestId`. The browser sends its last six completed messages; the server bounds history to six messages and 6,000 characters, with assistant messages truncated to 1,200 characters. Standalone questions skip rewriting. Follow-ups search a standalone query but answer the original question using recent history and current evidence. Old citations never become valid merely because they appear in history. New chat starts without history.

`/ask` defaults agentic to false; `/ask/stream` defaults it to true. **The UI keeps agentic retrieval opt-in.** Strong ranking signals skip the model grader. Weak evidence can trigger one retry with at most two alternative queries, merged by RRF and optionally reranked. Still-weak results return not-found with the closest sources. Rewriting and grading use the configurable fast model; only the final answer uses the answer model. No-key mode uses deterministic history context, lexical query variants, and source excerpts; it does not claim Gemini rewrite/grader behavior.

Every provider attempt, including retries, shares `MAX_LLM_CALLS_PER_QUESTION` (default 3). Optional steps reserve a final answer call. SDK automatic retries are disabled. The wrapper allows at most two retries for 429/5xx, with backoff, a global minute limit, a peer-IP limit, and a bounded short-wait queue. Explicit quota errors display "Demo limit reached, try again in a minute". The frontend reuses a request ID for compatible stream/fallback attempts, preventing a second request from resetting its call budget. A missing streaming endpoint uses the older JSON shape for compatibility.

Validated complete answers have a bounded ten-minute in-memory cache. Keys include snapshot, normalized rewritten question, retrieval/model settings, original question and bounded-history digest. Cache hits replay the normal stream without new model calls. Errors and stopped answers are not cached. `totalMs` includes rewrite, grading and queue time; the original retrieve/rerank/generate latency fields remain available.

| Variable | Default / purpose |
| --- | --- |
| `GEMINI_FAST_MODEL` | `gemini-2.5-flash-lite`; rewrite and weak-result grading |
| `GEMINI_ANSWER_MODEL` | Optional; otherwise existing `ASKREPO_GEMINI_MODEL` |
| `MAX_LLM_CALLS_PER_QUESTION` | `3`; hard provider-attempt cap |
| `AGENTIC_ENABLED` | `true`; server-wide off switch when false |
| `ASKREPO_AGENTIC_GOOD_SCORE` / `ASKREPO_AGENTIC_LOWER_SCORE` | `0.65` / `0.35`; ranking-rule thresholds |
| `ASKREPO_LLM_GLOBAL_RPM` / `ASKREPO_LLM_PER_IP_RPM` | `10` / `6` |
| `ASKREPO_LLM_QUEUE_WAIT_SECONDS` / `ASKREPO_LLM_MAX_QUEUED` | `2` / `32` |
| `ASKREPO_LLM_MAX_RETRIES` / `ASKREPO_LLM_RETRY_BACKOFF_SECONDS` | `2` / `0.5` |
| `ASKREPO_ANSWER_CACHE_SIZE` / `ASKREPO_ANSWER_CACHE_TTL_SECONDS` | `128` entries / `600` seconds; size 0 disables caching |

For the deployed Render/Vercel setup, `VITE_API_BASE_URL=https://askrepo-api.onrender.com` and `ASKREPO_CORS_ORIGINS=["https://askrepo-murex.vercel.app"]`; stream POSTs share the same CORS policy. Keep secrets in the backend. Do not route SSE through a Vercel serverless function. Free-tier quotas vary by project/model; these controls bound usage but cannot guarantee provider availability. Cache, counters and request-ID budgets are per process and reset on restart. `llmCalls` counts text-provider attempts, not embedding requests or CPU inference. Lightweight mode also consumes Gemini embedding quota.

The original 45 questions and all 15 new follow-up cases (`followup-seekr-01`–`05`, `followup-codenest-01`–`05`, `followup-dptrace-01`–`05`) require manual review. Follow-up histories are authored drafts, not recorded model outputs. Verify the history, call sites and path/symbol targets in [the complete checklist](../backend/eval/REVIEW.md).

From `backend`, after explicitly indexing compatible snapshots:

```powershell
..\.venv\Scripts\python.exe -m eval.run_eval --suite advanced --validate-only
..\.venv\Scripts\python.exe -m eval.run_eval --suite advanced --share-initial --provider extractive
# After setting a Gemini key and selecting auto/gemini generation:
..\.venv\Scripts\python.exe -m eval.run_eval --suite advanced --provider configured --delay-seconds 20
```

The paired option measures one initial hybrid/reranked search and adds each branch's measured continuation; it records both components explicitly. Omit `--share-initial` for independent full executions. Follow-up comparisons use hybrid retrieval without reranking in both modes unless `--followup-rerank` is supplied. Caching is disabled for evaluation. A no-key run reports actual CPU/offline behavior and zero text-provider calls; it must not be described as measured Gemini quality. The script updates a separate results table only after the full run succeeds.

A running API owns its embedded Qdrant directory. To evaluate without stopping it, create an isolated consistent copy:

```powershell
..\.venv\Scripts\python.exe -m eval.snapshot --output data/eval-copy
..\.venv\Scripts\python.exe -m eval.run_eval --suite advanced --share-initial --advanced-data-dir data/eval-copy
```

The snapshot helper uses SQLite online backups of completed immutable indexes, retains identical source files and vectors, and does not copy the live Qdrant lock. The report records snapshot provenance and corpus hashes. No source repository is modified or executed.

