import type { Answer, Comparison, JobStatus, Repo } from "@/api";

export const demos = [
  {
    name: "Seekr",
    description: "A search engine, from crawl to query.",
    language: "TypeScript",
    icon: "search",
  },
  {
    name: "CodeNest",
    description: "Collaborative coding interviews, explained.",
    language: "TypeScript",
    icon: "code",
  },
  {
    name: "DPTrace",
    description: "Dynamic programming, step by step.",
    language: "JavaScript",
    icon: "layers",
  },
];

// Illustrative search-engine fixtures, not verified contents of the named public repos.
export const demoFiles: Record<string, string> = {
  "packages/core/frontier.ts": [
    'import type { Redis } from "ioredis";',
    'import { normalizeUrl } from "./url";',
    "",
    "/** Redis-backed crawl frontier with URL deduplication. */",
    "export class URLFrontier {",
    "  constructor(private readonly redis: Redis) {}",
    "",
    "  async enqueue(url: string, priority = 0): Promise<boolean> {",
    "    const normalized = normalizeUrl(url);",
    '    const fresh = await this.redis.sadd("crawl:seen", normalized);',
    "    if (!fresh) return false;",
    '    await this.redis.zadd("crawl:pending", priority, normalized);',
    "    return true;",
    "  }",
    "",
    "  async dequeue(): Promise<string | null> {",
    '    const [url] = await this.redis.zpopmin("crawl:pending");',
    "    return url ?? null;",
    "  }",
    "}",
  ].join("\n"),
  "packages/search/bm25.ts": [
    "/** Rank documents using term frequency and inverse document frequency. */",
    "export function bm25(tf: number, df: number, length: number, avg: number, total: number) {",
    "  const k1 = 1.2;",
    "  const b = 0.75;",
    "  const idf = Math.log(1 + (total - df + 0.5) / (df + 0.5));",
    "  const norm = tf + k1 * (1 - b + b * length / avg);",
    "  return idf * (tf * (k1 + 1)) / norm;",
    "}",
  ].join("\n"),
  "packages/search/autocomplete.ts": [
    "type TrieNode = { children: Map<string, TrieNode>; word?: string };",
    "",
    "export function complete(node: TrieNode, prefix: string): string[] {",
    "  for (const character of prefix) {",
    "    const next = node.children.get(character);",
    "    if (!next) return [];",
    "    node = next;",
    "  }",
    "  return collectWords(node).slice(0, 10);",
    "}",
    "",
    "function collectWords(node: TrieNode): string[] {",
    "  return [...(node.word ? [node.word] : []),",
    "    ...[...node.children.values()].flatMap(collectWords)];",
    "}",
  ].join("\n"),
  "packages/index/snapshot.ts": [
    'import { readFile, writeFile } from "node:fs/promises";',
    "",
    "export async function saveSnapshot(path: string, index: Uint8Array) {",
    "  await writeFile(path, index);",
    "}",
    "",
    "export async function loadSnapshot(path: string): Promise<Uint8Array> {",
    "  return new Uint8Array(await readFile(path));",
    "}",
  ].join("\n"),
  "README.md":
    "# Search engine demo\n\nIllustrative fixtures for AskRepo.\n\n## Architecture\nA crawler feeds a Redis URL frontier. BM25 ranks indexed documents.\nA trie provides prefix completion and binary snapshots persist the index.",
};

const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const started = new Map<string, number>();

export function demoRepo(name: string): Repo {
  return {
    repoId: `demo:${name.toLowerCase()}`,
    repoUrl: `https://github.com/ShlokMaharwal/${name}`,
    files: Object.keys(demoFiles).length,
    chunks: 7,
    indexedAt: new Date().toISOString(),
  };
}

