import type { Page } from "@playwright/test";
import { demoFiles, mockApi } from "../src/lib/demo";

export const API_PATTERN = /^http:\/\/(localhost|127\.0\.0\.1):7860\//;
const repoId = "a".repeat(32);
const headers = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
};

export async function installFixtureAPI(page: Page) {
  let polls = 0;
  await page.route(API_PATTERN, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    let json: unknown;
    switch (url.pathname) {
      case "/health":
        json = {
          status: "ok",
          service: "askrepo",
          mode: "ready",
          generation: "test-contract",
          liteMode: false,
        };
        break;
      case "/repos":
        json = [
          {
            repoId,
            repoUrl: "https://github.com/ShlokMaharwal/Seekr",
            files: 5,
            chunks: 7,
            indexedAt: "2026-11-02T00:00:00Z",
          },
        ];
        break;
      case "/index":
        json = { repoId, jobId: "fixture-job" };
        break;
      case "/index/fixture-job": {
        const statuses = ["cloning", "parsing", "chunking", "embedding", "ready"];
        const stage = Math.min(polls++, 4);
        json = {
          status: statuses[stage],
          filesParsed: stage > 0 ? 5 : 0,
          chunksCreated: stage > 1 ? 7 : 0,
          queued: false,
        };
        break;
      }
      case "/files":
        json = Object.keys(demoFiles).map((path) => ({ path, language: "typescript" }));
        break;
      case "/file":
        json = await mockApi.file(repoId, url.searchParams.get("path") ?? "");
        break;
      case "/ask":
        json = await mockApi.ask(request.postDataJSON());
        break;
      case "/ask/stream": {
        const input = request.postDataJSON();
        const answer = await mockApi.ask(input);
        const event = (name: string, data: unknown) =>
          `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
        const rewritten =
          input.history?.length && /that|what about|and where/i.test(input.question)
            ? "Where is URLFrontier.enqueue called?"
            : input.question;
        const stream =
          event("status", { stage: "retrieving", message: "Searching your repository" }) +
          event("chunks", answer.chunks) +
          event("status", { stage: "generating", message: "Answering from the retrieved code" }) +
          event("token", { text: answer.answer }) +
          event("citations", answer.citations) +
          event("done", {
            notFound: answer.notFound,
            latencyMs: answer.latencyMs,
            llmCalls: 1,
            rewrittenQuestion: rewritten,
            generationMode: "test-contract",
            cached: false,
          });
        await route.fulfill({ body: stream, contentType: "text/event-stream", headers });
        return;
      }
      case "/compare":
        json = await mockApi.compare(request.postDataJSON());
        break;
      default:
        await route.fulfill({ status: 404, json: { detail: "Fixture route not found" }, headers });
        return;
    }
    await route.fulfill({ json, headers });
  });
}
