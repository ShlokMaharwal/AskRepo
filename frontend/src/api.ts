import { demoFiles, mockApi } from "@/lib/demo";
import {
  consumeAnswerStream,
  StreamRemoteError,
  throwIfAborted,
  type AnswerStreamEvent,
} from "@/lib/answer-stream";
export type { AnswerStreamEvent } from "@/lib/answer-stream";

const baseUrl = (import.meta.env["VITE_API_BASE_URL"] ?? "http://localhost:7860").replace(
  /\/$/,
  "",
);
export const useMock = import.meta.env["VITE_USE_MOCK"] === "true";
const mock = () => Promise.resolve(mockApi);

export type JobStatus = {
  status: "cloning" | "parsing" | "chunking" | "embedding" | "ready" | "failed";
  filesParsed: number;
  chunksCreated: number;
  error?: string;
  queued?: boolean;
};

export type Citation = { path: string; startLine: number; endLine: number };
export type Chunk = Citation & {
  score: number;
  method: "bm25" | "vector" | "hybrid" | "reranked";
  code: string;
};
export type Answer = {
  answer: string;
  citations: Citation[];
  chunks: Chunk[];
  notFound: boolean;
  latencyMs: { retrieve: number; rerank: number; generate: number };
  generationMode?: string | undefined;
  rerankApplied?: boolean | undefined;
  llmCalls?: number | undefined;
  rewrittenQuestion?: string | null | undefined;
  rewriteMode?: string | undefined;
  agenticUsed?: boolean | undefined;
  retried?: boolean | undefined;
  totalMs?: number | undefined;
  cached?: boolean | undefined;
};
export type Repo = {
  repoId: string;
  repoUrl: string;
  files: number;
  chunks: number;
  indexedAt: string;
};
export type AskInput = {
  repoId: string;
  question: string;
  topK?: number;
  hybrid?: boolean;
  rerank?: boolean;
  retrievalMode?: "bm25" | "vector" | "hybrid";
  history?: HistoryMessage[];
  agentic?: boolean;
  requestId?: string;
};
export type HistoryMessage = { role: "user" | "assistant"; content: string };
export type Comparison = Record<"bm25" | "vector" | "hybrid", Chunk[]>;

function errorMessage(payload: unknown, status: number): string {
  const fallback = `AskRepo request failed (${status})`;
  if (!payload || typeof payload !== "object") return fallback;
  const detail = "detail" in payload ? payload.detail : payload;
  if (typeof detail === "string") return detail;
  if (
    detail &&
    typeof detail === "object" &&
    "message" in detail &&
    typeof detail.message === "string"
  )
    return detail.message;
  return fallback;
}

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  throwIfAborted(signal);
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    120000,
  );
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      signal: controller.signal,
      ...(body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(errorMessage(payload, response.status));
    }
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
    controller.abort();
  }
}