export const mockApi = {
  async compare(input: { question: string; topK?: number }): Promise<Comparison> {
    await pause(250);
    const primary = /bm25|rank|score/i.test(input.question)
      ? "packages/search/bm25.ts"
      : /autocomplete|trie|prefix/i.test(input.question)
        ? "packages/search/autocomplete.ts"
        : /snapshot|persist|binary/i.test(input.question)
          ? "packages/index/snapshot.ts"
          : "packages/core/frontier.ts";
    const paths = [primary, ...Object.keys(demoFiles).filter((path) => path !== primary)];
    const results = {} as Comparison;
    for (const method of ["bm25", "vector", "hybrid"] as const) {
      const ordered =
        method === "vector"
          ? ["README.md", ...paths.filter((path) => path !== "README.md")]
          : paths;
      results[method] = ordered.slice(0, input.topK ?? 8).map((path, index) => ({
        path,
        startLine: 1,
        endLine: demoFiles[path]!.split("\n").length,
        score: Math.max(
          0.1,
          (method === "hybrid" ? 0.97 : method === "vector" ? 0.88 : 0.91) - index * 0.13,
        ),
        method,
        code: demoFiles[path]!,
      }));
    }
    return results;
  },
  async index(repoUrl: string) {
    await pause(250);
    const repoId = `demo:${repoUrl.split("/").filter(Boolean).at(-1) ?? "repository"}`;
    const jobId = `demo:${Date.now()}`;
    started.set(jobId, Date.now());
    return { jobId, repoId };
  },
  async indexStatus(jobId: string): Promise<JobStatus> {
    const stage = Math.min(4, Math.floor((Date.now() - (started.get(jobId) ?? Date.now())) / 850));
    const statuses = ["cloning", "parsing", "chunking", "embedding", "ready"] as const;
    return {
      status: statuses[stage]!,
      filesParsed: stage > 0 ? 5 : 0,
      chunksCreated: stage > 1 ? 7 : 0,
    };
  },
  async file(_repoId: string, path: string) {
    await pause(180);
    const content = demoFiles[path];
    if (content === undefined) throw new Error("File not found in the illustrative demo");
    return { content, language: path.endsWith(".md") ? "markdown" : "typescript" };
  },
  async ask(input: {
    question: string;
    topK?: number;
    hybrid?: boolean;
    rerank?: boolean;
  }): Promise<Answer> {
    await pause(700);
    const question = input.question.toLowerCase();
    if (/payment|stripe|authentication|oauth|billing/.test(question)) {
      return {
        answer:
          "The provided repository context does not contain an implementation for this. Try asking about crawling, ranking, autocomplete, or index persistence.",
        citations: [],
        chunks: [],
        notFound: true,
        latencyMs: { retrieve: 19, rerank: 0, generate: 0 },
      };
    }
    const path = /rank|bm25|score/.test(question)
      ? "packages/search/bm25.ts"
      : /trie|autocomplete|prefix/.test(question)
        ? "packages/search/autocomplete.ts"
        : /persist|snapshot|disk|binary/.test(question)
          ? "packages/index/snapshot.ts"
          : "packages/core/frontier.ts";
    const code = demoFiles[path]!;
    const citation = { path, startLine: 1, endLine: code.split("\n").length };
    const explanations: Record<string, string> = {
      "packages/core/frontier.ts":
        "The crawl frontier uses **Redis** to schedule URLs and avoid visiting the same page twice.\n\n1. `enqueue()` normalizes each URL and adds it to the `crawl:seen` set.\n2. If the URL already exists, it returns `false`.\n3. New URLs enter the `crawl:pending` sorted set with a priority.\n4. `dequeue()` uses `zpopmin` to atomically retrieve the next URL.\n\nThe `URLFrontier` class keeps scheduling separate from fetching page content.",
      "packages/search/bm25.ts":
        "Document ranking uses **BM25**, combining term frequency with inverse document frequency.\n\n- `k1 = 1.2` controls term-frequency saturation.\n- `b = 0.75` controls document-length normalization.\n- The IDF gives more weight to terms that appear in fewer documents.\n\n```ts\nreturn idf * (tf * (k1 + 1)) / norm;\n```",
      "packages/search/autocomplete.ts":
        "Autocomplete walks a **trie** one character at a time. If a prefix is missing, it returns an empty list. Otherwise, `collectWords()` visits the subtree and returns up to ten completions.\n\nEach node stores its children in a `Map` and optionally holds a complete word.",
      "packages/index/snapshot.ts":
        "The index is persisted as a **binary snapshot** using Node's filesystem API.\n\n`saveSnapshot()` writes a `Uint8Array` to disk. `loadSnapshot()` reads the bytes back into a `Uint8Array`, allowing the index to survive process restarts.",
    };
    return {
      answer: `${explanations[path]}\n\n[${path}:1-${citation.endLine}]`,
      citations: [citation],
      chunks: [
        {
          ...citation,
          code,
          score: 0.96,
          method: input.rerank ? "reranked" : input.hybrid ? "hybrid" : "bm25",
        },
        {
          path: "README.md",
          startLine: 5,
          endLine: 7,
          code: demoFiles["README.md"]!.split("\n").slice(4).join("\n"),
          score: 0.78,
          method: "vector",
        },
      ].slice(0, input.topK ?? 8) as Answer["chunks"],
      notFound: false,
      latencyMs: { retrieve: 24, rerank: input.rerank ? 38 : 0, generate: 412 },
    };
  },
};
