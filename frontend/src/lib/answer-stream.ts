import { z } from "zod";

const location = z.object({
  path: z.string().min(1).max(1024),
  startLine: z.number().int().min(1),
  endLine: z.number().int().min(1),
});
const schemas = {
  status: z.object({
    stage: z.enum(["rewriting", "retrieving", "reranking", "retrying", "generating"]),
    message: z.string().max(1024),
  }),
  chunks: z
    .array(
      location
        .extend({
          score: z.number().min(0).max(1),
          method: z.enum(["bm25", "vector", "hybrid", "reranked"]),
          code: z.string(),
        })
        .refine((value) => value.endLine >= value.startLine),
    )
    .max(50),
  token: z.object({ text: z.string().max(50000) }),
  answer_clean: z.object({ answer: z.string().max(50000) }),
  citations: z.array(location.refine((value) => value.endLine >= value.startLine)).max(100),
  done: z.object({
    notFound: z.boolean(),
    latencyMs: z.object({
      retrieve: z.number().nonnegative(),
      rerank: z.number().nonnegative(),
      generate: z.number().nonnegative(),
    }),
    llmCalls: z.number().int().nonnegative(),
    generationMode: z.string().optional(),
    rerankApplied: z.boolean().optional(),
    rewrittenQuestion: z.string().nullable().optional(),
    rewriteMode: z.string().optional(),
    agenticUsed: z.boolean().optional(),
    retried: z.boolean().optional(),
    totalMs: z.number().nonnegative().optional(),
    cached: z.boolean().optional(),
  }),
  error: z.object({ message: z.string().max(1000) }),
} as const;

export type AnswerStreamEvent = {
  [K in keyof typeof schemas]: { event: K; data: z.infer<(typeof schemas)[K]> };
}[keyof typeof schemas];

export class StreamProtocolError extends Error {}
export class StreamRemoteError extends Error {}

export function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) throw signal.reason ?? new DOMException("Request stopped", "AbortError");
}

/** Decode SSE across arbitrary byte, UTF-8, CRLF, and multiline-data boundaries. */
export async function consumeAnswerStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: AnswerStreamEvent) => void,
  options: { signal?: AbortSignal; onActivity?: () => void } = {},
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    event = "",
    data: string[] = [];
  let done = false,
    chunks = false,
    citations = false;
  const abort = () => {
    void reader.cancel().catch(() => {});
  };
  options.signal?.addEventListener("abort", abort, { once: true });
  function line(value: string) {
    if (value === "") {
      if (data.length && Object.prototype.hasOwnProperty.call(schemas, event)) {
        let parsed: AnswerStreamEvent;
        try {
          const key = event as keyof typeof schemas;
          parsed = {
            event: key,
            data: schemas[key].parse(JSON.parse(data.join("\n"))),
          } as AnswerStreamEvent;
        } catch {
          throw new StreamProtocolError("Invalid answer stream");
        }
        if (parsed.event === "chunks") chunks = true;
        if ((parsed.event === "token" || parsed.event === "citations") && (!chunks || citations)) {
          throw new StreamProtocolError("Answer stream events arrived out of order");
        }
        if (parsed.event === "citations") citations = true;
        if (parsed.event === "done") {
          if (!citations)
            throw new StreamProtocolError("Answer stream is missing validated citations");
          done = true;
        }
        onEvent(parsed);
        if (parsed.event === "error") throw new StreamRemoteError(parsed.data.message);
      }
      event = "";
      data = [];
    } else if (!value.startsWith(":")) {
      const colon = value.indexOf(":");
      const key = colon < 0 ? value : value.slice(0, colon);
      const content = colon < 0 ? "" : value.slice(colon + 1).replace(/^ /, "");
      if (key === "event") event = content;
      if (key === "data") data.push(content);
    }
  }
  try {
    while (!done) {
      throwIfAborted(options.signal);
      const next = await reader.read();
      throwIfAborted(options.signal);
      if (next.done) {
        buffer += decoder.decode();
        if (buffer.endsWith("\r")) buffer = buffer.slice(0, -1) + "\n";
      } else {
        options.onActivity?.();
        buffer += decoder.decode(next.value, { stream: true });
      }
      if (buffer.length + data.join("").length > 1048576)
        throw new StreamProtocolError("Answer stream frame is too large");
      let match: RegExpExecArray | null;
      while (!done && (match = /\r\n|\n|\r(?!$)/.exec(buffer))) {
        line(buffer.slice(0, match.index));
        buffer = buffer.slice(match.index + match[0].length);
      }
      if (next.done) break;
    }
    if (!done) throw new StreamProtocolError("The answer stream ended before completion");
  } finally {
    options.signal?.removeEventListener("abort", abort);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
