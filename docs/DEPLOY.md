# Deploy AskRepo

The live frontend is https://askrepo-murex.vercel.app and the API is
https://askrepo-api.onrender.com. The checked-in Blueprint prepares this topology. A source commit or Blueprint
validation does not prove that new code or settings are running on those URLs.
See Last verified for actual live smoke output.


## 1. Qdrant Cloud and Gemini

Create a free Qdrant Cloud cluster and a **Database API key** with permission to
create/write collections. Use a dedicated cluster for this app, or a distinct
`ASKREPO_DEPLOYMENT_ID` if deployments share a cluster. The backend uses the REST
endpoint, for example `https://YOUR_CLUSTER_HOSTNAME:443`.

Create a Gemini key in [AI Studio](https://aistudio.google.com/apikey). Verify your
project can use `gemini-embedding-001` and `gemini-3.5-flash-lite` and inspect its
active quotas. Generation and embeddings have separate limits; the application
paces embeddings and retries transient 429/5xx errors, but cannot grant quota.
Never paste keys into GitHub, frontend variables, screenshots, or issue logs.

## 2. Render Blueprint

For a new installation, open Render **New > Blueprint**, connect this GitHub
repository, select `main`, and review the resources from root `render.yaml`.
It defines a Docker web service rooted at `backend`, the free compute plan,
`/health`, lite mode, demo bootstrap, allowlist indexing, and proxy settings.
The Docker build arguments come from service environment variables, so lite mode
must be present before building. Leave the Docker command override empty.

During setup, supply the `sync: false` values:

| Variable | Value |
| --- | --- |
| `GEMINI_API_KEY` | Your fresh Gemini key |
| `QDRANT_URL` | Your HTTPS cluster REST endpoint |
| `QDRANT_API_KEY` | Your Database API key |
| `ASKREPO_CORS_ORIGINS` | JSON array of the exact frontend origin; update after Vercel assigns it |
| `ASKREPO_ADMIN_TOKEN` | A generated backend-only secret if token mode is used |

Allowlist mode does not use the admin token; it can be left empty if the setup UI
allows it. On an **existing** Render service, do not create a duplicate service
blindly. Apply the checked-in settings to that service and supply newly added
secret/environment values manually. Render ignores `sync: false` values during
updates to existing Blueprints. Review resource names and changes before syncing.

Validate structure without deploying:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe scripts/validate_deploy.py
```

The validator downloads Render's current official JSON Schema. Schema validation
passed locally on November 17, 2026. This checks structure, not account quotas,
resource ownership, or successful container execution. Field names were checked
against the [Blueprint reference](https://render.com/docs/blueprint-spec).

## 3. Vercel frontend

Import the same GitHub repository. Set root directory `frontend`, framework
preset **Other**, Node **22.x**, install command `npm ci`, and build command
`npm run build:vercel`. Leave the output-directory override disabled; Nitro emits
`.vercel/output`. No additional `vercel.json` is needed for this build target.

Set these public build variables before deploying, substituting your API URL:

```dotenv
VITE_API_BASE_URL=https://askrepo-api.onrender.com
VITE_USE_MOCK=false
```

Keep API keys and the admin token exclusively in the backend. Changing `VITE_*`
requires a frontend rebuild. The browser calls Render directly for SSE; no Vercel
serverless proxy is involved.

## 4. Exact CORS value and first boot

Set this **value only** in Render for the live frontend, without an equals sign,
backticks, extra outer quotes, or a trailing slash in the origin:

```json
["https://askrepo-murex.vercel.app"]
```

The variable name is `ASKREPO_CORS_ORIGINS`. Use your actual assigned domain for a
new installation; add each custom/preview origin explicitly. Save and redeploy.

Enable `ASKREPO_BOOTSTRAP_DEMOS=true`, keep a stable unique deployment ID, and
leave `ASKREPO_INDEXING_MODE=allowlist`. The API starts immediately and `/health`
reports queued/indexing/failed/ready states without contacting models or Qdrant.
The background coordinator checks local files, BM25, embedding profile, and the
configured demo collection's point count, then queues one rebuild at a time.
A first boot can take several minutes or longer under embedding quotas. Failed
batches resume from matching checkpoints while local artifacts survive; after a
complete disk reset they must be recreated. Retries back off automatically.

Future demo rebuilds replace only their own stable target collection. Unknown
legacy/random-ID collections cannot be safely attributed after registry loss and
are not deleted automatically. Review them manually in a dedicated cluster;
never clear unrelated collections to make bootstrap pass.

## 5. Verify the deployment

Open the frontend, `/health`, and `/docs`; the API's `/` can return 404. Once the
three demos report ready, run:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_deploy.py https://askrepo-api.onrender.com https://askrepo-murex.vercel.app --wait-seconds 1800
```

The script makes public reads and two question requests. It does not create or
delete repositories. It checks frontend response, demo readiness, stream CORS,
`/repos`, a JSON answer with real source-file bounds, and required SSE events with
validated citation ranges. It exits nonzero on missing demos, not-found answers,
provider failures, invalid citations, or incomplete streams. Passing establishes
structural behavior, not semantic faithfulness. The manual **Check live
deployment** GitHub Action runs the same check with URL inputs and no cloud keys.

Then test the UI: open a demo, ask a code question, follow a citation, ask a
follow-up, press Stop, and reload history. Restart Render and repeat once the
bootstrap states return to ready. Only that restart test proves recovery on the
actual hosting platform.

## Local Compose stack

Install Docker Engine/Desktop and Compose v2.24 or newer. From the project root:

```powershell
docker compose --profile frontend up --build
```

This starts the full CPU backend, a pinned Qdrant service, and an optional frontend
dev server. Full mode needs the RAM described in the local setup. To use lite mode
on a smaller machine, first add a Gemini key to ignored `backend/.env`, then:

```powershell
$env:LITE_MODE="true"
docker compose --profile frontend up --build
```

Compose's build argument comes from the shell/root Compose environment, not
`backend/.env`; it must agree with runtime lite mode. Backend and Qdrant data use
named volumes. Compose overrides cloud Qdrant values with its local service and
uses a development-only API key, so it does not modify your cloud collections.
Ports bind to localhost. Open `http://localhost:5173` and
`http://localhost:7860/docs`. Omit `--profile frontend` to run only backend/Qdrant.
`docker compose down` retains data; adding `-v` deletes the named volumes.

Compose configuration passed `docker compose config --quiet`. Container startup
has not been verified locally because the Docker daemon is unavailable.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Waking banner | Wait for `/health`; the app retries with backoff and preserves the page. |
| Demos stay indexing | Inspect Render job logs, Gemini embedding quota/key/model access, Qdrant write permission, and repository limits. Keep RPM within your project's allowance. |
| Demo failed | Bootstrap retries automatically. Matching vector checkpoints resume; repeated provider failures need corrected credentials/quota. |
| CORS SettingsError | Use a JSON array as the value; do not paste `ASKREPO_CORS_ORIGINS=` into the value box. |
| Frontend calls localhost | Correct `VITE_API_BASE_URL`, then rebuild Vercel. |
| 429 response | Distinguish API, text-provider, embedding, and daily-index limits. Respect Retry-After/quotas rather than repeatedly indexing. |
| PyTorch in a lite build | Set `LITE_MODE=true` before rebuilding the Docker image. |
| Files disappear | Free disk is ephemeral; allow bootstrap to finish after restart. Qdrant alone cannot restore files/BM25/SQLite. |
| Old saved chat cannot open files | Reopen the rebuilt demo and start a new chat; old random snapshot IDs may no longer exist. |
| Wrong client buckets | Confirm trusted-proxy settings and the Docker command below; do not trust arbitrary forwarded headers on a public direct socket. |

## Last verified

The final live smoke output and restart evidence will be recorded here after the
new reliability release is actually published and tested. Local tests and a
successful build must not be presented as proof of live deployment.

## Optional keep-alive

An external HTTP monitor can request `GET /health` every ten minutes. Configure
the actual backend URL, require HTTP 200, and do not call `/index` or `/ask` from a
pinger. This can reduce idle cold starts while traffic reaches the service.
It does not guarantee uptime or persistent disk, prevent platform restarts, or
increase Gemini/Qdrant quotas. Continuous activity consumes Render's included
instance hours and bandwidth. Check the current free-tier terms before enabling
a monitor. The app handles waking without requiring a pinger.

Sources: [Render free limits](https://render.com/docs/free),
[Render web services](https://render.com/docs/web-services).

## Proxy-aware rate limits

Set `ASKREPO_TRUSTED_PROXIES=*` only on Render's controlled public ingress, which
must append or overwrite X-Forwarded-For with the actual client. Here `*` trusts
the direct platform peer and uses the rightmost address; it does not trust a
client-supplied leftmost address. On a self-managed multi-hop setup, specify the
actual comma-separated proxy CIDRs instead. The resolver walks from right to
left and returns the first address outside those CIDRs. An untrusted direct peer,
duplicate/oversized/malformed header, or invalid address falls back to the peer.
IPv4, IPv6 and IPv4-mapped IPv6 are handled consistently. No trusted proxies is
the local default.

Docker enables Uvicorn proxy-header middleware with an intentionally empty
`--forwarded-allow-ips ''`. This preserves the original socket peer for the
application's resolver and avoids trusting/reprocessing the same header twice.
Do not replace this with Uvicorn's `*`, which would discard that evidence before
the application checks it. Both API and text-provider limits use the resolved
address. Startup logs the active mode without credentials.

## Public indexing policy

Local development defaults to `ASKREPO_INDEXING_MODE=open`. For the public demo,
use `allowlist`: only URLs in `ASKREPO_DEMO_REPOS` can be indexed. `token` permits
indexing new repositories only with `X-Admin-Token` matching the backend-only
`ASKREPO_ADMIN_TOKEN`; querying is public in every mode. The browser does not
collect or store the admin token. Already prepared demos can still be opened.

Lite ingestion is capped at 20 MB and 1,500 total files, or stricter regular
limits, before checkout and again when reading sources. Configure these with
`ASKREPO_LITE_MAX_REPO_BYTES` and `ASKREPO_LITE_MAX_FILES`.
`ASKREPO_MAX_NEW_REPOS_PER_DAY` bounds distinct repository URLs admitted per UTC
day, including bootstrap, across all clients. Failed attempts consume a slot;
retrying the same URL does not consume another. This ledger is SQLite-backed,
not distributed. It survives restarts only if the registry survives; ephemeral
disk loss resets it. Keep allowlist mode enabled to bound abuse across resets.
