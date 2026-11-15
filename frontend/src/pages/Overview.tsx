import { FileArchive, Trash2, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, errMsg, Health, Meta, Overview as OV } from "../api";
import { Empty, ErrorBox, PageHeader, Spinner, Stat, Tag } from "../components/ui";

const STAGES = ["extracting", "scanning", "analyzing", "indexing", "ready"];

export default function Overview({ meta, health, onUploaded, onDelete }: { meta: Meta | null; health: Health | null; onUploaded: (m: Meta) => void; onDelete: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [ov, setOv] = useState<OV | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setOv(null);
    if (meta?.status === "ready") api.get(`/repos/${meta.id}/overview`).then((r) => setOv(r.data)).catch((e) => setError(errMsg(e)));
  }, [meta?.id, meta?.status]);

  async function upload(file?: File) {
    if (!file) return;
    setError(null); setBusy(true);
    try {
      const form = new FormData(); form.append("file", file);
      const { data } = await api.post("/repos", form);
      onUploaded(data);
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }

  const stageIdx = meta ? STAGES.indexOf(meta.stage) : -1;
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Repository" sub="Upload a ZIP of a source repository. RepoMind extracts it safely, indexes the code and lets agents analyse it. Nothing you upload is ever executed."
        right={meta && <button className="btn btn-ghost" onClick={onDelete}><Trash2 className="h-4 w-4" />Remove repository</button>} />
      {health && !health.openrouter_configured && (
        <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
          OpenRouter is not configured. Static analysis, the dependency graph, test discovery and code search work; AI answers, AI review and AI test plans stay off until you add <code className="font-mono">OPENROUTER_API_KEY</code> to <code className="font-mono">backend/.env</code> and restart the backend.
        </div>)}
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}

      {(!meta || meta.status === "error") && (
        <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]); }}
          className={`flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-14 text-center transition-colors ${drag ? "border-accent bg-accent/5" : "border-ink-600"}`}>
          <UploadCloud className="h-9 w-9 text-accent" />
          <p className="text-slate-200">Drop a repository ZIP here</p>
          <p className="text-sm text-slate-500">.git, node_modules, virtual environments, caches and secret files (.env, keys) are skipped.</p>
          <input ref={input} type="file" accept=".zip" hidden onChange={(e) => upload(e.target.files?.[0])} />
          <button className="btn btn-primary" disabled={busy} onClick={() => input.current?.click()}><FileArchive className="h-4 w-4" />{busy ? "Uploading…" : "Choose ZIP"}</button>
          {meta?.status === "error" && <ErrorBox message={`Processing failed: ${meta.error}`} />}
        </div>)}

      {meta?.status === "processing" && (
        <div className="panel p-6">
          <Spinner label={`Processing ${meta.name}: ${meta.stage}…`} />
          <div className="mt-4 h-1.5 overflow-hidden rounded bg-ink-700"><div className="h-full bg-accent transition-all" style={{ width: `${meta.progress}%` }} /></div>
          <div className="mt-3 flex gap-2 text-xs">{STAGES.map((s, i) => <Tag key={s} tone={i < stageIdx ? "good" : i === stageIdx ? "accent" : "neutral"}>{s}</Tag>)}</div>
        </div>)}

      {meta?.status === "ready" && !ov && !error && <Spinner />}
      {meta?.status === "ready" && ov && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Files" value={ov.total_files} /><Stat label="Lines" value={ov.total_lines.toLocaleString()} />
            <Stat label="Modules analysed" value={meta.counts?.modules ?? 0} /><Stat label="Indexed code chunks" value={meta.index?.chunks ?? 0} />
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <div className="panel p-4">
              <h2 className="mb-3 text-sm font-semibold text-white">Languages</h2>
              <div className="mb-3 flex h-2 overflow-hidden rounded">{ov.languages.filter((l) => l.is_code).map((l, i) => <div key={l.language} title={`${l.language} ${l.percent}%`} style={{ width: `${l.percent}%`, opacity: 1 - i * 0.15 }} className="bg-accent" />)}</div>
              <table className="w-full text-sm"><tbody>{ov.languages.map((l) => (
                <tr key={l.language} className="border-t border-ink-700"><td className="py-1.5 text-slate-200">{l.language}</td><td className="text-right text-slate-400">{l.files} files</td><td className="text-right text-slate-400">{l.lines.toLocaleString()} lines</td><td className="w-14 text-right text-slate-300">{l.percent != null ? `${l.percent}%` : ""}</td></tr>))}</tbody></table>
            </div>
            <div className="space-y-5">
              <div className="panel p-4"><h2 className="mb-3 text-sm font-semibold text-white">Frameworks detected</h2>
                {ov.frameworks.length ? <div className="flex flex-wrap gap-2">{ov.frameworks.map((f) => <Tag key={f} tone="accent">{f}</Tag>)}</div> : <p className="text-sm text-slate-500">None found in dependency files.</p>}</div>
              <div className="panel p-4"><h2 className="mb-3 text-sm font-semibold text-white">Dependency files</h2>
                {ov.manifests.length ? ov.manifests.map((m) => (<div key={m.file} className="mb-3 last:mb-0"><div className="font-mono text-xs text-slate-300">{m.file} <span className="text-slate-500">({m.type})</span></div>
                  <div className="mt-1 flex flex-wrap gap-1.5">{m.dependencies.slice(0, 30).map((d) => <Tag key={d.name}>{d.name}{d.version !== "*" ? ` ${d.version}` : ""}</Tag>)}</div></div>)) : <p className="text-sm text-slate-500">No manifest files found.</p>}</div>
              {ov.parse_errors.length > 0 && <div className="panel p-4"><h2 className="mb-2 text-sm font-semibold text-white">Files that could not be parsed</h2>{ov.parse_errors.map((p) => <div key={p.path} className="text-xs text-sev-high">{p.path}:{p.line} {p.message}</div>)}</div>}
            </div>
          </div>
          {meta.extraction && <p className="text-xs text-slate-500">Extraction skipped: {meta.extraction.skipped_secret} secret file(s), {meta.extraction.skipped_ignored} ignored-directory file(s), {meta.extraction.skipped_binary} binary file(s). Index: {meta.index?.embedding_backend}.</p>}
        </div>)}
    </div>
  );
}
export { Empty };
