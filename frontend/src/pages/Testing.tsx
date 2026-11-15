import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { api, errMsg, OpenFn, Testing as T } from "../api";
import { Timeline } from "../components/Timeline";
import { Empty, ErrorBox, PageHeader, Spinner, Stat, Tag } from "../components/ui";
import { useRun } from "../hooks/useRun";

export default function Testing({ repoId, onOpen }: { repoId: string; onOpen: OpenFn }) {
  const [t, setT] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useRun();
  const load = () => api.get(`/repos/${repoId}/testing`).then((r) => setT(r.data)).catch((e) => setError(errMsg(e)));
  useEffect(() => { setT(null); load(); }, [repoId]);
  if (error) return <div className="p-6"><ErrorBox message={error} /></div>;
  if (!t) return <div className="p-6"><Spinner /></div>;
  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader title="Testing center" sub="Finds the tests that exist and the modules no test touches. Uploaded code is never executed, so nothing here claims tests passed."
        right={<button className="btn btn-primary" disabled={run.running || !t.ai_enabled} title={t.ai_enabled ? "" : "Needs OPENROUTER_API_KEY"} onClick={async () => { await run.start(repoId, "testing"); load(); }}><Play className="h-4 w-4" />{run.running ? "Planning…" : "Generate test plan"}</button>} />
      <div className="mb-5 rounded-md border border-ink-600 bg-ink-900 p-3 text-sm text-slate-300">Execution status: <Tag tone="neutral">not executed</Tag> — running uploaded tests needs real OS-level isolation, which this MVP deliberately does not provide.</div>
      <div className="mb-5 grid grid-cols-3 gap-3"><Stat label="Test files" value={t.tests.length} /><Stat label="Test cases found" value={t.total_cases} /><Stat label="Potentially untested modules" value={t.untested_modules.length} /></div>
      {t.frameworks.length > 0 && <div className="mb-5 flex gap-2 text-sm text-slate-400">Frameworks: {t.frameworks.map((f) => <Tag key={f} tone="accent">{f}</Tag>)}</div>}
      <h2 className="mb-2 text-sm font-semibold text-white">Existing tests</h2>
      {t.tests.length ? <div className="space-y-2">{t.tests.map((x) => (
        <div key={x.path} className="panel p-3"><button onClick={() => onOpen(x.path)} className="font-mono text-sm text-accent hover:underline">{x.path}</button><span className="ml-2 text-xs text-slate-500">{x.case_count} case(s)</span>
          <div className="mt-1 flex flex-wrap gap-1.5">{x.cases.slice(0, 12).map((c) => <button key={c.name + c.line} onClick={() => onOpen(x.path, c.line, c.line)}><Tag>{c.name}</Tag></button>)}</div></div>))}</div>
        : <Empty title="No tests found" hint="No files matching common test naming conventions were discovered." />}
      <h2 className="mb-2 mt-7 text-sm font-semibold text-white">Potentially untested modules <span className="font-normal text-slate-500">(heuristic)</span></h2>
      <div className="panel divide-y divide-ink-700">{t.untested_modules.map((u) => (
        <div key={u.path} className="flex items-center gap-3 px-3 py-2 text-sm"><button onClick={() => onOpen(u.path)} className="font-mono text-accent hover:underline">{u.path}</button>
          <span className="ml-auto text-xs text-slate-500">{u.functions} fn · {u.classes} cls · {u.lines} lines</span></div>))}
        {t.untested_modules.length === 0 && <p className="p-3 text-sm text-slate-500">Every analysed module is imported by a test or matches a test file name.</p>}</div>
      <p className="mt-1 text-xs text-slate-500">{t.note}</p>
      <div className="mb-2 mt-7 flex items-center gap-2"><h2 className="text-sm font-semibold text-white">Test plan and sample tests</h2><Tag tone="warn">AI-generated · unverified drafts</Tag></div>
      {t.plan ? (<div className="space-y-3"><p className="text-sm text-slate-300">{t.plan.summary}</p>
        <ul className="list-disc pl-5 text-sm text-slate-300">{t.plan.priorities.map((p, i) => <li key={i}>{p}</li>)}</ul>
        {t.plan.sample_tests.map((s, i) => <div key={i} className="panel p-3"><div className="text-sm text-white">{s.description}</div><div className="mb-2 text-xs text-slate-500">{s.target} · {s.framework}</div>
          <pre className="overflow-x-auto rounded bg-ink-950 p-3 font-mono text-xs text-slate-200">{s.code}</pre></div>)}</div>)
        : <Empty title="No AI test plan yet" hint={t.ai_enabled ? "Generate a plan to get prioritised test ideas and sample tests." : "AI test plans are off because OPENROUTER_API_KEY is not set."} />}
      {(run.events.length > 0 || run.running) && <div className="panel mt-6"><div className="border-b border-ink-700 px-4 py-2 text-sm font-semibold text-white">Agent activity</div><Timeline events={run.events} running={run.running} /></div>}
      {run.error && <div className="mt-4"><ErrorBox message={run.error} /></div>}
    </div>
  );
}
