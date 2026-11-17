# Deploy AskRepo

The live frontend is https://askrepo-murex.vercel.app and the API is
https://askrepo-api.onrender.com. Deployment configuration and smoke-test evidence
will be recorded here as the reliability milestones are completed.

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
