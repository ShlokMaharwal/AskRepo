import { ArrowLeft, Check, Circle, GitBranch, Loader2, X } from "lucide-react";
import type { JobStatus } from "@/api";

const stages = [
  ["cloning", "Cloning repository", "Fetching a shallow copy of the default branch"],
  ["parsing", "Parsing code", "Reading supported source files"],
  ["chunking", "Creating chunks", "Preserving functions, classes, and their context"],
  ["embedding", "Generating embeddings", "Building a searchable representation of your code"],
  ["ready", "Ready to explore", "Your repository is ready for questions"],
];

export function Indexing({
  url,
  job,
  error,
  onBack,
}: {
  url: string;
  job: JobStatus | null;
  error: string;
  onBack: () => void;
}) {
  const failed = job?.status === "failed" || Boolean(error);
  const current = Math.max(
    0,
    stages.findIndex(([status]) => status === job?.status),
  );
  return (
    <section className="indexing-page">
      <button className="text-button" onClick={onBack}>
        <ArrowLeft size={14} /> Back to workspace
      </button>
      <span className="large-icon">
        <GitBranch size={27} />
      </span>
      <p className="eyebrow">BUILDING YOUR KNOWLEDGE BASE</p>
      <h1>
        {failed
          ? "We couldn’t index this repository."
          : job?.queued
            ? "Waiting for the indexing worker."
            : "Getting to know your code."}
      </h1>
      <p className="muted mono">{url.replace("https://github.com/", "")}</p>
      <div
        className="index-progress"
        role="progressbar"
        aria-label="Indexing progress"
        aria-valuenow={failed ? 0 : current * 25}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span style={{ width: `${failed ? 0 : Math.max(4, current * 25)}%` }} />
      </div>
      <div className="index-stages">
        {stages.map(([status, title, subtitle], index) => (
          <div key={status} className={`index-stage ${index === current ? "current" : ""}`}>
            <span className={`stage-icon ${index < current ? "complete" : ""}`}>
              {failed && index === current ? (
                <X size={16} />
              ) : index < current ? (
                <Check size={16} />
              ) : index === current ? (
                <Loader2 size={16} className="spin" />
              ) : (
                <Circle size={13} />
              )}
            </span>
            <div>
              <strong>{title}</strong>
              <p>{subtitle}</p>
            </div>
            <span className="stage-label">
              {index < current
                ? "Done"
                : index === current
                  ? failed
                    ? "Failed"
                    : "In progress"
                  : "Waiting"}
            </span>
          </div>
        ))}
      </div>
      <div className="index-counters">
        <span>
          <strong>{job?.filesParsed ?? 0}</strong> files parsed
        </span>
        <span>
          <strong>{job?.chunksCreated ?? 0}</strong> chunks created
        </span>
      </div>
      {(error || job?.error) && (
        <div className="error-notice" role="alert">
          {error || job?.error}
        </div>
      )}
      {!failed && (
        <p className="muted small">This may take a few minutes. You can keep this tab open.</p>
      )}
    </section>
  );
}
