import { Maximize2, Play, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, Arch, ArchNode, errMsg, OpenFn } from "../api";
import { Timeline } from "../components/Timeline";
import { Empty, ErrorBox, PageHeader, Spinner, Tag } from "../components/ui";
import { useRun } from "../hooks/useRun";

const CELL_W = 220, CELL_H = 128, PAD_X = 90, PAD_Y = 55;

function Graph({ arch, selected, onSelect }: { arch: Arch; selected: string | null; onSelect: (id: string) => void }) {
  const inCycle = useMemo(() => new Set(arch.cycles.flatMap((c) => c.modules)), [arch]);
  const cycleEdges = useMemo(() => {
    const s = new Set<string>();
    arch.cycles.forEach((c) => c.modules.forEach((a) => c.modules.forEach((b) => s.add(a + ">" + b))));
    return s;
  }, [arch]);
  const layout = useMemo(() => {
    const nodes = [...arch.nodes].sort((a, b) => a.path.localeCompare(b.path));
    const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
    const rows = Math.ceil(nodes.length / columns);
    const pos: Record<string, { x: number; y: number }> = {};
    nodes.forEach((node, i) => {
      pos[node.id] = {
        x: PAD_X + (i % columns) * CELL_W + CELL_W / 2,
        y: PAD_Y + Math.floor(i / columns) * CELL_H + CELL_H / 2,
      };
    });
    return {
      pos,
      width: Math.max(760, columns * CELL_W + PAD_X * 2),
      height: Math.max(520, rows * CELL_H + PAD_Y * 2),
    };
  }, [arch]);
  const [viewBox, setViewBox] = useState({ x: 0, y: 0, width: layout.width, height: layout.height });
  const drag = useRef<{ x: number; y: number; viewX: number; viewY: number } | null>(null);
  useEffect(() => {
    setViewBox({ x: 0, y: 0, width: layout.width, height: layout.height });
  }, [layout]);
  const zoom = (factor: number, x = viewBox.x + viewBox.width / 2, y = viewBox.y + viewBox.height / 2) => {
    const width = Math.max(100, Math.min(layout.width * 2, viewBox.width * factor));
    const height = width * viewBox.height / viewBox.width;
    setViewBox({
      x: x - (x - viewBox.x) * (width / viewBox.width),
      y: y - (y - viewBox.y) * (height / viewBox.height),
      width,
      height,
    });
  };
  const pos = layout.pos;
  const label = (id: string) => id.split(/[./]/).slice(-2).join(".");
  return (
    <div className="relative h-full w-full overflow-hidden">
    <svg
      viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
      className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
      role="img"
      aria-label="Module dependency graph. Drag to pan and use the mouse wheel or controls to zoom."
      onWheel={(event) => {
        event.preventDefault();
        const bounds = event.currentTarget.getBoundingClientRect();
        const scale = Math.min(bounds.width / viewBox.width, bounds.height / viewBox.height);
        const offsetX = (bounds.width - viewBox.width * scale) / 2;
        const offsetY = (bounds.height - viewBox.height * scale) / 2;
        const x = viewBox.x + (event.clientX - bounds.left - offsetX) / scale;
        const y = viewBox.y + (event.clientY - bounds.top - offsetY) / scale;
        zoom(event.deltaY < 0 ? 0.85 : 1.18, x, y);
      }}
      onPointerDown={(event) => {
        drag.current = { x: event.clientX, y: event.clientY, viewX: viewBox.x, viewY: viewBox.y };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (!drag.current) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        const scale = Math.min(bounds.width / viewBox.width, bounds.height / viewBox.height);
        setViewBox((current) => ({
          ...current,
          x: drag.current!.viewX - (event.clientX - drag.current!.x) / scale,
          y: drag.current!.viewY - (event.clientY - drag.current!.y) / scale,
        }));
      }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
    >
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#4b5263" /></marker>
        <marker id="arrR" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#ff6b7a" /></marker>
      </defs>
      {arch.edges.map((e, i) => {
        const a = pos[e.source], b = pos[e.target]; if (!a || !b) return null;
        const bad = cycleEdges.has(e.source + ">" + e.target) && cycleEdges.has(e.target + ">" + e.source) || (inCycle.has(e.source) && inCycle.has(e.target) && cycleEdges.has(e.source + ">" + e.target));
        const hot = selected === e.source || selected === e.target;
        const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
        return <line key={i} x1={a.x + (dx / len) * 14} y1={a.y + (dy / len) * 14} x2={b.x - (dx / len) * 18} y2={b.y - (dy / len) * 18}
          stroke={bad ? "#ff6b7a" : hot ? "#8b8dff" : "#3a4050"} strokeWidth={hot || bad ? 1.8 : 1} markerEnd={bad ? "url(#arrR)" : "url(#arr)"} opacity={selected && !hot ? 0.25 : 1} />;
      })}
      {arch.nodes.map((n) => {
        const p = pos[n.id], sel = selected === n.id, r = 8 + Math.min(10, Math.sqrt(n.lines) / 2.5);
        return (
          <g key={n.id} transform={`translate(${p.x},${p.y})`} onClick={() => onSelect(n.id)} className="cursor-pointer" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onSelect(n.id)}>
            <title>{n.path}</title>
            <circle r={r} fill={inCycle.has(n.id) ? "#3b1d24" : "#1b1e2b"} stroke={inCycle.has(n.id) ? "#ff6b7a" : sel ? "#8b8dff" : "#5b5ee0"} strokeWidth={sel ? 3 : 1.5} />
            <text y={r + 13} textAnchor="middle" fontSize="11" fill={sel ? "#fff" : "#a5adbd"}>{label(n.id)}</text>
          </g>);
      })}
    </svg>
    <div className="absolute right-3 top-3 flex items-center gap-1 rounded-lg border border-ink-700 bg-ink-900/95 p-1 shadow-lg">
      <button className="btn btn-ghost h-8 w-8 p-0" aria-label="Zoom out" title="Zoom out" onClick={() => zoom(1.25)}><ZoomOut className="h-4 w-4" /></button>
      <button className="btn btn-ghost h-8 w-8 p-0" aria-label="Zoom in" title="Zoom in" onClick={() => zoom(0.8)}><ZoomIn className="h-4 w-4" /></button>
      <button className="btn btn-ghost h-8 w-8 p-0" aria-label="Fit graph to view" title="Fit graph to view" onClick={() => setViewBox({ x: 0, y: 0, width: layout.width, height: layout.height })}><Maximize2 className="h-4 w-4" /></button>
    </div>
    <div className="absolute bottom-3 left-3 rounded bg-ink-900/85 px-2 py-1 text-[11px] text-slate-400">Scroll to zoom · drag to pan</div>
    </div>
  );
}

