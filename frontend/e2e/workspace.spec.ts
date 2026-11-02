import { expect, test } from "@playwright/test";

test.beforeEach(({ page }) => {
  page.on("pageerror", (error) => console.log("Browser error:", error.message));
});

test("landing uses pure black, and the light preference persists", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
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

test("a real index request shows the backend's explicit stub failure", async ({ page }) => {
  const health = await page.request.get("http://127.0.0.1:7860/health").catch(() => null);
  test.skip(!health?.ok(), "Run the backend on port 7860 for this integration smoke check");
  await page.goto("/");
  await expect(page.locator(".askrepo-app")).toHaveAttribute("data-ready", "true");
  await page
    .getByRole("textbox", { name: "Public GitHub repository URL" })
    .fill("https://github.com/ShlokMaharwal/Seekr");
  await page.getByRole("button", { name: "Index repository", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "We couldn’t index this repository." }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("alert")).toContainText("Indexing is not implemented yet");
});
