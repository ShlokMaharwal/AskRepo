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
