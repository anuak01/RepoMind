import axios from "axios";

export const api = axios.create({ baseURL: "/api" });

export function errMsg(e: unknown): string {
  if (axios.isAxiosError(e)) return (e.response?.data as { detail?: string })?.detail ?? e.message;
  return e instanceof Error ? e.message : String(e);
}

export interface Meta {
  id: string; name: string; status: "processing" | "ready" | "error"; stage: string; progress: number; error?: string | null;
  counts?: { files: number; lines: number; modules: number; findings: number };
  extraction?: Record<string, number>; index?: { chunks: number; embedding_backend: string; truncated: boolean };
}
export interface Health { status: string; openrouter_configured: boolean; model: string; embeddings: string }
export interface LangStat { language: string; files: number; lines: number; percent: number | null; is_code: boolean }
export interface Overview {
  meta: Meta; languages: LangStat[]; frameworks: string[]; total_files: number; total_lines: number;
  manifests: { file: string; type: string; dependencies: { name: string; version: string; dev: boolean }[] }[];
  parse_errors: { path: string; line: number; message: string }[];
}
export interface TreeNode { name: string; type: "dir" | "file"; path?: string; language?: string; lines?: number; children?: TreeNode[] }
export interface FileData { path: string; language: string; content: string; lines: number }
export interface ArchNode { id: string; path: string; language: string; lines: number; functions: number; classes: number; fan_in: number; fan_out: number; external_imports: string[] }
export interface Arch {
  nodes: ArchNode[]; edges: { source: string; target: string; lines: number[] }[];
  cycles: { modules: string[]; path: string[] }[];
  facts: { facts: string[]; hubs: ArchNode[]; entry_points: string[]; isolated: string[]; top_external: [string, number][] };
  ai_summary: { summary: string; risks: string[]; recommendations: string[] } | null; ai_enabled: boolean;
}
export interface Finding {
  id: string; origin: "verified" | "ai_suggestion"; severity: "high" | "medium" | "low"; category: string; path: string; line: number;
  title: string; explanation: string; suggestion: string; snippet: string; rule: string;
}
export interface Review { verified: Finding[]; ai_suggestions: Finding[]; ai_enabled: boolean }
export interface Testing {
  tests: { path: string; language: string; case_count: number; cases: { name: string; line: number }[] }[];
  total_cases: number; frameworks: string[]; note: string; executed: boolean; ai_enabled: boolean;
  untested_modules: { module: string; path: string; functions: number; classes: number; lines: number }[];
  plan: { summary: string; priorities: string[]; sample_tests: { target: string; framework: string; description: string; code: string }[] } | null;
}
export interface RunEvent { seq: number; t: number; agent: string; type: string; message: string; data: Record<string, any> }
export interface Citation { path: string; start: number; end: number; language: string; snippet: string }
export interface RunResult {
  intent: string; agents: string[]; answer: string; citations: Citation[]; unverified_citations: string[]; ai_enabled: boolean;
  errors: string[]; report_markdown?: string;
}
export interface RunSummary { id: string; mode: string; message: string; status: string; started_at: string; event_count: number }
export type OpenFn = (path: string, start?: number, end?: number) => void;
