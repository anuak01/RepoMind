import { Activity as ActivityIcon, BookText, Boxes, FileSearch, FolderTree, LayoutDashboard, MessageSquare, ShieldCheck, TestTube2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, errMsg, Health, Meta } from "./api";
import Activity from "./pages/Activity";
import Architecture from "./pages/Architecture";
import Chat from "./pages/Chat";
import Explorer from "./pages/Explorer";
import Overview from "./pages/Overview";
import Report from "./pages/Report";
import Review from "./pages/Review";
import Testing from "./pages/Testing";
import { Empty, ErrorBox, Tag } from "./components/ui";

type View = "overview" | "explorer" | "chat" | "architecture" | "review" | "testing" | "activity" | "report";
const NAV: { id: View; label: string; icon: typeof FolderTree }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard }, { id: "explorer", label: "Explorer", icon: FolderTree },
  { id: "chat", label: "Ask codebase", icon: MessageSquare }, { id: "architecture", label: "Architecture", icon: Boxes },
  { id: "review", label: "Code review", icon: ShieldCheck }, { id: "testing", label: "Testing", icon: TestTube2 },
  { id: "activity", label: "Agent activity", icon: ActivityIcon }, { id: "report", label: "Report", icon: BookText },
];

export default function App() {
  const [view, setView] = useState<View>("overview");
  const [repoId, setRepoId] = useState<string | null>(localStorage.getItem("repomind.repo"));
  const [meta, setMeta] = useState<Meta | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [target, setTarget] = useState<{ path: string; start?: number; end?: number } | null>(null);

  useEffect(() => { api.get("/health").then((r) => { setHealth(r.data); setBackendError(null); }).catch((e) => setBackendError(`Cannot reach the backend (${errMsg(e)}). Start it with uvicorn on port 8000.`)); }, []);

  useEffect(() => {
    if (!repoId) { setMeta(null); return; }
    let stop = false, timer: number;
    const poll = async () => {
      try {
        const { data } = await api.get(`/repos/${repoId}`);
        if (stop) return;
        setMeta(data);
        if (data.status === "processing") timer = window.setTimeout(poll, 800);
      } catch { if (!stop) { localStorage.removeItem("repomind.repo"); setRepoId(null); } }
    };
    poll();
    return () => { stop = true; clearTimeout(timer); };
  }, [repoId]);

  const select = (m: Meta) => { localStorage.setItem("repomind.repo", m.id); setRepoId(m.id); setMeta(m); setTarget(null); setView("overview"); };
  const remove = async () => { if (!repoId || !confirm("Remove this repository and its index?")) return; await api.delete(`/repos/${repoId}`); localStorage.removeItem("repomind.repo"); setRepoId(null); setMeta(null); };
  const open = useCallback((path: string, start?: number, end?: number) => { setTarget({ path, start, end }); setView("explorer"); }, []);
  const ready = meta?.status === "ready" && repoId;

  return (
    <div className="flex h-full flex-col md:flex-row">
      <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-ink-700 bg-ink-900 p-2 md:w-60 md:flex-col md:overflow-visible md:border-b-0 md:border-r md:p-3" aria-label="Main">
        <div className="hidden px-2 pb-4 pt-1 md:block"><div className="text-lg font-semibold tracking-tight text-white">RepoMind</div><div className="text-xs text-slate-500">Code intelligence</div></div>
        {NAV.map(({ id, label, icon: Icon }) => {
          const locked = id !== "overview" && !ready;
          return <button key={id} disabled={locked} onClick={() => setView(id)} aria-current={view === id ? "page" : undefined}
            className={`flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${view === id ? "bg-accent-dim/25 text-white" : "text-slate-400 hover:bg-ink-800 hover:text-slate-200"} disabled:opacity-35`}><Icon className="h-4 w-4" />{label}</button>;
        })}
        <div className="mt-auto hidden space-y-2 border-t border-ink-700 px-2 pt-3 text-xs md:block">
          {meta && <div className="truncate text-slate-300" title={meta.name}><FileSearch className="mr-1 inline h-3.5 w-3.5" />{meta.name}</div>}
          {health && <div className="flex flex-wrap gap-1"><Tag tone={health.openrouter_configured ? "good" : "warn"}>{health.openrouter_configured ? `OpenRouter: ${health.model}` : "OpenRouter key missing"}</Tag></div>}
        </div>
      </nav>
      <main className="min-h-0 min-w-0 flex-1 overflow-auto">
        {backendError && <div className="p-4"><ErrorBox message={backendError} /></div>}
        {view === "overview" && <div className="p-6"><Overview meta={meta} health={health} onUploaded={select} onDelete={remove} /></div>}
        {view !== "overview" && !ready && <div className="p-8"><Empty title="Upload a repository first" hint="Every screen reads from the analysed repository." /></div>}
        {ready && view === "explorer" && <div className="h-full"><Explorer repoId={repoId} target={target} onSelect={(p) => open(p)} /></div>}
        {ready && view === "chat" && <div className="h-full"><Chat repoId={repoId} health={health} onOpen={open} /></div>}
        {ready && view === "architecture" && <Architecture repoId={repoId} onOpen={open} />}
        {ready && view === "review" && <Review repoId={repoId} onOpen={open} />}
        {ready && view === "testing" && <Testing repoId={repoId} onOpen={open} />}
        {ready && view === "activity" && <Activity repoId={repoId} refreshKey={0} />}
        {ready && view === "report" && <Report repoId={repoId} health={health} onOpen={open} />}
      </main>
    </div>
  );
}
