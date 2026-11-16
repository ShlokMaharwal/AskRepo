# AskRepo frontend

A repository question-and-answer workspace built with React, TypeScript, TanStack Start, Tailwind, and shadcn/ui. See the [project README](../README.md) for backend setup, API contracts, architecture, milestone status, and limitations.

## Develop

Copy .env.example to .env, then:

    npm ci
    npm run dev

Open http://localhost:5173. Dark mode defaults to pure black; use the header toggle for light mode.

VITE_USE_MOCK=false sends repository requests to VITE_API_BASE_URL. Demo cards open ready backend snapshots or start real indexing. Set VITE_USE_MOCK=true to use isolated illustrative frontend fixtures and simulated progress. Restart Vite after changing env values.

All frontend requests go through src/api.ts. Conversation history, settings, and theme preferences use askrepo: localStorage keys. Legacy keys migrate once without overwriting newer values.

## Verify

    npm test
    npm run typecheck
    npm run build
    npm run test:e2e

Browser tests use installed Microsoft Edge on Windows and Playwright Chromium elsewhere. Run npx playwright install chromium once on non-Windows hosts. Deterministic tests intercept the API contract. The test server uses port 4173 with strict port checking; it does not reuse another project’s development server. To test an already running AskRepo production build on port 4173, set ASKREPO_E2E_REUSE=true.

For the live check, explicitly pre-index the demos, run the API on port 7860, add http://127.0.0.1:4173 to ASKREPO_CORS_ORIGINS, and set ASKREPO_LIVE_E2E=true. The API must use the same embedding profile as its indexed snapshots.

The Node production build starts with npm run start. npm run build:vercel prepares local Vercel build output without deploying it.

The npm lockfile is the dependency source of truth. The app retains its original Lovable TanStack Start build configuration and connection instructions in AGENTS.md.

## Streaming and follow-ups

The default real API path uses POST /ask/stream with fetch and ReadableStream. Status and retrieved sources appear before the answer completes; final citation chips are validated by the backend. Stop aborts the connection and preserves the response as an explicitly unfinished partial answer. Transport failures can fall back once to /ask. A reused request ID keeps compatible fallback attempts within the same provider-call budget; an older backend without the stream route receives only its legacy fields.

Conversations still live in askrepo: localStorage. Only the last six completed messages are sent, with long assistant text bounded. Follow-ups display Searching for when the backend rewrites the query. New chat starts without previous conversation context. Agentic retrieval is opt-in in settings and can be disabled by the server. Cached answers are marked in the response actions. See ../backend/STREAMING.md and the root README for configuration and quota behavior.

ASKREPO_E2E_PORT can select another isolated browser-test port, for example 4175, when a running app already uses 4173. The deterministic suite includes a real chunked HTTP fixture to verify live text and actual connection cancellation. Its synthetic fixture data is never used as retrieval benchmark evidence.
