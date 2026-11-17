export const WAKING_MESSAGE = "Server is waking up on free hosting, this can take about a minute";

export type DemoReadiness = {
  name: string;
  status: "ready" | "indexing" | "queued" | "failed";
  chunks: number;
  error?: string;
};

export type BackendHealth = {
  status: string;
  service: string;
  mode: string;
  generation?: string;
  liteMode?: boolean;
  agenticEnabled?: boolean;
  maxLlmCalls?: number;
  bootstrapEnabled?: boolean;
  demoRepos?: DemoReadiness[];
  indexingMode?: "open" | "allowlist" | "token";
};

export class BackendUnavailableError extends Error {
  constructor() {
    super(WAKING_MESSAGE);
    this.name = "BackendUnavailableError";
  }
}

export function healthReady(health?: BackendHealth) {
  return (
    health?.status === "ok" && (health.demoRepos ?? []).every((repo) => repo.status === "ready")
  );
}

export const healthRetryDelay = (attempt: number) => Math.min(15000, 1000 * 2 ** attempt);

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
  });
}

export async function retryHealth<T>(
  fetchOnce: () => Promise<T>,
  signal?: AbortSignal,
  sleep = wait,
) {
  for (let attempt = 0; attempt < 8; attempt++) {
    signal?.throwIfAborted();
    try {
      return await fetchOnce();
    } catch {
      signal?.throwIfAborted();
      if (attempt === 7) throw new BackendUnavailableError();
      await sleep(healthRetryDelay(attempt), signal);
    }
  }
  throw new BackendUnavailableError();
}
