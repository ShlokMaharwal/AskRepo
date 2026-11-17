import { Loader2 } from "lucide-react";
import { WAKING_MESSAGE, type BackendHealth } from "@/lib/backend-status";

export function BackendBanner({
  health,
  unreachable,
  slow,
}: {
  health?: BackendHealth | undefined;
  unreachable: boolean;
  slow: boolean;
}) {
  const demos = health?.demoRepos ?? [];
  const preparing = demos.some((repo) => repo.status !== "ready");
  if (!unreachable && !preparing && !slow) return null;
  return (
    <aside className="backend-banner" role="status" aria-live="polite">
      <Loader2 className="spin" size={16} aria-hidden="true" />
      <div>
        <strong>
          {unreachable
            ? WAKING_MESSAGE
            : preparing
              ? "Preparing demo repositories"
              : WAKING_MESSAGE}
        </strong>
        <p>
          {preparing
            ? "Repositories become available after indexing. Progress updates automatically."
            : "Your workspace stays here. Requests can take longer while the free server starts."}
        </p>
        {demos.length > 0 && (
          <ul>
            {demos.map((repo) => (
              <li key={repo.name}>
                {repo.name}: {repo.status} · {repo.chunks.toLocaleString()} chunks
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
