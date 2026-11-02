import {
  ArrowDown,
  ArrowRight,
  BookOpen,
  Code2,
  GitBranch,
  Github,
  Layers,
  Search,
  Terminal,
  Loader2,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { demos } from "@/lib/demo";

export function Landing({
  onIndex,
  onDemo,
  busy,
  error,
}: {
  onIndex: (url: string) => void;
  onDemo: (name: string) => void;
  busy: boolean;
  error: string;
}) {
  const [url, setUrl] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    onIndex(url);
  }
  return (
    <div className="landing">
      <div className="landing-eyebrow">
        <span className="tiny-square" /> YOUR REPOSITORY. NO GUESSWORK.
      </div>
      <h1>
        AskRepo<span>.</span>
      </h1>
      <h2>
        Good questions deserve
        <br />
        <span>answers from your code.</span>
      </h2>
      <p className="hero-subtitle">
        Ask questions about any codebase. Get answers with exact file and line citations.
      </p>
      <form className="repo-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="repo-url">
          Public GitHub repository URL
        </label>
        <Github size={20} aria-hidden="true" />
        <input
          id="repo-url"
          type="url"
          required
          pattern="https://github.com/[^/]+/[^/?#]+/?"
          placeholder="https://github.com/owner/repository"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={busy}
        />
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? <Loader2 className="spin" size={15} /> : null} Index repository{" "}
          <ArrowRight size={15} />
        </button>
      </form>
      {error && (
        <p className="error-notice" role="alert">
          {error}
        </p>
      )}
      <div className="repo-hint">
        <GitBranch size={12} /> Public GitHub repositories <span>·</span> Your code is never
        executed
      </div>
      <div className="demo-section">
        <div className="section-rule">
          <span>OR EXPLORE A DEMO</span>
          <span>
            NO SETUP REQUIRED <ArrowDown size={11} />
          </span>
        </div>
        <div className="demo-grid">
          {demos.map((demo, index) => {
            const Icon = [Search, Code2, Layers][index]!;
            return (
              <button
                className="demo-card"
                key={demo.name}
                onClick={() => onDemo(demo.name)}
                disabled={busy}
              >
                <div className="demo-card-top">
                  <span className="demo-icon">
                    <Icon size={20} strokeWidth={1.4} />
                  </span>
                  <ArrowRight className="demo-arrow" size={17} />
                </div>
                <h3>{demo.name}</h3>
                <p>{demo.description}</p>
                <div className="demo-meta">
                  <span className="language-dot" />
                  {demo.language}
                  <span className="demo-label">Demo</span>
                </div>
              </button>
            );
          })}
        </div>
        <p className="demo-disclaimer">Interactive examples use illustrative search-engine data.</p>
      </div>
      <div className="feature-strip">
        <div>
          <Terminal size={17} />
          <span>
            Understands the structure<span>Functions, classes, and context</span>
          </span>
        </div>
        <div>
          <Search size={17} />
          <span>
            Finds what matters<span>Keyword + semantic retrieval</span>
          </span>
        </div>
        <div>
          <BookOpen size={17} />
          <span>
            Shows its sources<span>Every answer, back to the code</span>
          </span>
        </div>
      </div>
      <footer className="landing-footer">
        <span>LESS SEARCHING. MORE BUILDING.</span>
        <span>
          Built for the curious developer <span className="footer-symbol">↗</span>
        </span>
      </footer>
    </div>
  );
}