async function askStream(
  input: AskInput,
  onEvent: (event: AnswerStreamEvent) => void,
  signal: AbortSignal,
): Promise<Answer> {
  throwIfAborted(signal);
  const body = {
    topK: 8,
    hybrid: true,
    rerank: true,
    agentic: true,
    ...input,
    requestId:
      input.requestId ??
      globalThis.crypto?.randomUUID?.() ??
      `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  };
  if (useMock || input.repoId.startsWith("demo:")) {
    onEvent({
      event: "status",
      data: { stage: "retrieving", message: "Searching illustrative demo data" },
    });
    const answer = await mockApi.ask(body);
    throwIfAborted(signal);
    onEvent({ event: "chunks", data: answer.chunks });
    for (const text of answer.answer.match(/\S+\s*|\s+/g) ?? []) {
      throwIfAborted(signal);
      onEvent({ event: "token", data: { text } });
      await new Promise((resolve) => setTimeout(resolve, 8));
    }
    onEvent({ event: "citations", data: answer.citations });
    onEvent({ event: "done", data: { ...answer, llmCalls: 0 } });
    return answer;
  }
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  signal.addEventListener("abort", abort, { once: true });
  let timer: ReturnType<typeof setTimeout>;
  const refresh = () => {
    clearTimeout(timer);
    timer = setTimeout(
      () => controller.abort(new DOMException("Answer stream timed out", "TimeoutError")),
      45000,
    );
  };
  let answer: Answer = {
    answer: "",
    chunks: [],
    citations: [],
    notFound: false,
    latencyMs: { retrieve: 0, rerank: 0, generate: 0 },
  };
  let legacyFallback = false;
  try {
    refresh();
    const response = await fetch(`${baseUrl}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      legacyFallback = [404, 405, 501].includes(response.status);
      const payload = await response.json().catch(() => null);
      if ([400, 401, 403, 409, 413, 422, 429].includes(response.status)) {
        throw new StreamRemoteError(errorMessage(payload, response.status));
      }
      throw new Error("Streaming is unavailable");
    }
    if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream"))
      throw new Error("Streaming is unavailable");
    await consumeAnswerStream(
      response.body,
      (event) => {
        switch (event.event) {
          case "token":
            answer.answer += event.data.text;
            break;
          case "answer_clean":
            answer.answer = event.data.answer;
            break;
          case "chunks":
            answer.chunks = event.data;
            break;
          case "citations":
            answer.citations = event.data;
            break;
          case "done":
            answer = { ...answer, ...event.data };
            break;
        }
        if (answer.answer.length > 50000) throw new Error("Answer exceeds the response limit");
        onEvent(event);
      },
      { signal: controller.signal, onActivity: refresh },
    );
    return answer;
  } catch (error) {
    throwIfAborted(signal);
    if (error instanceof StreamRemoteError) throw error;
    clearTimeout(timer!);
    controller.abort();
    onEvent({ event: "answer_clean", data: { answer: "" } });
    onEvent({ event: "chunks", data: [] });
    onEvent({
      event: "status",
      data: { stage: "generating", message: "Streaming unavailable; requesting a complete answer" },
    });
    const fallbackBody = legacyFallback
      ? {
          repoId: input.repoId,
          question: input.question,
          topK: input.topK ?? 8,
          hybrid: input.hybrid ?? true,
          rerank: input.rerank ?? true,
          ...(input.retrievalMode ? { retrievalMode: input.retrievalMode } : {}),
        }
      : body;
    answer = await request<Answer>("/ask", fallbackBody, signal);
    throwIfAborted(signal);
    onEvent({ event: "chunks", data: answer.chunks });
    onEvent({ event: "answer_clean", data: { answer: answer.answer } });
    onEvent({ event: "citations", data: answer.citations });
    onEvent({ event: "done", data: { ...answer, llmCalls: answer.llmCalls ?? 0 } });
    return answer;
  } finally {
    clearTimeout(timer!);
    signal.removeEventListener("abort", abort);
    controller.abort();
  }
}

export const api = {
  askStream,
  compare: (input: AskInput): Promise<Comparison> => {
    if (useMock || input.repoId.startsWith("demo:"))
      return mock().then((provider) => provider.compare(input));
    return request<Comparison>("/compare", input);
  },
  health: () =>
    request<{
      status: string;
      service: string;
      mode: string;
      generation?: string;
      liteMode?: boolean;
      agenticEnabled?: boolean;
      maxLlmCalls?: number;
    }>("/health"),
  index: (repoUrl: string) =>
    useMock
      ? mock().then((provider) => provider.index(repoUrl))
      : request<{ jobId: string; repoId: string }>("/index", { repoUrl }),
  indexStatus: (jobId: string) =>
    jobId.startsWith("demo:")
      ? mock().then((provider) => provider.indexStatus(jobId))
      : request<JobStatus>(`/index/${encodeURIComponent(jobId)}`),
  ask: (input: AskInput) =>
    useMock || input.repoId.startsWith("demo:")
      ? mock().then((provider) => provider.ask({ topK: 8, hybrid: true, rerank: true, ...input }))
      : request<Answer>("/ask", { topK: 8, hybrid: true, rerank: true, ...input }),
  file: (repoId: string, path: string) =>
    useMock || repoId.startsWith("demo:")
      ? mock().then((provider) => provider.file(repoId, path))
      : request<{ content: string; language: string }>(
          `/file?${new URLSearchParams({ repoId, path })}`,
        ),
  repos: () => (useMock ? Promise.resolve([] as Repo[]) : request<Repo[]>("/repos")),
  files: (repoId: string) =>
    useMock || repoId.startsWith("demo:")
      ? Promise.resolve(
          Object.keys(demoFiles).map((path) => ({
            path,
            language: path.endsWith(".md") ? "markdown" : "typescript",
          })),
        )
      : request<{ path: string; language: string }[]>(`/files?${new URLSearchParams({ repoId })}`),
};
