# API reference

## API

CamelCase JSON; `/docs` is the executable OpenAPI contract.

| Endpoint | Contract |
| --- | --- |
| `POST /index` | `{repoUrl}` → `{jobId,repoId}` |
| `GET /index/{jobId}` | `{status,filesParsed,chunksCreated,error?,queued}`; status is cloning/parsing/chunking/embedding/ready/failed |
| `POST /ask` | `{repoId,question,topK?:8,hybrid?:true,rerank?:true}` → `{answer,citations,chunks,notFound,latencyMs,generationMode,rerankApplied}` |
| `POST /ask/stream` | Ask body plus optional history/agentic/requestId; POST SSE status, chunks, token, answer_clean, validated citations, done, and sanitized error events |
| `GET /file?repoId=…&path=…` | `{content,language}` from the immutable source snapshot |
| `GET /repos` | Ready repositories with `repoId,repoUrl,files,chunks,indexedAt` |
| `GET /files?repoId=…` | Stored source paths/languages for the file tree |
| `POST /compare` | Ask input → independent `{bm25:[chunks],vector:[chunks],hybrid:[chunks]}` without generation |
| `GET /health` | Liveness and configured generation mode; does not trigger model downloads |

`citations` are `{path,startLine,endLine}`. Returned `chunks` add `{score,method,code}` with BM25/vector/hybrid/reranked method labels. `latencyMs` contains retrieve, rerank, and generate timings. The optional `retrievalMode` request field selects `bm25`, `vector`, or `hybrid` directly; existing `hybrid=false` requests continue to mean BM25-only. The original backend contract's `repoId`, `notFound`, and latency fields are retained even though the short frontend reference prompt omitted them. The frontend uses POST SSE for live answers and can fall back once to `/ask` for transport or unsupported-endpoint failures.

Questions are nonblank and at most 500 characters; Top K is 1–50 (the UI exposes 3–20). Unknown resources return 404, repositories not ready or indexes with incompatible settings return 409, malformed inputs return 422, queue/rate limits return 429, oversized bodies return 413, and unavailable providers return a sanitized 503. Secrets use `SecretStr` and are not returned in errors.


The health response also includes cached `demoRepos`, `bootstrapEnabled`, and `indexingMode`. It performs no model or network calls. See [deployment](DEPLOY.md) for readiness and proxy behavior.
