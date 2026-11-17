# Record the AskRepo demo

The README capture is intentionally a placeholder until a real run is recorded.

1. Open the live app with a 1440 x 900 browser viewport. Wait until health and all
   demo readiness states are ready; keep API-key/settings pages out of view.
2. Start a screen recording. Open Seekr and ask: "How does the Redis URL frontier
   queue work?" Capture the real streamed response; do not substitute mock text.
3. Click a citation to show its exact file and highlighted line range. Expand
   Retrieval details, then ask "and where is that called?" to show query rewriting.
4. Record about 20-40 seconds, trimming waiting time transparently. Do not alter
   answers, citations, scores or elapsed-time labels. A screenshot can show the
   completed chat and code viewer instead.
5. Export an optimized GIF to `docs/assets/askrepo-demo.gif` (or a PNG screenshot
   to `docs/assets/askrepo-demo.png`). Aim below 8 MB. Create the assets directory
   when adding the actual file; no artificial capture is checked in.
6. Replace the README placeholder with this Markdown after the file exists:

```markdown
![AskRepo streaming a real repository answer with exact source citations](docs/assets/askrepo-demo.gif)
```

Verify the capture contains no secrets or unrelated private windows. Commit the
capture and README update together.
