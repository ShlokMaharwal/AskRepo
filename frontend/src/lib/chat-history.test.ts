import { expect, it } from "vitest";
import { requestHistory } from "./chat-history";

it("sends six recent messages, preserves citation tails, and excludes incomplete replies", () => {
  const response = {
    answer: "a".repeat(3000) + " [src/frontier.ts:20-30]",
    chunks: [],
    citations: [],
    notFound: false,
    latencyMs: { retrieve: 0, rerank: 0, generate: 0 },
  };
  const messages = Array.from({ length: 5 }, (_, index) => ({
    id: String(index),
    question: `question ${index}`,
    response,
  }));
  const history = requestHistory([
    ...messages,
    { id: "stop", question: "interrupted", response, stopped: true },
  ]);
  expect(history).toHaveLength(6);
  expect(history[0]?.content).toBe("question 2");
  expect(history.at(-1)?.content.length).toBe(1200);
  expect(history.at(-1)?.content).toContain("src/frontier.ts:20-30");
  expect(history.some((message) => message.content === "interrupted")).toBe(false);
});
