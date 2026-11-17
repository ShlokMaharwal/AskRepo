# Streaming, memory, and bounded retrieval

The frontend calls `VITE_API_BASE_URL` directly with `fetch`, including on Vercel. It uses a POST body and a `ReadableStream`, not `EventSource` or a Vercel serverless proxy. Existing clients can keep using `POST /ask` and its original fields.

## Request and events

Both endpoints accept optional `history: [{role:"user"|"assistant",content}]`, `agentic`, and `requestId`. `/ask` defaults agentic to false; `/ask/stream` defaults it to true. The UI explicitly sends its opt-in setting, which defaults to false. A client should reuse `requestId` when falling back from a failed stream so both attempts share the same model-call budget.

Each SSE packet is `event: <name>`, then `data: <JSON>`, followed by a blank line:

| Event | JSON payload |
| --- | --- |
| `status` | `{stage,message}`; rewriting, retrieving, reranking, retrying, or generating |
| `chunks` | Array of the original `/ask` chunk objects; may be replaced after the one retry |
| `token` | `{text}`; provisional generated text |
| `answer_clean` | `{answer}`; replace all accumulated text when invalid markers were removed or the answer was withheld |
| `citations` | Array of validated `{path,startLine,endLine}` objects, after generation |
| `done` | `{notFound,latencyMs,llmCalls,rewrittenQuestion,rewriteMode,agenticUsed,retried,totalMs,cached,generationMode,rerankApplied}` |
| `error` | `{message,code?,retryAfter?}`; sanitized and terminal |

`latencyMs` retains exactly retrieve/rerank/generate. `totalMs` also includes rewrite, grading and provider-queue time. `llmCalls` counts actual text-provider attempts, including 429/5xx retries; it excludes embeddings and CPU model inference. A cached answer normally incurs zero new calls. A fallback carrying the same request ID reports its shared cumulative attempt count.

The server sends `: heartbeat` comments every 15 seconds while waiting, with `Cache-Control: no-cache` and `X-Accel-Buffering: no`. The parser handles split UTF-8, CRLF, multiline data, unknown future events and truncated streams. It treats explicit quota/validation errors as terminal. It falls back once for transport/unsupported-stream failures, preserving the request ID when the server supports streaming; a missing endpoint uses the legacy JSON shape.

The UI displays retrieved sources early and labels them separately from final validated citations. Stop aborts the fetch and closes the provider stream. A stopped partial response is kept with an explicit unfinished status and no model citations. Reloading it does not convert it into a completed answer. A CPU inference operation already executing in native code finishes its current operation; cancellation checkpoints prevent subsequent retrieval, reranking and generation work.

## Stateless memory

The browser stores conversations under `askrepo:` and sends only the last six completed user/assistant messages. The server independently keeps at most six messages and 6,000 content characters, truncates assistant messages to 1,200 characters and user messages to 500, and rejects unsupported roles. Assistant truncation retains the tail so file identifiers and citations can survive. HTTP bodies are capped at 32,768 bytes by default.

No history, or an already standalone question without follow-up pronouns/phrases, skips the rewrite model. Ambiguous follow-ups use `GEMINI_FAST_MODEL`; retrieval searches the standalone query, while generation sees the original question and recent history. History and repository text are untrusted data. Citations are permitted only within the current retrieved evidence, never merely because a previous answer cited a file.

Without a Gemini key, the explicitly extractive provider carries actual prior identifiers into the search query. This deterministic context expansion is reported as `rewriteMode:"context"`; it is not an LLM rewrite. New chat starts with an empty history.

## One retry and hard budgets

Strong retrieval requires the existing confidence gate, a top score of at least `ASKREPO_AGENTIC_GOOD_SCORE` (0.65), and at least two chunks scoring at least `ASKREPO_AGENTIC_LOWER_SCORE` (0.35). It skips the grader. Only weak retrieval can call the fast JSON grader. Malformed grader output defaults to sufficient, without overriding the original confidence gate.

A negative grade permits one retry with at most two distinct alternative queries. Candidates from the original and alternative searches are combined with RRF and optionally reranked against the standalone question. The retry is not recursive. Still-weak results return `notFound:true`, a helpful message, and the closest chunks. No-key mode uses ranking rules and lexical query variants; it does not pretend to run a Gemini grader.

`MAX_LLM_CALLS_PER_QUESTION=3` is a hard provider-attempt cap. Optional rewrite/grading reserve one call for the final answer. Smaller budgets skip optional model steps. SDK automatic retries are disabled; the application retries 429/5xx at most twice with exponential backoff, subject to the same cap. A provider stream is never replayed after its first text piece.

Provider requests share a global minute allowance, an allowance per actual ASGI peer IP, and a FIFO queue of at most 32 waiters with a two-second default wait. Exhaustion returns a structured `demo_limit` error: "Demo limit reached, try again in a minute". Forwarded headers are not blindly trusted. Behind a host proxy, peers can share one limit until trusted proxy addresses are configured explicitly.

Complete validated answers use a bounded, ten-minute in-memory cache. Keys include repository snapshot, normalized rewritten query, retrieval/model settings, original question and a digest of bounded history. Different conversation contexts do not share generated answers accidentally. Errors and interrupted answers are not cached. Cache and request-ID budgets are per process and disappear on restart; use one backend worker with embedded Qdrant.

## Configuration and future hosting

See `.env.example` for exact defaults. New variables are `GEMINI_FAST_MODEL`, optional `GEMINI_ANSWER_MODEL` (otherwise `ASKREPO_GEMINI_MODEL`), `MAX_LLM_CALLS_PER_QUESTION`, `AGENTIC_ENABLED`, `ASKREPO_AGENTIC_GOOD_SCORE`, `ASKREPO_AGENTIC_LOWER_SCORE`, `ASKREPO_LLM_GLOBAL_RPM`, `ASKREPO_LLM_PER_IP_RPM`, `ASKREPO_LLM_QUEUE_WAIT_SECONDS`, `ASKREPO_LLM_MAX_QUEUED`, `ASKREPO_LLM_MAX_RETRIES`, `ASKREPO_LLM_RETRY_BACKOFF_SECONDS`, `ASKREPO_ANSWER_CACHE_SIZE`, and `ASKREPO_ANSWER_CACHE_TTL_SECONDS`.

For Render/Vercel hosting, follow [the deployment guide](../docs/DEPLOY.md).
Set the exact frontend origin in `ASKREPO_CORS_ORIGINS` and build the frontend
with the direct Render API URL. Both streaming and JSON POSTs use the same CORS
policy. Keep provider/admin keys in backend secrets. See the guide for actual
live smoke output; successful local tests alone do not prove hosted behavior.

Free-tier quotas and availability depend on the provider/project. Limits are configurable safeguards, not a promise of unlimited free calls. `LITE_MODE=true` avoids local neural models and skips reranking, but uses Gemini embedding quota as well as text-generation quota. Qdrant Cloud stores vectors; files, registry and BM25 still need persistent backend storage. Keep agentic mode opt-in, or set `AGENTIC_ENABLED=false` to disable it server-wide.

References: [Gemini text generation](https://ai.google.dev/gemini-api/docs/text-generation), [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [fast model](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite), [Render Docker](https://render.com/docs/docker).
