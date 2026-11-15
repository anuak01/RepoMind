import { Download, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { api, errMsg, Health, OpenFn } from "../api";
import { Markdown } from "../components/Markdown";
import { Timeline } from "../components/Timeline";
import { Empty, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useRun } from "../hooks/useRun";

export default function Report({ repoId, health, onOpen }: { repoId: string; health: Health | null; onOpen: OpenFn }) {
  const [md, setMd] = useState<string | null>(null);
  const [cites, setCites] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const run = useRun();
  const load = () => api.get(`/repos/${repoId}/report`).then((r) => { setMd(r.data?.markdown ?? null); setCites(r.data?.citations ?? []); }).catch((e) => setError(errMsg(e))).finally(() => setLoading(false));
  useEffect(() => { setLoading(true); setMd(null); load(); }, [repoId]);
  async function generate() { await run.start(repoId, "report"); load(); }
  const download = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([md ?? ""], { type: "text/markdown" })); a.download = "repomind-report.md"; a.click(); };
  // Findings sections cite real lines from static rules; executive-summary citations stay limited to the verified list
  const clickable = Array.from((md ?? "").split("\n## Architecture").slice(1).join("\n## Architecture").matchAll(/\[([\w./\\@\- ]+?):(\d+)(?:-(\d+))?\]/g)).map((m) => ({ path: m[1], start: +m[2], end: m[3] ? +m[3] : +m[2], language: "", snippet: "" }));
  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader title="Final report" sub="Runs the Architecture, Code Review, Testing and Analyst agents and consolidates verified facts and clearly labelled AI output."
        right={<div className="flex gap-2">{md && <button className="btn btn-ghost" onClick={download}><Download className="h-4 w-4" />Download .md</button>}
          <button className="btn btn-primary" disabled={run.running} onClick={generate}><Play className="h-4 w-4" />{run.running ? "Generating…" : md ? "Regenerate" : "Generate report"}</button></div>} />
      {health && !health.openrouter_configured && <p className="mb-4 text-sm text-amber-300">OpenRouter is not configured: the report will contain only deterministic analysis (no AI summary, suggestions or test plan).</p>}
      {error && <ErrorBox message={error} />}
      {(run.events.length > 0 || run.running) && <div className="panel mb-5"><div className="border-b border-ink-700 px-4 py-2 text-sm font-semibold text-white">Agent activity</div><div className="max-h-72 overflow-auto"><Timeline events={run.events} running={run.running} /></div></div>}
      {run.error && <ErrorBox message={run.error} />}
      {loading ? <Spinner /> : md ? <div className="panel p-6"><Markdown text={md} citations={[...cites, ...clickable]} onOpen={onOpen} /></div>
        : !run.running && <Empty title="No report yet" hint="Generate a report to get a consolidated analysis with architecture, dependencies, review findings, testing recommendations and citations." />}
    </div>
  );
}
