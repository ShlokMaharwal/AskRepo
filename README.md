# AskRepo

Ask questions about a GitHub codebase and get answers with exact file and line citations.

[![AskRepo checks](https://github.com/ShlokMaharwal/AskRepo/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ShlokMaharwal/AskRepo/actions/workflows/ci.yml)

**[Open the live app](https://askrepo-murex.vercel.app/)** · [API docs](https://askrepo-api.onrender.com/docs) · [API health](https://askrepo-api.onrender.com/health)

> **Screenshot/GIF placeholder:** record a real streamed answer and citation click.
> Follow [the exact capture instructions](docs/RECORDING.md), then add the recorded asset here.

## What makes it different

- **AST-aware chunking:** preserves functions, classes, imports and source-line provenance, with fixed-window fallback.
- **Hybrid retrieval:** combines BM25 keyword search and vector search using reciprocal-rank fusion.
- **Checked citations:** generated references must point into current repository evidence; the UI opens exact file ranges.
- **Evaluation harness:** compares chunking and retrieval modes, records model/source provenance, and keeps draft relevance labels explicit.

The React/TanStack Start interface provides black dark mode, light mode, indexing
progress, streamed answers with Stop, follow-up memory, retrieval details, and a
responsive source viewer. FastAPI handles ingestion, retrieval and generation.

## Live deployment and limits

The public app uses **Vercel + Render Free + Qdrant Cloud + Gemini**. Render runs
Docker in lite mode, with Gemini embeddings and generation and no local reranker.
The [deployment guide](docs/DEPLOY.md) and [render.yaml](render.yaml) describe the
reproducible configuration, including demo bootstrap, indexing restrictions and
proxy-aware rate limiting. Source code and local checks alone do not prove that
new settings are active on the hosted service; see the guide's Last verified entry.

Free hosting can sleep and cold starts can take about a minute. The UI retries
health checks and shows readiness rather than a blank page. Render disk is
ephemeral: enable demo bootstrap to rebuild files, BM25 and registry data after a
reset. Stable demo IDs replace their own vector collections without touching
unrelated collections. Quotas can delay preparation; bootstrap and provider
retries are bounded/backed off. Browser chat history can outlive a lost snapshot.

| Capability | Local full mode | Deployed lite mode |
| --- | --- | --- |
| Embeddings | Local BGE CPU model | Gemini `gemini-embedding-001`, 768 dimensions |
| Reranker | Optional BGE cross-encoder | Disabled |
| Vectors | Local Qdrant or configured cloud | Qdrant Cloud |
| Generation | Gemini when configured; source excerpts without a key | Gemini; deployment overrides currently select `gemini-3.5-flash-lite` |
| Storage | Local directory or Docker volume | Ephemeral Render files; bootstrap is required for recovery |
| Public indexing | Open by default | Blueprint recommends demo allowlist |
| Evaluation applicability | Historical BGE CPU results | Requires the separate deployed-lite profile |

## Run locally

For a complete Docker stack, install Docker and Compose v2.24+ and run:

```powershell
docker compose --profile frontend up --build
```

This starts backend, Qdrant and the frontend dev server with named data volumes.
Full mode needs sufficient RAM for local models. For lite mode, put a Gemini key
in ignored `backend/.env`, set `$env:LITE_MODE="true"` before the command, and build
again. Open [localhost:5173](http://localhost:5173) and
[localhost:7860/docs](http://localhost:7860/docs).

For Python 3.11/Node 22 setup without Docker, model preparation, and test commands,
see [local development](docs/LOCAL_DEVELOPMENT.md). Container configuration is
validated; local Docker startup still requires a running daemon.

## Evaluation

Relevance labels for all 45 standalone questions and 15 follow-ups remain
**drafts requiring manual review**. Do not interpret historical local BGE or
extractive-provider measurements as deployed Gemini quality. Full measured
results, provenance, protocols and limitations are in
[the evaluation reference](docs/EVALUATION.md) and
[the review checklist](backend/eval/REVIEW.md).

<!-- ASKREPO:DEPLOYED:EVAL:START -->
The deployed-lite benchmark and automated Gemini faithfulness audit are being
prepared. No deployed-lite result is claimed until a completed measured report is saved.
<!-- ASKREPO:DEPLOYED:EVAL:END -->

## Verify a deployment

```powershell
.\.venv\Scripts\python.exe scripts/smoke_deploy.py https://askrepo-api.onrender.com https://askrepo-murex.vercel.app --wait-seconds 1800
```

The smoke script checks health, ready demos, CORS, cited JSON answers and SSE.
It does not create repositories and exits nonzero on failure. The manual
[deployment-check workflow](.github/workflows/smoke-deploy.yml) runs the same command.
A passing structural check is not human validation of answer faithfulness.

## Reference

- [Deployment, cold starts, proxy trust, quotas and troubleshooting](docs/DEPLOY.md)
- [All configuration variables](docs/CONFIGURATION.md)
- [Architecture and limits](docs/ARCHITECTURE.md)
- [API contract](docs/API.md)
- [Chunking, retrieval and streaming](docs/RETRIEVAL.md)
- [SSE transport details](backend/STREAMING.md)
- [Local development and tests](docs/LOCAL_DEVELOPMENT.md)
- [Evaluation instructions and measured reports](docs/EVALUATION.md)
- [Initial deployment audit](docs/AUDIT.md)
- [Suggested GitHub description, website and topics](docs/REPO_METADATA.md)

There is no user authentication, distributed job queue or distributed quota
ledger. Public deployments should use allowlist/token indexing and one backend
worker. Structural citation validity does not establish semantic faithfulness.
