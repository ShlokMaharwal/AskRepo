# Local development

## Local setup

Prerequisites: Python **3.11**, Git, Node **22.17+**, npm, and network access for the initial public model downloads. Full mode is intended for a CPU host with approximately 16 GB RAM. A memory-saving int8 profile is also available; lightweight mode avoids local neural models entirely.

PowerShell, from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 7860
```

Second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open [AskRepo](http://localhost:5173), [API docs](http://localhost:7860/docs), and [health](http://localhost:7860/health). If Python is installed outside PATH, substitute its Python 3.11 executable for `python`. On Linux/macOS use `python3.11`, `.venv/bin/python`, `cp`, and `npm` in place of the Windows command names. Keep the API working directory at `backend` so `.env` and relative data paths resolve consistently.

Optional explicit model prefetch:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts/download_models.py
```

The default frontend uses real HTTP requests (`VITE_USE_MOCK=false`). Demo cards use already indexed repositories when available and otherwise start real indexing. To exercise only the illustrative frontend fixtures, set `VITE_USE_MOCK=true` and restart Vite. Fixture scores and answers are never included in backend evaluation results. Historical browser demo workspaces retain their explicit `demo:` namespace and banner.


## Demo preparation

Run explicitly from the project root, with the API process stopped when using local Qdrant:

```powershell
.\.venv\Scripts\python.exe scripts/preindex.py
```

This queues Seekr, CodeNest, and DPTrace, prints real stage/counter progress, and skips already indexed URLs. Use `--repos Seekr` for one repository or `--force` for new snapshots. Then start the backend; demo cards open the indexed repositories immediately. Source repositories are never executed, built, or imported.


## Tests and local builds

Fast CI dependencies do not download neural models:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check backend scripts
.\.venv\Scripts\python.exe -m pytest -q backend
cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

Tests stub the embedding model, reranker and LLM while exercising actual local Qdrant persistence, the indexing queue, file store and API. Browser tests use installed Edge on Windows; elsewhere install Playwright Chromium with `npx playwright install chromium`. They cover the black/light themes, chat history, citation viewer, settings and mobile tabs. The isolated test server uses port 4173. The live backend test requires a running local API and that test origin in its CORS array; deterministic UI tests use intercepted contract responses. Set `ASKREPO_E2E_REUSE=true` only when intentionally testing an already running AskRepo build on port 4173.

Verified locally: backend **122 passed, 1 skipped** (Windows symlink privilege), clean Ruff, frontend **17 unit tests passed**, clean TypeScript and changed-component ESLint, and successful Node and Vercel artifact builds. All **8 browser scenarios passed against the built production app**, including a real Seekr answer over SSE with no JSON fallback, working source citations, follow-up history, New chat, Stop closing a chunked HTTP connection, and opening a demo while the repository list is still loading. A fresh `octocat/Hello-World` HTTP smoke test also passed real cloning, indexing, source retrieval, cited answering, missing-evidence handling, and clone cleanup. The demo-preparation CLI recognized all three completed real demo indexes. The Vercel artifact build only prepares local files; it does not deploy. Gemini and Qdrant Cloud integration tests use SDK substitutes. Render's Docker build and application startup succeeded; hosted checks verify the frontend, API docs, health, and CORS. Credentialed provider behavior and hosted end-to-end RAG remain outside those checks.

This workspace's ignored local `.env` points at the completed `data/eval-indexes/ast` snapshots and allows the browser-test origin on port 4173. Model weights and source/vector snapshots are generated local data. A clean clone should follow the setup and explicit pre-indexing commands above.

The default production build uses Nitro's Node server target. Start it with `npm run start` after `npm run build`. `npm run build:vercel` creates local Vercel Build Output API artifacts only; it does not deploy. The npm lockfile and `.npmrc` are authoritative for the retained Lovable starter's dependency graph. CI runs backend Ruff/pytest and frontend tests/typecheck/build.

