import { AlertCircle, Bot, CheckCircle2, Info, ListChecks, Play, Wrench, CornerDownRight } from "lucide-react";
import { useEffect, useRef } from "react";
import { RunEvent } from "../api";

const AGENT_COLOR: Record<string, string> = {
  supervisor: "text-amber-300", analyst: "text-sky-300", architecture: "text-violet-300", review: "text-rose-300",
  testing: "text-emerald-300", synthesizer: "text-slate-300", system: "text-slate-500",
};
const AGENT_LABEL: Record<string, string> = {
  supervisor: "Supervisor", analyst: "Repository Analyst", architecture: "Architecture Agent", review: "Code Review Agent",
  testing: "Testing Agent", synthesizer: "Synthesizer", system: "System",
};

function Icon({ type }: { type: string }) {
  const c = "h-3.5 w-3.5 shrink-0";
  switch (type) {
    case "agent_started": return <Bot className={c} />;
    case "tool_call": return <Wrench className={c} />;
    case "tool_result": return <CornerDownRight className={c} />;
    case "agent_finished": return <CheckCircle2 className={c} />;
    case "plan": return <ListChecks className={c} />;
    case "error": return <AlertCircle className={`${c} text-sev-high`} />;
    case "run_started": return <Play className={c} />;
    default: return <Info className={c} />;
  }
}

/** Renders the actual events emitted by the backend run (nothing is hardcoded here). */
export function Timeline({ events, running }: { events: RunEvent[]; running?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [events.length]);
  if (!events.length) return <p className="p-4 text-sm text-slate-500">{running ? "Waiting for the first backend event…" : "No activity yet. Start a run to see agents work."}</p>;
  return (
    <ol className="space-y-1 p-3 text-xs">
      {events.filter((e) => e.type !== "task").map((e) => (
        <li key={e.seq} className={`flex gap-2 rounded px-2 py-1.5 ${e.type === "agent_started" ? "mt-2 bg-ink-800" : ""}`}>
          <span className={`mt-0.5 ${AGENT_COLOR[e.agent] ?? "text-slate-300"}`}><Icon type={e.type} /></span>
          <div className="min-w-0 flex-1">
            {e.type === "agent_started" ? (
              <div><span className={`font-semibold ${AGENT_COLOR[e.agent]}`}>{AGENT_LABEL[e.agent] ?? e.agent}</span><span className="text-slate-400"> · {e.data.task}</span></div>
            ) : e.type === "tool_call" ? (
              <div><span className="font-mono text-slate-200">{e.data.tool}</span>
                <span className="ml-1 break-all font-mono text-slate-500">({JSON.stringify(e.data.args).slice(0, 140)})</span></div>
            ) : e.type === "tool_result" ? (
              <div className="break-all font-mono text-slate-500">→ {String(e.data.summary).slice(0, 200)}</div>
            ) : <div className={e.type === "error" ? "text-sev-high" : "text-slate-300"}>{e.message}</div>}
          </div>
          <span className="shrink-0 font-mono text-[10px] text-slate-600">{e.t.toFixed(2)}s</span>
        </li>
      ))}
      {running && <li className="px-2 py-1 text-slate-500">working…</li>}
      <div ref={end} />
    </ol>
  );
}
