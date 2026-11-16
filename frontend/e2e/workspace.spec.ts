import { expect, test } from "@playwright/test";
import { createServer } from "node:http";
import { API_PATTERN, installFixtureAPI } from "./api-fixture";

test.beforeEach(async ({ page }) => {
  await installFixtureAPI(page);
  page.on("pageerror", (error) => console.log("Browser error:", error.message));
});

test("landing uses pure black, and the light preference persists", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true", {
    timeout: 90000,
  });
  await expect(page).toHaveTitle(/AskRepo/);
  await expect(page.getByRole("heading", { name: "AskRepo." })).toBeVisible();
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(0, 0, 0)");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: "test-results/screenshots/askrepo-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await page.reload();
  await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();
});

test("demo chat opens exact cited code, saves history, and handles missing evidence", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
  await page.getByRole("button", { name: /Seekr A search engine/ }).click();
  await page.getByRole("button", { name: /How does the URL frontier/ }).click();
  const source = page.locator(".citation-chip").first();
  await expect(source).toBeVisible({ timeout: 15000 });
  await source.click();
  await expect(page.getByRole("complementary", { name: "Code viewer" })).toContainText(
    "URLFrontier",
  );
  await expect(page.locator(".cited-line")).toHaveCount(20);
  await page.getByText("Retrieval details", { exact: true }).click();
  await page.getByLabel("Compare retrieval modes").check();
  await expect(page.locator(".comparison-grid")).toContainText("BM25");
  await page.getByRole("button", { name: "Helpful answer", exact: true }).click();
  await expect(page.getByRole("button", { name: "Helpful answer", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "Search settings" }).click();
  await expect(page.getByRole("dialog")).toContainText("Retrieval settings");
  await page.getByRole("switch", { name: "Reranker" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByText("Retrieval details", { exact: true }).click();
  await page.locator(".chat-scroll").evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.screenshot({ path: "test-results/screenshots/askrepo-chat.png", fullPage: true });
  await page.reload();
  await page.locator(".history-item").first().click();
  await expect(page.locator(".citation-chip").first()).toBeVisible();
  await expect(page.locator(".composer-bottom")).toContainText("Reranker off");
  await page
    .getByRole("textbox", { name: "Ask a question about the repository" })
    .fill("How does billing work?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByText("Not found in this repository", { exact: true })).toBeVisible();
});

test("mobile switches between chat and source without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
  await page.screenshot({ path: "test-results/screenshots/askrepo-mobile.png", fullPage: true });
  await page.getByRole("button", { name: /Seekr A search engine/ }).click();
  await page.getByRole("button", { name: /How are search results ranked/ }).click();
  await expect(page.locator(".citation-chip").first()).toBeVisible({ timeout: 15000 });
  await page.locator(".citation-chip").first().click();
  await expect(page.locator(".code-lines")).toBeVisible();
  await expect(page.locator(".chat-panel")).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: "test-results/screenshots/askrepo-mobile-code.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  await expect(page.locator(".chat-panel")).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("button", { name: "Close sidebar" })).toBeVisible();
});

test("index progress uses the HTTP contract and opens a cited chat", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
  await page
    .getByRole("textbox", { name: "Public GitHub repository URL" })
    .fill("https://github.com/owner/new-repo");
  await page.getByRole("button", { name: "Index repository", exact: true }).click();
  await expect(page.getByRole("progressbar", { name: "Indexing progress" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Meet your codebase." })).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ask a question about the repository" })
    .fill("How does the Redis frontier work?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".citation-chip").first()).toBeVisible();
});

test("opening a demo waits for the repository list without starting another index", async ({
  page,
}) => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let indexCalls = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/index") indexCalls++;
  });
  await page.route("**/repos", async (route) => {
    await gate;
    await route.fallback();
  });
  try {
    await page.goto("/");
    await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
    const demo = page.getByRole("button", { name: /Seekr A search engine/ });
    await demo.click();
    await expect(demo).toBeDisabled();
    expect(indexCalls).toBe(0);
    release();
    await expect(page.getByRole("heading", { name: "Meet your codebase." })).toBeVisible();
    expect(indexCalls).toBe(0);
  } finally {
    release();
  }
});

