# AskRepo frontend

A repository question-and-answer workspace built with React, TypeScript, TanStack Start, Tailwind, and shadcn/ui. See the [project README](../README.md) for backend setup, API contracts, architecture, milestone status, and limitations.

## Develop

Copy .env.example to .env, then:

    npm ci
    npm run dev

Open http://localhost:5173. Dark mode defaults to pure black; use the header toggle for light mode.

VITE_USE_MOCK=false sends custom repository requests to VITE_API_BASE_URL. Demo cards always open clearly labeled illustrative fixtures. Set VITE_USE_MOCK=true to simulate custom indexing too. Restart Vite after changing env values.

All frontend requests go through src/api.ts. Conversation history, settings, and theme preferences use askrepo: localStorage keys. Legacy keys migrate once without overwriting newer values.

## Verify

    npm test
    npm run typecheck
    npm run build
    npm run test:e2e

Browser tests use installed Microsoft Edge on Windows and Playwright Chromium elsewhere. Run npx playwright install chromium once on non-Windows hosts. Start the backend on port 7860 to include the live integration smoke test.

The npm lockfile is the dependency source of truth. The app retains its original Lovable TanStack Start build configuration and connection instructions in AGENTS.md.
