import { useQuery } from "@tanstack/react-query";
import { api, type Citation } from "@/api";

export function RetrievalComparison({
  repoId,
  question,
  onCitation,
}: {
  repoId: string;
  question: string;
  onCitation: (citation: Citation) => void;
}) {
  const result = useQuery({
    queryKey: ["comparison", repoId, question],
    queryFn: () => api.compare({ repoId, question, topK: 3 }),
    retry: false,
  });
  if (result.error) return <p className="comparison-note muted">{result.error.message}</p>;
  if (result.isPending)
    return (
      <div className="skeleton-list" aria-label="Comparing retrieval modes">
        <div />
        <div />
      </div>
    );
  return (
    <div className="comparison-grid">
      {(["bm25", "vector", "hybrid"] as const).map((method) => (
        <div key={method}>
          <strong>{method.toUpperCase()}</strong>
          {result.data[method].map((chunk) => (
            <button key={chunk.path} onClick={() => onCitation(chunk)}>
              {chunk.path.split("/").at(-1)}
              <span>{Math.round(chunk.score * 100)}%</span>
            </button>
          ))}
        </div>
      ))}
      <p className="comparison-note">Illustrative retrieval rankings for this question.</p>
    </div>
  );
}
