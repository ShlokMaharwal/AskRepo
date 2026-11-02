import { Check, Copy, FileCode2, Loader2, PanelRightClose } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Citation } from "@/api";

function SyntaxLine({ text }: { text: string }) {
  // All token categories intentionally use neutral shades.
  const tokens = text.split(
    /("[^"]*"|'[^']*'|\b(?:export|class|const|let|function|return|async|await|if|for|import|from|new|private|readonly|type)\b|\/\/.*$)/g,
  );
  return (
    <>
      {tokens.map((token, index) => (
        <span
          key={index}
          className={
            token.startsWith("//")
              ? "syntax-comment"
              : /^["']/.test(token)
                ? "syntax-string"
                : /^(export|class|const|let|function|return|async|await|if|for|import|from|new|private|readonly|type)$/.test(
                      token,
                    )
                  ? "syntax-keyword"
                  : ""
          }
        >
          {token}
        </span>
      ))}
    </>
  );
}

export function CodeViewer({
  repoId,
  citation,
  onClose,
}: {
  repoId: string;
  citation: Citation | null;
  onClose: () => void;
}) {
  const [file, setFile] = useState<{ content: string; language: string } | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const lineRef = useRef<HTMLDivElement>(null);
  const path = citation?.path;
  useEffect(() => {
    let active = true;
    setFile(null);
    setError("");
    if (path)
      api
        .file(repoId, path)
        .then((result) => {
          if (active) setFile(result);
        })
        .catch((reason: Error) => {
          if (active) setError(reason.message);
        });
    return () => {
      active = false;
    };
  }, [repoId, path]);
  useEffect(() => {
    lineRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [file, citation?.startLine]);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1800);
    return () => clearTimeout(timer);
  }, [copied]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(file?.content ?? "");
      setCopied(true);
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  }
  return (
    <aside className="code-viewer" aria-label="Code viewer">
      <div className="code-toolbar">
        <span>
          <FileCode2 size={14} /> {citation?.path.split("/").at(-1) ?? "Source explorer"}
        </span>
        <div>
          <button className="icon-button" aria-label="Copy file" onClick={copy} disabled={!file}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button className="icon-button" aria-label="Close code viewer" onClick={onClose}>
            <PanelRightClose size={16} />
          </button>
        </div>
      </div>
      {citation ? (
        <>
          <div className="code-breadcrumb mono">{citation.path}</div>
          <div className="code-location">
            <span>{file?.language ?? "source"}</span>
            <span>
              L{citation.startLine}–{citation.endLine}
            </span>
          </div>
          {error ? (
            <div className="error-notice" role="alert">
              {error}
            </div>
          ) : !file ? (
            <div className="code-loading">
              <Loader2 className="spin" size={18} /> Loading source…
            </div>
          ) : (
            <div className="code-lines" tabIndex={0} aria-label={`Source code: ${citation.path}`}>
              {file.content.split("\n").map((line, index) => {
                const number = index + 1;
                const selected = number >= citation.startLine && number <= citation.endLine;
                return (
                  <div
                    key={number}
                    ref={number === citation.startLine ? lineRef : undefined}
                    className={`code-line ${selected ? "cited-line" : ""}`}
                  >
                    <span className="line-number">{number}</span>
                    <code>
                      <SyntaxLine text={line || " "} />
                    </code>
                  </div>
                );
              })}
            </div>
          )}
          <div className="code-footer">
            <span className="tiny-square" /> Highlighted lines are cited in the answer
          </div>
        </>
      ) : (
        <div className="code-empty">
          <FileCode2 size={30} strokeWidth={1} />
          <h3>The evidence lives here.</h3>
          <p>Click a source citation to inspect the exact code behind an answer.</p>
          <span className="mono small">FILE → LINE → CONTEXT</span>
        </div>
      )}
    </aside>
  );
}
