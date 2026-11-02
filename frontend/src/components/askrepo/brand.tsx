import { Code2 } from "lucide-react";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand">
      <span className="brand-mark">
        <Code2 size={19} strokeWidth={1.7} />
      </span>
      {!compact && (
        <span>
          AskRepo<span className="brand-dot">.</span>
        </span>
      )}
    </span>
  );
}
