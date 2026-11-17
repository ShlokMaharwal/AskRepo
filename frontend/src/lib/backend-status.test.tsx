import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { BackendBanner } from "@/components/askrepo/backend-banner";
import {
  BackendUnavailableError,
  healthReady,
  healthRetryDelay,
  retryHealth,
  WAKING_MESSAGE,
} from "./backend-status";

describe("free-host readiness", () => {
  it("retries mocked fetch with capped exponential delays", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(new Response("", { status: 503 }))
      .mockResolvedValueOnce(new Response('{"status":"ok"}'));
    const sleep = vi.fn().mockResolvedValue(undefined);
    const result = await retryHealth(
      async () => {
        const response = await fetchMock();
        if (!response.ok) throw new Error("waking");
        return response.json();
      },
      undefined,
      sleep,
    );
    expect(result).toEqual({ status: "ok" });
    expect(sleep.mock.calls.map(([ms]) => ms)).toEqual([1000, 2000]);
    expect(healthRetryDelay(20)).toBe(15000);
  });

  it("bounds retries and stops on cancellation", async () => {
    const call = vi.fn().mockRejectedValue(new Error("offline"));
    await expect(retryHealth(call, undefined, async () => {})).rejects.toBeInstanceOf(
      BackendUnavailableError,
    );
    expect(call).toHaveBeenCalledTimes(8);
    const controller = new AbortController();
    controller.abort();
    await expect(retryHealth(call, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(call).toHaveBeenCalledTimes(8);
  });

  it("shows a waking banner and live demo progress until all demos are ready", () => {
    const health = {
      status: "ok",
      service: "askrepo",
      mode: "ready",
      demoRepos: [{ name: "Seekr", status: "indexing" as const, chunks: 42 }],
    };
    expect(healthReady(health)).toBe(false);
    expect(
      healthReady({ ...health, demoRepos: [{ name: "Seekr", status: "ready", chunks: 42 }] }),
    ).toBe(true);
    expect(renderToStaticMarkup(<BackendBanner unreachable slow={false} />)).toContain(
      WAKING_MESSAGE,
    );
    expect(
      renderToStaticMarkup(<BackendBanner health={health} unreachable={false} slow={false} />),
    ).toContain("Seekr: indexing");
    expect(
      renderToStaticMarkup(
        <BackendBanner health={{ ...health, demoRepos: [] }} unreachable={false} slow={false} />,
      ),
    ).toBe("");
  });
});
