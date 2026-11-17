import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Command,
  FileCode2,
  GitBranch,
  Github,
  HelpCircle,
  LayoutGrid,
  Loader2,
  Menu,
  MessageSquare,
  Moon,
  Plus,
  Search,
  ShieldCheck,
  Sun,
  Square,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { z } from "zod";
import {
  api,
  useMock,
  type Answer,
  type AnswerStreamEvent,
  type Citation,
  type JobStatus,
  type Repo,
} from "@/api";
import { demoFiles, demoRepo } from "@/lib/demo";
import { migrateStorage } from "@/lib/storage";
import { requestHistory } from "@/lib/chat-history";
import { healthReady } from "@/lib/backend-status";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Brand } from "./brand";
import { BackendBanner } from "./backend-banner";
import { CodeViewer } from "./code-viewer";
import { Conversation, type Message } from "./conversation";
import { FileTree } from "./file-tree";
import { Indexing } from "./indexing";
import { Landing } from "./landing";
import { SearchSettingsDialog, type SearchSettings } from "./settings";

const citationSchema = z.object({ path: z.string(), startLine: z.number(), endLine: z.number() });
const sessionSchema = z.object({
  id: z.string(),
  title: z.string(),
  repo: z.object({
    repoId: z.string(),
    repoUrl: z.string(),
    files: z.number(),
    chunks: z.number(),
    indexedAt: z.string(),
  }),
  messages: z.array(
    z.object({
      id: z.string(),
      question: z.string(),
      error: z.string().optional(),
      streaming: z.boolean().optional(),
      stopped: z.boolean().optional(),
      response: z
        .object({
          answer: z.string(),
          citations: z.array(citationSchema),
          chunks: z.array(
            citationSchema.extend({
              score: z.number(),
              code: z.string(),
              method: z.enum(["bm25", "vector", "hybrid", "reranked"]),
            }),
          ),
          notFound: z.boolean(),
          latencyMs: z.object({ retrieve: z.number(), rerank: z.number(), generate: z.number() }),
          generationMode: z.string().optional(),
          rerankApplied: z.boolean().optional(),
          llmCalls: z.number().optional(),
          rewrittenQuestion: z.string().nullable().optional(),
          rewriteMode: z.string().optional(),
          agenticUsed: z.boolean().optional(),
          retried: z.boolean().optional(),
          totalMs: z.number().optional(),
          cached: z.boolean().optional(),
        })
        .optional(),
    }),
  ),
});
type Session = { id: string; title: string; repo: Repo; messages: Message[] };
const repoName = (repo: Repo | null) =>
  repo?.repoUrl.split("/").filter(Boolean).at(-1) ?? "Workspace";
const uid = () => crypto.randomUUID();

