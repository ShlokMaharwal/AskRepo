# Deployment audit

Inspected November 17, 2026, before reliability changes.

- `Storage` keeps the registry in SQLite and saves source files and chunks under
  `ASKREPO_DATA_DIR/repos/<id>`. BM25 and embedded Qdrant are local files too.
  Qdrant Cloud preserves only vectors. A surviving cloud collection cannot restore
  a lost registry, source files, or BM25. The initial implementation did not check
  these artifacts when listing ready repositories.
- Startup marked interrupted indexing failed and did not recreate demo indexes.
  `scripts/preindex.py` was an explicit local CLI. Random repository IDs could
  leave cloud collections behind after an ephemeral filesystem reset.
- Both the request guard and text-provider quota used the ASGI `client` address.
  Docker explicitly disabled Uvicorn proxy headers. This prevents spoofing but
  puts clients behind a hosting proxy in the same rate-limit bucket.
- The frontend health query had no retries and polled every 30 seconds. HTTP
  requests allowed two minutes, but there was no waking/readiness banner or
  action gate. Demo cards could start indexing on demand. Streaming had Stop,
  heartbeats, and a transport fallback, but network failures were generic.
- Public indexing was unrestricted beyond per-IP, queue, file and clone limits.
  Gemini embeddings were batched but did not have application-owned pacing,
  bounded retries, or a resumable batch checkpoint.
- Existing evaluation uses local BGE CPU embeddings, optional BGE reranking,
  and draft relevance labels. Those measurements do not describe deployed lite
  mode. Credentialed Gemini answer quality has not yet been measured.

The implementation milestones and live checks must record their actual outcomes;
this audit is an observation of the starting state, not proof of completion.

## Milestone 1 evidence

Background demo preparation now checks source files, chunk/BM25 identities, the
embedding profile and collection point count. Health reads cached state only.
Completed vector batches have digest-bound checkpoints; retries resume them.
Configured demos use deployment-specific stable IDs after disk loss. Only their
own target collection is replaced during a rebuild. Legacy collections with
random IDs cannot safely be attributed after a registry is lost and are left
untouched for operator review; broad remote collection deletion is not enabled.

Local checks: Ruff passed; pytest **130 passed, 1 skipped** (Windows symlink
privilege); frontend typecheck, **17 unit tests**, and Node production build
passed. Stubbed tests cover non-blocking health, stale source/BM25/vector repair,
resume after failure, and preservation of an unrelated collection.
Credentialed read-only checks accessed Gemini model metadata and Qdrant collection
listing. These do not yet establish embedding or answer-generation quality.

## Reliability release status

Milestones 1–6 were committed separately and pushed to `main`: recovery,
cold-start UI, proxy-aware limits, public indexing policy, reproducible hosting,
and README/reference cleanup. The user's non-secret Render settings are saved.
Live health confirms bootstrap, lite mode and allowlist indexing; a non-demo
index request returned 403 and the frontend-origin preflight returned 200.

Milestone 7 tooling and quota recovery were published as `ed8e233`, but the
measurements remain **incomplete**. The actual Gemini embedding attempt saved
45 query and 64 document vectors before the daily input quota was exhausted.
The user chose to leave the free-tier run pending. The three freshly cloned AST
demo snapshots contain 3,618 chunks before reuse. Exact-input cloud caching and
long provider cooldowns now preserve work across ephemeral resets without
deleting unrelated collections. Tests exercise persistence, task/model
separation, bounded cache writes, input/token pacing, and daily-limit handling.
No AST experiment was promoted and no evaluation label was marked reviewed.

Milestone 8 local browser checks passed **10 tests**, with the optional live test
skipped. Final live smoke exited 1 because demos were not ready. Its actual output
and remaining steps are in [DEPLOY.md](DEPLOY.md#last-verified). Successful live
JSON/SSE answers and a successful Render restart remain **unverified** until
embedding quota permits completion. A green local test suite is not a substitute
for those checks. An additional recovery regression removes obsolete files when
a stable demo ID is rebuilt from a changed repository snapshot.
