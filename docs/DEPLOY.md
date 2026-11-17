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