export function Workspace() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"landing" | "indexing" | "chat">("landing");
  const [repo, setRepo] = useState<Repo | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [theme, setTheme] = useState("dark");
  const [settings, setSettings] = useState<SearchSettings>({
    hybrid: true,
    rerank: true,
    topK: 8,
    agentic: false,
  });
  const [citation, setCitation] = useState<Citation | null>(null);
  const [codeOpen, setCodeOpen] = useState(true);
  const [mobileTab, setMobileTab] = useState("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dialog, setDialog] = useState<"help" | "repos" | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const [indexJob, setIndexJob] = useState<{
    jobId: string;
    repoId: string;
    repoUrl: string;
  } | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    retry: true,
    retryDelay: 15000,
    refetchInterval: 5000,
  });
  const backendReady = (useMock || healthReady(health.data)) && health.failureCount === 0;
  const [slowRequest, setSlowRequest] = useState(false);
  useEffect(() => {
    setSlowRequest(false);
    if (!busy && !pendingId) return;
    const timer = setTimeout(() => setSlowRequest(true), 10000);
    return () => clearTimeout(timer);
  }, [busy, pendingId]);
  const repositories = useQuery({ queryKey: ["repos"], queryFn: api.repos, retry: false });
  const currentSession = sessions.find((session) => session.id === sessionId);
  const messages = currentSession?.messages ?? [];
  const isDemo = Boolean(repo?.repoId.startsWith("demo:"));
  const files = useQuery({
    queryKey: ["files", repo?.repoId],
    queryFn: () => api.files(repo!.repoId),
    enabled: Boolean(repo),
    retry: false,
  });

  useEffect(() => {
    try {
      migrateStorage(localStorage);
      const saved = localStorage.getItem("askrepo:history");
      if (saved)
        setSessions(
          z
            .array(sessionSchema)
            .parse(JSON.parse(saved))
            .slice(0, 20)
            .map((session) => ({
              ...session,
              messages: session.messages.map((message) =>
                message.streaming
                  ? { ...message, streaming: false, stopped: true }
                  : message.response || message.error
                    ? message
                    : {
                        ...message,
                        error: "This answer was interrupted. Send the question again to retry.",
                      },
              ),
            })),
        );
      const savedTheme = localStorage.getItem("askrepo:theme");
      if (savedTheme === "light") setTheme("light");
      const savedSettings = localStorage.getItem("askrepo:settings");
      if (savedSettings)
        setSettings(
          z
            .object({
              hybrid: z.boolean(),
              rerank: z.boolean(),
              topK: z.number().min(3).max(20),
              agentic: z.boolean().default(false),
            })
            .parse(JSON.parse(savedSettings)),
        );
    } catch {
      /* Invalid or unavailable storage starts a clean session. */
    }
    setHydrated(true);
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    if (hydrated)
      try {
        localStorage.setItem("askrepo:theme", theme);
      } catch {
        /* Storage is optional. */
      }
  }, [theme, hydrated]);
  useEffect(() => {
    if (!hydrated) return;
    function save() {
      try {
        localStorage.setItem("askrepo:history", JSON.stringify(sessions.slice(0, 20)));
        localStorage.setItem("askrepo:settings", JSON.stringify(settings));
      } catch {
        /* Quota limits must not interrupt chat. */
      }
    }
    if (!sessions.some((session) => session.messages.some((message) => message.streaming))) {
      save();
      return;
    }
    const timer = setTimeout(save, 500);
    return () => clearTimeout(timer);
  }, [sessions, settings, hydrated]);
  useEffect(() => () => activeRequest.current?.abort(), []);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        if (view === "chat") input.current?.focus();
        else document.getElementById("repo-url")?.focus();
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [view]);
  useEffect(() => {
    if (!indexJob || view !== "indexing") return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const status = await api.indexStatus(indexJob!.jobId);
        if (!active) return;
        setJob(status);
        if (status.status === "ready") {
          openRepo({
            repoId: indexJob!.repoId,
            repoUrl: indexJob!.repoUrl,
            files: status.filesParsed,
            chunks: status.chunksCreated,
            indexedAt: new Date().toISOString(),
          });
          void queryClient.invalidateQueries({ queryKey: ["repos"] });
        } else if (status.status !== "failed") timer = setTimeout(poll, 800);
      } catch (reason) {
        if (active)
          setError(reason instanceof Error ? reason.message : "Could not fetch indexing progress.");
      }
    }
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [indexJob, view, queryClient]);

  function openRepo(nextRepo: Repo) {
    activeRequest.current?.abort();
    setRepo(nextRepo);
    setView("chat");
    setSessionId(null);
    setCitation(null);
    setQuestion("");
    setError("");
    setSidebarOpen(false);
    setDialog(null);
    setMobileTab("chat");
  }
  function home() {
    activeRequest.current?.abort();
    setView("landing");
    setError("");
    setRepo(null);
    setSessionId(null);
    setSidebarOpen(false);
  }
  function openSession(session: Session) {
    activeRequest.current?.abort();
    setRepo(session.repo);
    setSessionId(session.id);
    setView("chat");
    setCitation(null);
    setSidebarOpen(false);
    setMobileTab("chat");
  }
  async function index(url: string) {
    if (!backendReady) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.index(url);
      setIndexJob({ ...result, repoUrl: url });
      setJob(null);
      setView("indexing");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start indexing.");
    } finally {
      setBusy(false);
    }
  }
  async function openDemo(name: string) {
    if (!backendReady) return;
    if (useMock) {
      openRepo(demoRepo(name));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const target = `https://github.com/ShlokMaharwal/${name}`;
      const available = await queryClient.fetchQuery({
        queryKey: ["repos"],
        queryFn: api.repos,
        staleTime: 0,
        retry: false,
      });
      const existing = available.find(
        (item) => item.repoUrl.toLowerCase() === target.toLowerCase(),
      );
      if (existing) openRepo(existing);
      else await index(target);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to open this repository.");
    } finally {
      setBusy(false);
    }
  }
  async function ask(text: string) {
    if (!repo || !backendReady || !text.trim() || text.trim().length > 500 || pendingId) return;
    const id = uid();
    const activeSessionId = sessionId ?? uid();
    const message: Message = { id, question: text.trim(), streaming: true };
    const controller = new AbortController();
    activeRequest.current = controller;
    if (!sessionId) {
      setSessions((previous) =>
        [
          { id: activeSessionId, title: message.question, repo, messages: [message] },
          ...previous,
        ].slice(0, 20),
      );
      setSessionId(activeSessionId);
    } else
      setSessions((previous) =>
        previous.map((session) =>
          session.id === activeSessionId
            ? { ...session, messages: [...session.messages, message] }
            : session,
        ),
      );
    setQuestion("");
    setPendingId(id);
    function updateMessage(change: (item: Message) => Message) {
      setSessions((previous) =>
        previous.map((session) =>
          session.id === activeSessionId
            ? {
                ...session,
                messages: session.messages.map((item) => (item.id === id ? change(item) : item)),
              }
            : session,
        ),
      );
    }
    const empty: Answer = {
      answer: "",
      chunks: [],
      citations: [],
      notFound: false,
      latencyMs: { retrieve: 0, rerank: 0, generate: 0 },
    };
    function onEvent(event: AnswerStreamEvent) {
      if (controller.signal.aborted) return;
      updateMessage((item) => {
        const response = item.response ?? empty;
        switch (event.event) {
          case "status":
            return { ...item, status: event.data.message };
          case "chunks":
            return { ...item, response: { ...response, chunks: event.data } };
          case "token":
            return {
              ...item,
              response: { ...response, answer: response.answer + event.data.text },
            };
          case "answer_clean":
            return { ...item, response: { ...response, answer: event.data.answer } };
          case "citations":
            return { ...item, response: { ...response, citations: event.data } };
          case "done":
            return {
              ...item,
              streaming: false,
              status: "",
              response: { ...response, ...event.data },
            };
          default:
            return item;
        }
      });
    }
    try {
      const response = await api.askStream(
        {
          repoId: repo.repoId,
          question: message.question,
          history: requestHistory(messages),
          ...settings,
          rerank: settings.rerank && !health.data?.liteMode,
          agentic: settings.agentic && health.data?.agenticEnabled !== false,
        },
        onEvent,
        controller.signal,
      );
      setSessions((previous) =>
        previous.map((session) =>
          session.id === activeSessionId
            ? {
                ...session,
                messages: session.messages.map((item) =>
                  item.id === id ? { ...item, response, streaming: false, status: "" } : item,
                ),
              }
            : session,
        ),
      );
    } catch (reason) {
      setSessions((previous) =>
        previous.map((session) =>
          session.id === activeSessionId
            ? {
                ...session,
                messages: session.messages.map((item) =>
                  item.id === id
                    ? {
                        ...item,
                        streaming: false,
                        stopped: controller.signal.aborted,
                        status: "",
                        error: controller.signal.aborted
                          ? undefined
                          : reason instanceof Error
                            ? reason.message
                            : "Could not answer this question.",
                      }
                    : item,
                ),
              }
            : session,
        ),
      );
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setPendingId(null);
      }
    }
  }
  function showCitation(value: Citation) {
    setCitation(value);
    setCodeOpen(true);
    setMobileTab("code");
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }
  const paths =
    files.data?.map((file) => file.path) ??
    (isDemo
      ? Object.keys(demoFiles)
      : [
          ...new Set(
            messages.flatMap(
              (message) => message.response?.chunks.map((chunk) => chunk.path) ?? [],
            ),
          ),
        ]);

  return (
    <div className="askrepo-app" data-ready={hydrated}>
      <aside className={`app-sidebar ${sidebarOpen ? "mobile-open" : ""}`}>
        <div className="sidebar-brand">
          <button onClick={home} aria-label="AskRepo home">
            <Brand />
          </button>
          <span className="version-tag">BETA</span>
          <button
            className="icon-button mobile-close"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            <X size={17} />
          </button>
        </div>
        <div className="sidebar-workspace">
          <span className="workspace-avatar">A</span>
          <div>
            <strong>Personal workspace</strong>
            <span>Local environment</span>
          </div>
          <ChevronDown size={13} />
        </div>
        <nav className="sidebar-nav" aria-label="Workspace">
          <span className="sidebar-label">WORKSPACE</span>
          <button className={view === "landing" ? "active" : ""} onClick={home}>
            <LayoutGrid size={15} />
            Overview<span className="nav-shortcut">⌘ K</span>
          </button>
          <button onClick={() => setDialog("repos")}>
            <GitBranch size={15} />
            Repositories<span className="nav-count">{repositories.data?.length ?? 0}</span>
          </button>
        </nav>
        {repo && (
          <div className="sidebar-repo">
            <div className="sidebar-label">
              REPOSITORY <span>{isDemo ? "DEMO" : "INDEXED"}</span>
            </div>
            <a className="repo-title" href={repo.repoUrl} target="_blank" rel="noreferrer">
              <Github size={15} />
              <span>{repoName(repo)}</span>
              <ArrowRight size={12} />
            </a>
            <div className="repo-stats">
              <span>{repo.files} files</span>
              <span>·</span>
              <span>{repo.chunks} chunks</span>
            </div>
            <details className="sidebar-files" open>
              <summary>
                <ChevronRight size={12} />
                Files<span>{paths.length}</span>
              </summary>
              <FileTree
                paths={paths}
                onFile={(path) => showCitation({ path, startLine: 1, endLine: 1 })}
              />
            </details>
          </div>
        )}
        <div className="sidebar-history">
          <div className="sidebar-label">
            RECENT CONVERSATIONS{" "}
            <button
              className="icon-button"
              aria-label="New conversation"
              onClick={() => {
                if (repo) openRepo(repo);
                else home();
              }}
            >
              <Plus size={13} />
            </button>
          </div>
          {sessions.length ? (
            sessions.slice(0, 10).map((session) => (
              <button
                className={`history-item ${session.id === sessionId ? "active" : ""}`}
                key={session.id}
                onClick={() => openSession(session)}
              >
                <MessageSquare size={13} />
                <span>{session.title}</span>
              </button>
            ))
          ) : (
            <div className="history-empty">
              <MessageSquare size={19} strokeWidth={1.2} />
              <p>
                Your next discovery
                <br />
                starts with a question.
              </p>
            </div>
          )}
        </div>
        <button className="new-repo-button" onClick={home}>
          <Plus size={15} /> New repository
        </button>
        <div className="sidebar-bottom">
          <button onClick={() => setDialog("help")}>
            <HelpCircle size={14} /> Help & documentation <ArrowRight size={12} />
          </button>
          <div className="connection-status">
            <span className={`status-dot ${health.data ? "online" : ""}`} />
            {useMock
              ? "Mock mode enabled"
              : health.isPending
                ? "Connecting to backend"
                : health.data
                  ? "Backend connected"
                  : "Backend offline"}
            <span className="mono">v0.1</span>
          </div>
        </div>
      </aside>
      {sidebarOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <main className="app-main">
        <header className="app-header">
          <div className="header-breadcrumb">
            <button
              className="icon-button mobile-menu"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={18} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {view === "landing" ? "Overview" : view === "indexing" ? "Indexing" : repoName(repo)}
            </strong>
            {isDemo && <span className="subtle-badge">DEMO</span>}
          </div>
          <div className="header-actions">
            <span className="header-note">
              <ShieldCheck size={13} /> Grounded in your code
            </span>
            <span className="header-divider" />
            <button
              className="icon-button"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              disabled={!hydrated}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <a
              className="icon-button"
              href="https://github.com/ShlokMaharwal"
              target="_blank"
              rel="noreferrer"
              aria-label="Demo repositories on GitHub"
            >
              <Github size={16} />
            </a>
          </div>
        </header>
        <BackendBanner
          health={health.data}
          unreachable={!health.data || health.failureCount > 0}
          slow={slowRequest}
        />
        {view === "landing" ? (
          <div className="landing-scroll">
            <Landing
              onIndex={(url) => void index(url)}
              onDemo={(name) => void openDemo(name)}
              busy={busy || !hydrated || !backendReady}
              error={error}
            />
          </div>
        ) : view === "indexing" ? (
          <div className="landing-scroll">
            <Indexing url={indexJob?.repoUrl ?? ""} job={job} error={error} onBack={home} />
          </div>
        ) : (
          repo && (
            <>
              <div className="chat-subheader">
                <div>
                  <GitBranch size={14} />
                  <strong>{repoName(repo)}</strong>
                  <span className="branch-badge">snapshot</span>
                </div>
                <div>
                  <button className="text-button" onClick={() => openRepo(repo)}>
                    <Plus size={13} /> New chat
                  </button>
                  <SearchSettingsDialog
                    value={{
                      ...settings,
                      rerank: settings.rerank && !health.data?.liteMode,
                      agentic: settings.agentic && health.data?.agenticEnabled !== false,
                    }}
                    onChange={setSettings}
                    rerankerAvailable={!health.data?.liteMode}
                    agenticAvailable={health.data?.agenticEnabled !== false}
                  />
                  <button
                    className="icon-button"
                    aria-label="Toggle source explorer"
                    onClick={() => setCodeOpen(!codeOpen)}
                  >
                    <FileCode2 size={16} />
                  </button>
                </div>
              </div>
              {isDemo && (
                <div className="demo-banner">
                  <span>DEMO WORKSPACE</span> Illustrative fixtures · not verified repository
                  contents{" "}
                  <button onClick={home}>
                    Connect your own <ArrowRight size={11} />
                  </button>
                </div>
              )}
              <div className="mobile-tabs">
                <button
                  className={mobileTab === "chat" ? "active" : ""}
                  onClick={() => setMobileTab("chat")}
                >
                  <MessageSquare size={13} /> Chat
                </button>
                <button
                  className={mobileTab === "code" ? "active" : ""}
                  onClick={() => {
                    setMobileTab("code");
                    setCodeOpen(true);
                  }}
                >
                  <FileCode2 size={13} /> Code
                </button>
              </div>
              <div className={`workspace-panels ${codeOpen ? "with-code" : ""}`}>
                <section
                  className={`chat-panel ${mobileTab === "code" ? "mobile-hidden" : ""}`}
                  aria-label="Chat"
                >
                  <div className="chat-scroll">
                    <Conversation
                      repoId={repo.repoId}
                      messages={messages}
                      repoName={repoName(repo)}
                      pending={Boolean(pendingId) || !backendReady}
                      onAsk={(value) => void ask(value)}
                      onCitation={showCitation}
                    />
                  </div>
                  <div className="composer-area">
                    <form onSubmit={submit} className="composer">
                      <label className="sr-only" htmlFor="question">
                        Ask a question about the repository
                      </label>
                      <textarea
                        id="question"
                        ref={input}
                        rows={2}
                        maxLength={500}
                        value={question}
                        disabled={Boolean(pendingId) || !backendReady}
                        placeholder={`Ask anything about ${repoName(repo)}…`}
                        onChange={(event) => setQuestion(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.shiftKey) {
                            event.preventDefault();
                            void ask(question);
                          }
                        }}
                      />
                      <div className="composer-bottom">
                        <span>
                          <Search size={12} />
                          {settings.hybrid ? "Hybrid search" : "Keyword search"}
                          <span>·</span>
                          {settings.rerank && !health.data?.liteMode
                            ? "Reranker on"
                            : "Reranker off"}
                        </span>
                        <div>
                          <span className="character-count">{question.length}/500</span>
                          {pendingId ? (
                            <button
                              className="send-button"
                              type="button"
                              onClick={() => activeRequest.current?.abort()}
                              aria-label="Stop response"
                              title="Stop response"
                            >
                              <Square size={14} fill="currentColor" />
                            </button>
                          ) : (
                            <button
                              className="send-button"
                              type="submit"
                              disabled={!question.trim() || Boolean(pendingId) || !backendReady}
                              aria-label="Send question"
                            >
                              <ArrowUp size={17} />
                            </button>
                          )}
                        </div>
                      </div>
                    </form>
                    <div className="composer-footnote">
                      <span>Check the sources. Understand the answer.</span>
                      <span>
                        <Command size={10} /> K to focus <span>·</span> ↵ to send
                      </span>
                    </div>
                  </div>
                </section>
                {codeOpen && (
                  <div
                    className={`source-panel ${mobileTab === "chat" ? "mobile-code-hidden" : ""}`}
                  >
                    <CodeViewer
                      repoId={repo.repoId}
                      citation={citation}
                      onClose={() => {
                        setCodeOpen(false);
                        setMobileTab("chat");
                      }}
                    />
                  </div>
                )}
              </div>
            </>
          )
        )}
      </main>
      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
      >
        <DialogContent className="ask-dialog">
          <DialogHeader>
            <DialogTitle>
              {dialog === "repos" ? "Your repositories" : "A little context goes a long way."}
            </DialogTitle>
            <DialogDescription>
              {dialog === "repos"
                ? "Open an indexed repository, or connect a new one."
                : "AskRepo finds answers in code and takes you directly to the source."}
            </DialogDescription>
          </DialogHeader>
          {dialog === "repos" ? (
            <div className="repo-list">
              {repositories.isPending ? (
                <div className="skeleton-list">
                  <div />
                  <div />
                  <div />
                </div>
              ) : repositories.error ? (
                <div className="error-notice" role="alert">
                  Backend unavailable. Start the API server to see indexed repositories.
                  <button className="text-button" onClick={() => void repositories.refetch()}>
                    Retry <ArrowRight size={12} />
                  </button>
                </div>
              ) : repositories.data?.length ? (
                repositories.data.map((item) => (
                  <button key={item.repoId} onClick={() => openRepo(item)}>
                    <Github size={17} />
                    <span>
                      {repoName(item)}
                      <small>
                        {item.files} files · {item.chunks} chunks
                      </small>
                    </span>
                    <ArrowRight size={15} />
                  </button>
                ))
              ) : (
                <div className="repo-list-empty">
                  <GitBranch size={28} />
                  <h3>A clean slate.</h3>
                  <p>Your indexed repositories will appear here.</p>
                </div>
              )}
              <button
                className="primary-button"
                onClick={() => {
                  setDialog(null);
                  home();
                }}
              >
                <Plus size={14} /> Connect a repository
              </button>
            </div>
          ) : (
            <div className="help-content">
              <div>
                <span>01</span>
                <div>
                  <strong>Connect a public GitHub repository</strong>
                  <p>
                    Paste a repository URL. AskRepo indexes its files without executing any code.
                  </p>
                </div>
              </div>
              <div>
                <span>02</span>
                <div>
                  <strong>Ask in your own words</strong>
                  <p>
                    Search for behavior, follow an implementation, or find the function you need.
                  </p>
                </div>
              </div>
              <div>
                <span>03</span>
                <div>
                  <strong>Follow the evidence</strong>
                  <p>
                    Click a citation to open the exact file and line range. Use retrieval settings
                    to tune the context.
                  </p>
                </div>
              </div>
              <p className="muted small">
                Demo cards connect to the public repositories. Mock mode uses labeled fixtures. Chat
                history is saved only in this browser. Clear this site’s storage to remove it.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
