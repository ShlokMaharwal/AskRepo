import { mockApi } from "@/lib/demo";

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
};
export type Comparison = Record<"bm25" | "vector" | "hybrid", Chunk[]>;

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
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
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `AskRepo request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  compare: (input: AskInput): Promise<Comparison> => {
    if (useMock || input.repoId.startsWith("demo:"))
      return mock().then((provider) => provider.compare(input));
    return Promise.reject(new Error("Mode comparison is available in demo workspaces."));
  },
  health: () => request<{ status: string; service: string; mode: string }>("/health"),
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
};