export default function Architecture({ repoId, onOpen }: { repoId: string; onOpen: OpenFn }) {
  const [arch, setArch] = useState<Arch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const run = useRun();
  const load = () => api.get(`/repos/${repoId}/architecture`).then((r) => setArch(r.data)).catch((e) => setError(errMsg(e)));
  useEffect(() => { setArch(null); load(); }, [repoId]);
  const node: ArchNode | undefined = arch?.nodes.find((n) => n.id === sel);

  if (error) return <div className="p-6"><ErrorBox message={error} /></div>;
  if (!arch) return <div className="p-6"><Spinner /></div>;
  return (
    <div className="mx-auto max-w-6xl p-6">
      <PageHeader title="Architecture" sub="Modules and import relationships parsed from the source (Python via AST, JS/TS via import statements)."
        right={<button className="btn btn-primary" disabled={run.running} onClick={async () => { await run.start(repoId, "architecture"); load(); }}><Play className="h-4 w-4" />{run.running ? "Running…" : "Run Architecture Agent"}</button>} />
      {arch.cycles.length > 0 && (
        <div className="mb-5 rounded-lg border border-sev-high/40 bg-sev-high/10 p-4">
          <h2 className="text-sm font-semibold text-sev-high">{arch.cycles.length} circular dependency group(s)</h2>
          {arch.cycles.map((c, i) => <div key={i} className="mt-2 font-mono text-xs text-slate-200">{c.path.join(" → ")}</div>)}
        </div>)}
      {arch.nodes.length === 0 ? <Empty title="No modules found" hint="This repository has no Python or JavaScript/TypeScript source files to graph." /> : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="panel h-[520px] p-2 lg:col-span-2"><Graph arch={arch} selected={sel} onSelect={setSel} /></div>
          <div className="space-y-5">
            <div className="panel p-4">{node ? (<>
              <div className="font-mono text-sm text-white">{node.id}</div>
              <div className="mt-2 flex flex-wrap gap-1.5"><Tag>{node.language}</Tag><Tag>{node.lines} lines</Tag><Tag>{node.functions} functions</Tag><Tag>{node.classes} classes</Tag></div>
              <div className="mt-2 text-xs text-slate-400">{node.fan_in} module(s) depend on it · it depends on {node.fan_out}</div>
              {node.external_imports.length > 0 && <div className="mt-2 text-xs text-slate-500">External: {node.external_imports.join(", ")}</div>}
              <button className="btn btn-ghost mt-3" onClick={() => onOpen(node.path)}>Open source</button></>) : <p className="text-sm text-slate-500">Select a module in the graph. Red nodes and edges are part of a cycle.</p>}</div>
            <div className="panel p-4"><h2 className="mb-2 text-sm font-semibold text-white">Facts from the code</h2>
              <ul className="list-disc space-y-1 pl-4 text-sm text-slate-300">{arch.facts.facts.map((f, i) => <li key={i}>{f}</li>)}</ul></div>
          </div>
          <div className="panel p-4 lg:col-span-2"><h2 className="mb-2 text-sm font-semibold text-white">Most depended-on modules</h2>
            <table className="w-full text-sm"><thead className="text-left text-xs text-slate-500"><tr><th>Module</th><th className="text-right">Dependents</th><th className="text-right">Depends on</th><th className="text-right">Lines</th></tr></thead>
              <tbody>{[...arch.nodes].sort((a, b) => b.fan_in - a.fan_in).slice(0, 8).map((n) => <tr key={n.id} className="cursor-pointer border-t border-ink-700 hover:bg-ink-800" onClick={() => setSel(n.id)}><td className="py-1.5 font-mono text-xs text-slate-200">{n.id}</td><td className="text-right">{n.fan_in}</td><td className="text-right">{n.fan_out}</td><td className="text-right text-slate-400">{n.lines}</td></tr>)}</tbody></table></div>
          <div className="panel p-4"><h2 className="mb-2 text-sm font-semibold text-white">Top external packages</h2>
            <div className="flex flex-wrap gap-1.5">{arch.facts.top_external.length ? arch.facts.top_external.map(([n, c]) => <Tag key={n}>{n} ×{c}</Tag>) : <span className="text-sm text-slate-500">None</span>}</div></div>
        </div>)}
      <div className="panel mt-5 p-4">
        <div className="mb-2 flex items-center gap-2"><h2 className="text-sm font-semibold text-white">AI architecture summary</h2><Tag tone="warn">AI-generated</Tag></div>
        {arch.ai_summary ? (<div className="space-y-2 text-sm text-slate-300"><p>{arch.ai_summary.summary}</p>
          {arch.ai_summary.risks.length > 0 && <div><div className="text-xs text-slate-500">Risks</div><ul className="list-disc pl-5">{arch.ai_summary.risks.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
          {arch.ai_summary.recommendations.length > 0 && <div><div className="text-xs text-slate-500">Recommendations</div><ul className="list-disc pl-5">{arch.ai_summary.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}</div>)
          : <p className="text-sm text-slate-500">{arch.ai_enabled ? "Run the Architecture Agent to generate a summary." : "Add OPENROUTER_API_KEY to enable AI summaries. The facts above are computed without AI."}</p>}
      </div>
      {(run.events.length > 0 || run.running) && <div className="panel mt-5"><div className="border-b border-ink-700 px-4 py-2 text-sm font-semibold text-white">Agent activity</div><Timeline events={run.events} running={run.running} /></div>}
      {run.error && <div className="mt-4"><ErrorBox message={run.error} /></div>}
    </div>
  );
}