test("live backend answers a pre-indexed real repository with working citations", async ({
  page,
}) => {
  test.skip(
    process.env["ASKREPO_LIVE_E2E"] !== "true",
    "Opt in after explicitly pre-indexing the demo repositories",
  );
  await page.unroute(API_PATTERN);
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
  await page.getByRole("button", { name: /Seekr A search engine/ }).click();
  await expect(page.getByRole("heading", { name: "Meet your codebase." })).toBeVisible();
  await page.getByRole("button", { name: "Search settings" }).click();
  const reranker = page.getByRole("switch", { name: "Reranker" });
  if ((await reranker.getAttribute("aria-checked")) === "true") await reranker.click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page
    .getByRole("textbox", { name: "Ask a question about the repository" })
    .fill("How does BM25 combine document length and term frequency?");
  let fallbackCalls = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/ask") fallbackCalls++;
  });
  const streamResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/ask/stream" && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Send question" }).click();
  expect((await streamResponse).headers()["content-type"]).toContain("text/event-stream");
  await expect(page.locator(".citation-chip").first()).toBeVisible({ timeout: 120000 });
  await expect(page.getByRole("button", { name: "Stop response" })).toBeHidden({ timeout: 120000 });
  expect(fallbackCalls).toBe(0);
  await page.locator(".citation-chip").first().click();
  await expect(page.locator(".code-lines")).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/askrepo-live.png", fullPage: true });
});

test("follow-up history is bounded and New chat starts without memory", async ({ page }) => {
  const requests: { history?: { role: string; content: string }[] }[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/ask/stream")
      requests.push(request.postDataJSON());
  });
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
  await page.getByRole("button", { name: /Seekr A search engine/ }).click();
  await page.getByRole("button", { name: /How does the URL frontier/ }).click();
  await expect(page.getByRole("button", { name: "Stop response" })).toBeHidden();
  const input = page.getByRole("textbox", { name: "Ask a question about the repository" });
  await input.fill("and where is that called?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByText("Searching for:", { exact: false })).toContainText(
    "URLFrontier.enqueue",
  );
  expect(requests[1]?.history?.map((message) => message.role)).toEqual(["user", "assistant"]);
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await page.getByRole("button", { name: /How are search results ranked/ }).click();
  await expect(page.getByRole("button", { name: "Stop response" })).toBeHidden();
  expect(requests[2]?.history).toEqual([]);
});

test("Stop aborts a real chunked HTTP stream and keeps partial replies uncited", async ({
  page,
}) => {
  let disconnected = false;
  let fallbackCalls = 0;
  const event = (name: string, data: unknown) =>
    `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
  const server = createServer((request, response) => {
    const headers = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "content-type",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    };
    if (request.method === "OPTIONS") {
      response.writeHead(204, headers);
      response.end();
      return;
    }
    request.resume();
    response.writeHead(200, headers);
    response.flushHeaders();
    response.write(event("chunks", []));
    response.write(event("status", { stage: "generating", message: "Receiving live evidence" }));
    const interval = setInterval(
      () => response.write(event("token", { text: "Some source evidence is arriving. " })),
      80,
    );
    const expiry = setTimeout(
      () => response.end(event("error", { message: "Fixture expired" })),
      20000,
    );
    response.once("close", () => {
      disconnected = true;
      clearInterval(interval);
      clearTimeout(expiry);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("No fixture port");
  try {
    await page.route("**/ask/stream", (route) =>
      route.continue({ url: `http://127.0.0.1:${address.port}/ask/stream` }),
    );
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === "/ask") fallbackCalls++;
    });
    await page.goto("/");
    await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
    await page.getByRole("button", { name: /Seekr A search engine/ }).click();
    await page.getByRole("button", { name: /How does the URL frontier/ }).click();
    await expect(page.locator(".markdown")).toContainText("source evidence is arriving");
    await page.getByRole("button", { name: "Stop response" }).click();
    await expect(page.getByText("Stopped · Partial response", { exact: false })).toBeVisible();
    await expect.poll(() => disconnected).toBe(true);
    expect(fallbackCalls).toBe(0);
    await expect(page.locator(".citation-chip")).toHaveCount(0);
    await page.reload();
    await page.locator(".history-item").first().click();
    await expect(page.getByText("Stopped · Partial response", { exact: false })).toBeVisible();
    await page.screenshot({
      path: "test-results/screenshots/askrepo-stream-stop.png",
      fullPage: true,
    });
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
