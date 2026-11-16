import { describe, expect, it, vi, afterEach } from "vitest";
import { consumeAnswerStream, StreamProtocolError, StreamRemoteError } from "./answer-stream";
import { api } from "@/api";

const frame = (event: string, data: unknown) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const done = { notFound: false, latencyMs: { retrieve: 1, rerank: 0, generate: 2 }, llmCalls: 1 };
function body(text: string, size = 1) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (let index = 0; index < bytes.length; index += size)
        controller.enqueue(bytes.slice(index, index + size));
      controller.close();
    },
  });
}

afterEach(() => vi.restoreAllMocks());

describe("answer stream parser", () => {
  it("accepts a final lone-CR event delimiter at EOF", async () => {
    const events: string[] = [];
    const text = frame("chunks", []) + frame("citations", []) + frame("done", done);
    await consumeAnswerStream(body(text.replace(/\n/g, "\r")), (event) => events.push(event.event));
    expect(events).toEqual(["chunks", "citations", "done"]);
  });
  it("handles fragmented UTF-8, CRLF, heartbeats, and multiline JSON", async () => {
    const events: string[] = [];
    const text =
      ": heartbeat\n\n" +
      frame("chunks", []) +
      'event: token\ndata: {\ndata: "text":"hello → 🌱"}\n\n' +
      frame("citations", []) +
      frame("done", done);
    await consumeAnswerStream(body(text.replace(/\n/g, "\r\n")), (event) => {
      events.push(event.event);
      if (event.event === "token") expect(event.data.text).toBe("hello → 🌱");
    });
    expect(events).toEqual(["chunks", "token", "citations", "done"]);
  });

  it("rejects truncated, malformed, and out-of-order streams", async () => {
    for (const text of [
      frame("chunks", []),
      frame("token", { text: "early" }),
      "event: chunks\ndata: nope\n\n",
      frame("done", done),
    ]) {
      await expect(consumeAnswerStream(body(text), () => {})).rejects.toBeInstanceOf(
        StreamProtocolError,
      );
    }
  });

  it("uses the final cleaned answer and ignores unknown event types", async () => {
    const values: string[] = [];
    const text =
      frame("future_event", { anything: true }) +
      frame("chunks", []) +
      frame("token", { text: "bad [no.py:1-2]" }) +
      frame("answer_clean", { answer: "clean" }) +
      frame("citations", []) +
      frame("done", done);
    await consumeAnswerStream(body(text, 7), (event) => {
      if (event.event === "answer_clean") values.push(event.data.answer);
    });
    expect(values).toEqual(["clean"]);
  });

  it("closes a blocked reader immediately on Stop", async () => {
    const controller = new AbortController();
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({
      start(source) {
        source.enqueue(
          new TextEncoder().encode(frame("status", { stage: "generating", message: "working" })),
        );
      },
      cancel,
    });
    await expect(
      consumeAnswerStream(stream, () => controller.abort(), { signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(cancel).toHaveBeenCalled();
  });

  it("surfaces sanitized server errors", async () => {
    await expect(
      consumeAnswerStream(
        body(frame("error", { message: "Demo limit reached, try again in a minute" })),
        () => {},
      ),
    ).rejects.toBeInstanceOf(StreamRemoteError);
  });
});

describe("stream request fallback", () => {
  const input = { repoId: "0123456789abcdef0123456789abcdef", question: "where" };
  it("supports an older backend when its streaming endpoint is missing", async () => {
    const answer = {
      answer: "legacy",
      chunks: [],
      citations: [],
      notFound: true,
      latencyMs: done.latencyMs,
    };
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 404 }))
      .mockResolvedValueOnce(Response.json(answer));
    await api.askStream(
      { ...input, history: [{ role: "user", content: "prior" }] },
      () => {},
      new AbortController().signal,
    );
    const payload = JSON.parse(String(fetch.mock.calls[1]?.[1]?.body));
    expect(payload).toEqual({
      repoId: input.repoId,
      question: input.question,
      topK: 8,
      hybrid: true,
      rerank: true,
    });
  });
  it("falls back once when the streaming endpoint is unavailable", async () => {
    const answer = {
      answer: "complete",
      chunks: [],
      citations: [],
      notFound: true,
      latencyMs: done.latencyMs,
    };
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 503 }))
      .mockResolvedValueOnce(Response.json(answer));
    const response = await api.askStream(input, () => {}, new AbortController().signal);
    expect(response.answer).toBe("complete");
    expect(fetch).toHaveBeenCalledTimes(2);
    const streamBody = JSON.parse(String(fetch.mock.calls[0]?.[1]?.body));
    const fallbackBody = JSON.parse(String(fetch.mock.calls[1]?.[1]?.body));
    expect(streamBody.requestId).toBe(fallbackBody.requestId);
    expect(fallbackBody.agentic).toBe(true);
    expect(String(fetch.mock.calls[1]?.[0])).toMatch(/\/ask$/);
  });

  it("does not retry rate-limited requests", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        Response.json({ detail: "Demo limit reached, try again in a minute" }, { status: 429 }),
      );
    await expect(api.askStream(input, () => {}, new AbortController().signal)).rejects.toThrow(
      "Demo limit reached",
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not fall back after a user abort", async () => {
    const controller = new AbortController();
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("stopped", "AbortError")),
            { once: true },
          );
        }),
    );
    const pending = api.askStream(input, () => {}, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
