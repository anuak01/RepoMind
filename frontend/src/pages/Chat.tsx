import { Send, ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Health, OpenFn, RunResult } from "../api";
import { Markdown } from "../components/Markdown";
import { Timeline } from "../components/Timeline";
import { ErrorBox, Tag } from "../components/ui";
import { useRun } from "../hooks/useRun";

interface Msg { role: "user" | "assistant"; text: string; result?: RunResult }
const SUGGESTIONS = ["What does this project do and how is it structured?", "Where is user input handled and is it validated?", "Are there circular dependencies?", "Which parts have security risks?"];

export default function Chat({ repoId, health, onOpen }: { repoId: string; health: Health | null; onOpen: OpenFn }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const run = useRun();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length, run.running]);
  useEffect(() => { setMsgs([]); }, [repoId]);

  async function send(text: string) {
    if (!text.trim() || run.running) return;
    setMsgs((m) => [...m, { role: "user", text }]); setInput("");
    const res = await run.start(repoId, "chat", text);
    setMsgs((m) => [...m, { role: "assistant", text: res?.answer ?? "The run did not return an answer.", result: res ?? undefined }]);
  }

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-auto p-5">
          <div className="mx-auto max-w-3xl space-y-5">
            {!msgs.length && (
              <div className="pt-10">
                <h1 className="text-xl font-semibold text-white">Ask the codebase</h1>
                <p className="mt-1 text-sm text-slate-400">Answers are built from code retrieved from your repository. Citations are checked against what the agents actually read.</p>
                {health && !health.openrouter_configured && <p className="mt-3 flex items-center gap-2 text-sm text-amber-300"><ShieldAlert className="h-4 w-4" />No OpenRouter key: you will get retrieved code locations only, not written answers.</p>}
                <div className="mt-5 grid gap-2 sm:grid-cols-2">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="panel p-3 text-left text-sm text-slate-300 hover:bg-ink-800">{s}</button>)}</div>
              </div>)}
            {msgs.map((m, i) => m.role === "user"
              ? <div key={i} className="ml-auto max-w-[85%] rounded-lg bg-accent-dim/25 px-4 py-2 text-sm text-white">{m.text}</div>
              : <div key={i} className="panel p-4">
                  <Markdown text={m.text} citations={m.result?.citations ?? []} onOpen={onOpen} />
                  {m.result && <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-ink-700 pt-3">
                    <Tag tone="accent">{m.result.intent}</Tag>{m.result.agents.map((a) => <Tag key={a}>{a}</Tag>)}
                    <Tag tone={m.result.citations.length ? "good" : "neutral"}>{m.result.citations.length} verified citation(s)</Tag>
                    {m.result.unverified_citations.length > 0 && <Tag tone="warn">{m.result.unverified_citations.length} unverified removed</Tag>}
                  </div>}
                  {m.result && m.result.citations.length > 0 && <div className="mt-3 space-y-2">{m.result.citations.slice(0, 4).map((c) => (
                    <button key={c.path + c.start} onClick={() => onOpen(c.path, c.start, c.end)} className="block w-full rounded border border-ink-700 bg-ink-950 p-2 text-left hover:border-accent-dim">
                      <div className="font-mono text-xs text-accent">{c.path}:{c.start}-{c.end}</div><pre className="mt-1 max-h-24 overflow-hidden font-mono text-[11px] leading-4 text-slate-400">{c.snippet}</pre></button>))}</div>}
                </div>)}
            {run.running && <div className="text-sm text-slate-400">Agents are working… see the activity panel.</div>}
            {run.error && <ErrorBox message={run.error} />}
            <div ref={end} />
          </div>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="border-t border-ink-700 bg-ink-900 p-3">
          <div className="mx-auto flex max-w-3xl gap-2">
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about this repository…" aria-label="Question" className="flex-1 rounded-md border border-ink-600 bg-ink-950 px-3 py-2 text-sm text-white placeholder:text-slate-500" />
            <button className="btn btn-primary" disabled={run.running || !input.trim()}><Send className="h-4 w-4" />Ask</button>
          </div>
        </form>
      </section>
      <aside className="h-56 shrink-0 overflow-auto border-t border-ink-700 bg-ink-900 lg:h-auto lg:w-[22rem] lg:border-l lg:border-t-0">
        <div className="sticky top-0 border-b border-ink-700 bg-ink-900 px-4 py-2 text-sm font-semibold text-white">Live agent activity</div>
        <Timeline events={run.events} running={run.running} />
      </aside>
    </div>
  );
}
