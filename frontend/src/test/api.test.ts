import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/api";

afterEach(() => vi.unstubAllGlobals());

describe("AskRepo API contract", () => {
  it("indexes repositories against the configured backend", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ jobId: "job", repoId: "repo" })));
    vi.stubGlobal("fetch", fetchMock);
    expect(await api.index("https://github.com/owner/repo")).toEqual({
      jobId: "job",
      repoId: "repo",
    });
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toMatch(/\/index$/);
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ repoUrl: "https://github.com/owner/repo" });
  });

  it("uses the request defaults and safely encodes file paths", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}")));
    vi.stubGlobal("fetch", fetchMock);
    await api.ask({ repoId: "repo", question: "Where?" });
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({
      repoId: "repo",
      question: "Where?",
      topK: 8,
      hybrid: true,
      rerank: true,
    });
    await api.file("repo", "src/a & b.ts");
    expect(fetchMock.mock.calls[1]![0]).toContain("path=src%2Fa+%26+b.ts");
  });

  it("surfaces backend errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"detail":"Repository not found"}', { status: 404 })),
    );
    await expect(api.ask({ repoId: "missing", question: "Where?" })).rejects.toThrow(
      "Repository not found",
    );
  });
});
