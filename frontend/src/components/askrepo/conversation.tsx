import {
  ArrowRight,
  Check,
  ChevronDown,
  Copy,
  FileCode2,
  GitBranch,
  Search,
  ThumbsDown,
  ThumbsUp,
  TriangleAlert,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import type { Answer, Citation } from "@/api";
import { Brand } from "./brand";
import { RetrievalComparison } from "./comparison";

export type Message = {
  id: string;
  question: string;
  response?: Answer | undefined;
  error?: string | undefined;
};

function CopyButton({
  text,
  label = "Copy answer",
}: {
  text: string | (() => string);
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!copied && !error) return;
    const timer = setTimeout(() => {
      setCopied(false);
      setError(false);
    }, 1800);
    return () => clearTimeout(timer);
  }, [copied, error]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(typeof text === "function" ? text() : text);
      setCopied(true);
    } catch {
      setError(true);
    }
  }
  return (
    <button
      className="icon-button"
      onClick={copy}
      aria-label={error ? "Clipboard unavailable" : copied ? "Copied" : label}
      title={error ? "Clipboard unavailable" : copied ? "Copied!" : label}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const code = useRef<HTMLPreElement>(null);
  return (
    <div className="markdown-code">
      <div>
        <span>Code</span>
        <CopyButton text={() => code.current?.textContent ?? ""} label="Copy code" />
      </div>
      <pre ref={code}>{children}</pre>
    </div>
  );
}

function AssistantAnswer({
  answer,
  onCitation,
  animate,
  repoId,
  question,
}: {
  answer: Answer;
  onCitation: (citation: Citation) => void;
  animate: boolean;
  repoId: string;
  question: string;
}) {
  const [visible, setVisible] = useState(animate ? 0 : answer.answer.length);
  const [vote, setVote] = useState<"up" | "down" | null>(null);
  const [compare, setCompare] = useState(false);
  useEffect(() => {
    if (!animate) {
      setVisible(answer.answer.length);
      return;
    }
    const timer = setInterval(
      () =>
        setVisible((count) => {
          const next = Math.min(answer.answer.length, count + 24);
          if (next === answer.answer.length) clearInterval(timer);
          return next;
        }),
      16,
    );
    return () => clearInterval(timer);
  }, [answer.answer, animate]);
  const complete = visible >= answer.answer.length;
  const text = answer.answer.slice(0, visible).replace(/\[([^\]\n]+):\d+-\d+\]/g, "");
  return (
    <div className="assistant-answer">
      {answer.notFound && (
        <div className="not-found">
          <TriangleAlert size={17} />
          <strong>Not found in this repository</strong>
        </div>
      )}
      <div className="markdown">
        <Markdown
          components={{
            pre: CodeBlock,
            a: ({ href, children }) => (
              <a
                href={href && /^https?:\/\//.test(href) ? href : undefined}
                target="_blank"
                rel="noreferrer"
              >
                {children}
              </a>
            ),
          }}
        >
          {text}
        </Markdown>
        {!complete && <span className="typing-cursor" />}
      </div>
      {complete && (
        <>
          {answer.citations.length > 0 && (
            <div className="citation-section">
              <span className="eyebrow">SOURCES</span>
              <div className="citation-chips">
                {answer.citations.map((citation) => (
                  <button
                    className="citation-chip"
                    key={`${citation.path}:${citation.startLine}`}
                    onClick={() => onCitation(citation)}
                  >
                    <FileCode2 size={12} />
                    <span>{citation.path}</span>
                    <span className="citation-range">
                      L{citation.startLine}–{citation.endLine}
                    </span>
                    <ArrowRight size={11} />
                  </button>
                ))}
              </div>
            </div>
          )}
          {answer.chunks.length > 0 && (
            <details className="retrieval-details">
              <summary>
                <Search size={12} />
                <span>Retrieval details</span>
                <span className="count-badge">{answer.chunks.length}</span>
                <ChevronDown size={12} />
              </summary>
              <div className="retrieval-body">
                {answer.chunks.map((chunk, index) => (
                  <button
                    onClick={() => onCitation(chunk)}
                    className="retrieved-chunk"
                    key={`${chunk.path}:${index}`}
                  >
                    <div>
                      <span className="mono">{chunk.path}</span>
                      <span>{Math.round(chunk.score * 100)}%</span>
                    </div>
                    <div className="score-track">
                      <span style={{ width: `${chunk.score * 100}%` }} />
                    </div>
                    <div>
                      <span className="method-badge">{chunk.method.toUpperCase()}</span>
                      <span>
                        L{chunk.startLine}–{chunk.endLine}
                      </span>
                    </div>
                  </button>
                ))}
                <label className="compare-toggle">
                  <input
                    type="checkbox"
                    checked={compare}
                    onChange={(event) => setCompare(event.target.checked)}
                  />{" "}
                  Compare retrieval modes
                </label>
                {compare && (
                  <RetrievalComparison
                    repoId={repoId}
                    question={question}
                    onCitation={onCitation}
                  />
                )}
              </div>
            </details>
          )}
          <div className="answer-actions">
            <CopyButton text={answer.answer} />
            <span className="action-divider" />
            <button
              className={`icon-button ${vote === "up" ? "selected" : ""}`}
              aria-label="Helpful answer"
              aria-pressed={vote === "up"}
              onClick={() => setVote(vote === "up" ? null : "up")}
            >
              <ThumbsUp size={14} />
            </button>
            <button
              className={`icon-button ${vote === "down" ? "selected" : ""}`}
              aria-label="Unhelpful answer"
              aria-pressed={vote === "down"}
              onClick={() => setVote(vote === "down" ? null : "down")}
            >
              <ThumbsDown size={14} />
            </button>
            <span className="answer-latency">
              {Math.round(
                answer.latencyMs.retrieve + answer.latencyMs.rerank + answer.latencyMs.generate,
              )}{" "}
              ms <span>·</span> {answer.citations.length} sources
            </span>
          </div>
        </>
      )}
    </div>
  );
}

