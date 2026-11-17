# Configuration reference

Copy `backend/.env.example` to ignored `backend/.env` for local use. The example chooses current Gemini model overrides; code defaults may remain legacy for compatibility. Hosting configuration is in [DEPLOY.md](DEPLOY.md). Never commit real keys.

| Variable | Example value | Purpose |
| --- | --- | --- |
| `ASKREPO_DATA_DIR` | `data` | Writable source, SQLite, BM25 and local-vector directory; needs durable storage to persist. |
| `ASKREPO_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | JSON array of exact frontend origins, without trailing slashes. |
| `ASKREPO_TRUSTED_PROXIES` | `` | Comma-separated trusted proxy CIDRs; * is direct-platform-ingress trust only. |
| `ASKREPO_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local CPU embedding model in full mode. |
| `ASKREPO_RERANKER_MODEL` | `BAAI/bge-reranker-base` | Local CPU cross-encoder model; disabled in lite mode. |
| `ASKREPO_INDEXING_CONCURRENCY` | `1` | Number of indexing workers. Keep 1 on small hosts. |
| `ASKREPO_INDEXING_MODE` | `open` | open locally; allowlist or token for a public demo. |
| `ASKREPO_ADMIN_TOKEN` | `` | Backend-only secret for X-Admin-Token in token mode; never commit a real value. |
| `ASKREPO_LITE_MAX_REPO_BYTES` | `20971520` | Total repository byte cap applied in lite mode, in addition to regular limits. |
| `ASKREPO_LITE_MAX_FILES` | `1500` | Total file cap in lite mode; checked before checkout and source loading. |
| `ASKREPO_MAX_NEW_REPOS_PER_DAY` | `20` | Distinct admitted URLs per UTC day across clients; ledger needs persistent SQLite. |
| `ASKREPO_MAX_FILE_BYTES` | `307200` | Skip individual source files larger than this byte count. |
| `ASKREPO_MAX_REPO_BYTES` | `104857600` | Maximum total tracked/read repository bytes before filtering. |
| `ASKREPO_MAX_FILES` | `10000` | Maximum total tracked/read repository file count before filtering. |
| `ASKREPO_CLONE_TIMEOUT_SECONDS` | `180` | Maximum seconds allowed for Git cloning and checkout. |
| `ASKREPO_MAX_CLONE_BYTES` | `209715200` | Maximum on-disk clone size, including Git objects. |
| `ASKREPO_CHUNK_STRATEGY` | `ast` | Chunking strategy: ast or fixed. |
| `ASKREPO_MAX_CHUNK_CHARS` | `6000` | Maximum characters per source chunk. |
| `ASKREPO_MAX_QUEUED_JOBS` | `20` | Pending queue capacity in addition to active workers. |
| `ASKREPO_BOOTSTRAP_DEMOS` | `false` | Rebuild missing/stale demo artifacts in the background; enable on ephemeral hosting. |
| `ASKREPO_DEPLOYMENT_ID` | `local` | Stable unique deployment name; separates deterministic demo IDs across deployments. |
| `ASKREPO_DEMO_REPOS` | `["https://github.com/ShlokMaharwal/Seekr","https://github.com/ShlokMaharwal/CodeNest","https://github.com/ShlokMaharwal/DPTrace"]` | JSON array of canonical public GitHub demo URLs; also the indexing allowlist. |
| `ASKREPO_BOOTSTRAP_RETRY_SECONDS` | `60` | Initial background retry delay; exponential backoff is capped at one hour. |
| `ASKREPO_GEMINI_EMBEDDING_BATCH_SIZE` | `32` | Maximum texts per Gemini embedding request, at most 32. |
| `ASKREPO_GEMINI_EMBEDDING_RPM` | `10` | Embedding requests per minute, separately paced from generation. |
| `ASKREPO_GEMINI_EMBEDDING_RETRIES` | `3` | Bounded retries for transient embedding provider errors. |
| `ASKREPO_GEMINI_EMBEDDING_BACKOFF_SECONDS` | `5` | Initial exponential embedding retry delay; failed batches can resume. |
| `ASKREPO_MODEL_THREADS` | `4` | CPU threads used by local neural models. |
| `ASKREPO_MODEL_CACHE` | `data\models` | Local full-mode model cache; Docker uses /opt/models. |
| `ASKREPO_GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Gemini embedding model used by lite mode; output dimension is 768. |
| `ASKREPO_FUSION_THRESHOLD` | `0.55` | Confidence gate for normalized hybrid RRF scores. |
| `ASKREPO_BM25_THRESHOLD` | `0.15` | Confidence gate for normalized keyword scores. |
| `ASKREPO_VECTOR_THRESHOLD` | `0.55` | Confidence gate for vector similarity scores. |
| `ASKREPO_RERANK_THRESHOLD` | `0.2` | Confidence gate for local cross-encoder scores. |
| `ASKREPO_GEMINI_MODEL` | `gemini-3.5-flash-lite` | Fallback generation model. Example selects a current model; code default is legacy. |
| `GEMINI_FAST_MODEL` | `gemini-3.5-flash-lite` | Rewrite/grader model override; verify availability for your Gemini project. |
| `GEMINI_ANSWER_MODEL` | `gemini-3.5-flash-lite` | Final-answer model override; empty falls back to ASKREPO_GEMINI_MODEL. |
| `MAX_LLM_CALLS_PER_QUESTION` | `3` | Hard cap on text-provider attempts, including retries, per logical question. |
| `AGENTIC_ENABLED` | `true` | Server-wide agentic switch; public demo recommends false. |
| `ASKREPO_AGENTIC_GOOD_SCORE` | `0.65` | Top score required to skip the optional model grader. |
| `ASKREPO_AGENTIC_LOWER_SCORE` | `0.35` | Lower threshold required for at least two chunks in the cheap grading rule. |
| `ASKREPO_LLM_GLOBAL_RPM` | `10` | Global text-provider requests per minute, excluding embedding calls. |
| `ASKREPO_LLM_PER_IP_RPM` | `6` | Text-provider requests per resolved client IP per minute. |
| `ASKREPO_LLM_QUEUE_WAIT_SECONDS` | `2` | Maximum seconds to wait in the provider quota queue. |
| `ASKREPO_LLM_MAX_QUEUED` | `32` | Maximum provider-quota waiters. |
| `ASKREPO_LLM_MAX_RETRIES` | `2` | Retries for transient text-provider errors; also bounded by the question cap. |
| `ASKREPO_LLM_RETRY_BACKOFF_SECONDS` | `0.5` | Initial exponential text-provider retry delay. |
| `ASKREPO_ANSWER_CACHE_SIZE` | `128` | Maximum complete validated answers cached in memory; zero disables caching. |
| `ASKREPO_ANSWER_CACHE_TTL_SECONDS` | `600` | Lifetime in seconds of complete validated cached answers. |
| `ASKREPO_LLM_PROVIDER` | `auto` | auto selects Gemini when a key exists, otherwise source excerpts; gemini or extractive also supported. |
| `ASKREPO_MAX_CONTEXT_CHARS` | `100000` | Total generation context character budget. |
| `ASKREPO_ASK_RATE_PER_MINUTE` | `30` | API requests per resolved IP per minute; compare costs three units. |
| `ASKREPO_INDEX_RATE_PER_MINUTE` | `5` | Index API requests per resolved IP per minute. |
| `ASKREPO_MAX_REQUEST_BYTES` | `32768` | Maximum JSON request body size in bytes. |
| `ASKREPO_QUANTIZE_MODELS` | `false` | Optional full-mode CPU int8 quantization. |
| `ASKREPO_QUANTIZE_LINEARS` | `true` | Include linear layers in int8 quantization; false quantizes embedding tables only. |
| `ASKREPO_EMBEDDING_BATCH_SIZE` | `16` | Local full-mode embedding batch size. |
| `ASKREPO_RERANKER_BATCH_SIZE` | `4` | Local full-mode reranker batch size. |
| `ASKREPO_EMBEDDING_MAX_LENGTH` | `512` | Local embedding input token cap; changing it requires compatible fresh indexes. |
| `ASKREPO_RERANKER_MAX_LENGTH` | `512` | Local reranker input token cap. |
| `LITE_MODE` | `false` | Use Gemini embeddings and omit local neural models. Also set this at Docker build time. |
| `GEMINI_API_KEY` | `` | Gemini secret. Add only to ignored local .env or hosting secrets. |
| `QDRANT_URL` | `` | Empty uses local Qdrant. Cloud example: https://YOUR_CLUSTER_HOSTNAME:443. |
| `QDRANT_API_KEY` | `` | Database API key with collection write permission; never commit a real value. |

Frontend public build settings are `VITE_API_BASE_URL` and `VITE_USE_MOCK`. Changes require rebuilding the frontend. Keep provider/admin keys out of all `VITE_*` values.
