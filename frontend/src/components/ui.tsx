import { AlertTriangle, Loader2 } from "lucide-react";
import { ReactNode } from "react";

export const Spinner = ({ label }: { label?: string }) => (
  <div className="flex items-center gap-2 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />{label ?? "Loading…"}</div>
);

export const ErrorBox = ({ message }: { message: string }) => (
  <div role="alert" className="flex items-start gap-2 rounded-md border border-sev-high/40 bg-sev-high/10 p-3 text-sm text-sev-high">
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span>{message}</span>
  </div>
);

export const Empty = ({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) => (
  <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-ink-700 p-10 text-center">
    <p className="font-medium text-slate-200">{title}</p>
    {hint && <p className="max-w-md text-sm text-slate-400">{hint}</p>}
    {action}
  </div>
);

export const PageHeader = ({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) => (
  <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
    <div><h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>{sub && <p className="mt-1 max-w-2xl text-sm text-slate-400">{sub}</p>}</div>
    {right}
  </div>
);

const SEV: Record<string, string> = { high: "text-sev-high border-sev-high/40 bg-sev-high/10", medium: "text-sev-medium border-sev-medium/40 bg-sev-medium/10", low: "text-sev-low border-sev-low/40 bg-sev-low/10" };
export const Severity = ({ level }: { level: string }) => <span className={`rounded border px-1.5 py-0.5 text-xs font-medium ${SEV[level]}`}>{level}</span>;

export const Tag = ({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "accent" }) => {
  const c = { neutral: "border-ink-600 text-slate-300", good: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300", warn: "border-amber-500/40 bg-amber-500/10 text-amber-300", accent: "border-accent-dim/60 bg-accent-dim/15 text-accent" }[tone];
  return <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs ${c}`}>{children}</span>;
};

export const Stat = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="panel p-4"><div className="text-2xl font-semibold text-white">{value}</div><div className="mt-1 text-xs text-slate-400">{label}</div></div>
);
