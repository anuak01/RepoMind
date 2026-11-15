import { useEffect, useState } from "react";
import { api, errMsg, RunEvent, RunSummary } from "../api";
import { Timeline } from "../components/Timeline";
import { Empty, ErrorBox, PageHeader, Spinner, Tag } from "../components/ui";

export default function Activity({ repoId, refreshKey }: { repoId: string; refreshKey: number }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.get(`/repos/${repoId}/runs`).then((r) => setRuns(r.data)).catch((e) => setError(errMsg(e))); }, [repoId, refreshKey]);
  async function pick(id: string) {
    setActive(id);
    try { setEvents((await api.get(`/runs/${id}`)).data.events ?? []); } catch (e) { setError(errMsg(e)); }
  }
  if (error) return <div className="p-6"><ErrorBox message={error} /></div>;
  if (!runs) return <div className="p-6"><Spinner /></div>;
  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader title="Agent activity" sub="Recorded execution events from every run: which agent worked, its task, tool calls and results. Live events also stream in Chat and on each dashboard." />
      {runs.length === 0 ? <Empty title="No runs yet" hint="Ask a question in Chat or run an agent from the Architecture, Review, Testing or Report pages." /> : (
        <div className="grid gap-5 md:grid-cols-3">
          <div className="space-y-2">{runs.map((r) => (
            <button key={r.id} onClick={() => pick(r.id)} className={`panel w-full p-3 text-left ${active === r.id ? "border-accent-dim" : ""}`}>
              <div className="flex items-center gap-2"><Tag tone="accent">{r.mode}</Tag><Tag tone={r.status === "completed" ? "good" : "warn"}>{r.status}</Tag></div>
              <div className="mt-1 truncate text-sm text-slate-200">{r.message || `${r.mode} run`}</div><div className="text-xs text-slate-500">{new Date(r.started_at).toLocaleString()} · {r.event_count} events</div></button>))}</div>
          <div className="panel md:col-span-2">{active ? <Timeline events={events} /> : <p className="p-4 text-sm text-slate-500">Select a run to inspect its events.</p>}</div>
        </div>)}
    </div>
  );
}