export function Conversation({
  messages,
  repoName,
  pending,
  onAsk,
  onCitation,
  freshId,
  repoId,
}: {
  messages: Message[];
  repoName: string;
  pending: boolean;
  onAsk: (question: string) => void;
  onCitation: (citation: Citation) => void;
  freshId: string | null;
  repoId: string;
}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, pending]);
  if (!messages.length)
    return (
      <div className="chat-welcome">
        <span className="welcome-icon">
          <GitBranch size={25} strokeWidth={1.3} />
        </span>
        <span className="eyebrow">{repoName.toUpperCase()} / WORKSPACE</span>
        <h1>Meet your codebase.</h1>
        <p>
          Start with a question. Follow the sources.
          <br />
          Understand how everything connects.
        </p>
        <div className="suggested-questions">
          {[
            "How does the URL frontier avoid crawling duplicate pages?",
            "How are search results ranked with BM25?",
            "How is the index persisted between restarts?",
          ].map((question, index) => (
            <button key={question} onClick={() => onAsk(question)}>
              <span className="suggestion-index">0{index + 1}</span>
              <span>{question}</span>
              <ArrowRight size={15} />
            </button>
          ))}
        </div>
        <span className="welcome-footnote">ANSWERS GROUNDED IN CODE, NOT GUESSWORK.</span>
      </div>
    );
  return (
    <div className="conversation" role="log" aria-label="Chat messages">
      {messages.map((message) => (
        <div key={message.id} className="message-pair">
          <div className="user-message">
            <span className="user-avatar">Y</span>
            <div>
              <span className="message-author">You</span>
              <p>{message.question}</p>
            </div>
          </div>
          <div className="assistant-message">
            <Brand compact />
            <div className="assistant-content">
              <div className="assistant-author">
                AskRepo <span>CODEBASE ASSISTANT</span>
              </div>
              {message.response ? (
                <AssistantAnswer
                  repoId={repoId}
                  question={message.question}
                  answer={message.response}
                  onCitation={onCitation}
                  animate={message.id === freshId}
                />
              ) : message.error ? (
                <div className="error-notice" role="alert">
                  {message.error}
                </div>
              ) : (
                <div className="thinking" role="status">
                  <span />
                  <span />
                  <span />
                  <span className="thinking-label">Searching your repository</span>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}
