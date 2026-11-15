import { Fragment, ReactNode } from "react";
import { Citation, OpenFn } from "../api";

const CITE = /\[([\w./\\@\- ]+?):(\d+)(?:\s*-\s*(\d+))?\]/g;

/** Minimal markdown renderer. Citations become chips: verified (retrieved by an agent) open the file;
 *  anything else is shown muted and marked unverified. */
export function Inline({ text, citations, onOpen }: { text: string; citations: Citation[]; onOpen: OpenFn }) {
  const parts: ReactNode[] = [];
  const re = new RegExp(`${CITE.source}|\\*\\*(.+?)\\*\\*|\`([^\`]+)\``, "g");
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1]) {
      const path = m[1].replace(/\\/g, "/"), s = +m[2], e = m[3] ? +m[3] : s;
      const ok = citations.some((c) => c.path === path && s <= c.end && e >= c.start);
      parts.push(ok
        ? <button key={i++} onClick={() => onOpen(path, s, e)} title="Open in code viewer" className="mx-0.5 rounded border border-accent-dim/60 bg-accent-dim/15 px-1.5 py-0.5 font-mono text-xs text-accent hover:bg-accent-dim/30">{path}:{s}{e !== s ? `-${e}` : ""}</button>
        : <span key={i++} title="Not verified: this range was not retrieved from the repository" className="mx-0.5 rounded border border-amber-500/40 px-1.5 py-0.5 font-mono text-xs text-amber-300 line-through decoration-amber-500/60">{m[0].slice(1, -1)}</span>);
    } else if (m[4]) parts.push(<strong key={i++} className="font-semibold text-white">{m[4]}</strong>);
    else if (m[5]) parts.push(<code key={i++} className="rounded bg-ink-800 px-1 py-0.5 font-mono text-[0.85em] text-slate-100">{m[5]}</code>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts.map((p, k) => <Fragment key={k}>{p}</Fragment>)}</>;
}

export function Markdown({ text, citations = [], onOpen }: { text: string; citations?: Citation[]; onOpen: OpenFn }) {
  const out: ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0, k = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const buf: string[] = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      out.push(<pre key={k++} className="my-2 overflow-x-auto rounded-md border border-ink-700 bg-ink-950 p-3 font-mono text-xs leading-5 text-slate-200">{buf.join("\n")}</pre>);
    } else if (/^#{1,4} /.test(line)) {
      const lvl = line.match(/^#+/)![0].length;
      const cls = lvl === 1 ? "mt-4 text-lg font-semibold text-white" : lvl === 2 ? "mt-5 border-b border-ink-700 pb-1 text-base font-semibold text-white" : "mt-3 text-sm font-semibold text-slate-100";
      out.push(<div key={k++} className={cls}><Inline text={line.replace(/^#+ /, "")} citations={citations} onOpen={onOpen} /></div>); i++;
    } else if (/^\s*[-*] /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*] /.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*] /, ""));
      out.push(<ul key={k++} className="my-2 list-disc space-y-1 pl-5 text-sm leading-6">{items.map((it, j) => <li key={j}><Inline text={it} citations={citations} onOpen={onOpen} /></li>)}</ul>);
    } else if (!line.trim()) i++;
    else {
      out.push(<p key={k++} className="my-2 text-sm leading-6"><Inline text={line} citations={citations} onOpen={onOpen} /></p>); i++;
    }
  }
  return <div>{out}</div>;
}
