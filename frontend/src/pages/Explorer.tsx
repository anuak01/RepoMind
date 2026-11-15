import { useEffect, useState } from "react";
import { api, errMsg, FileData, TreeNode } from "../api";
import { CodeViewer } from "../components/CodeViewer";
import { FileTree } from "../components/FileTree";
import { Empty, ErrorBox, Spinner } from "../components/ui";

export default function Explorer({ repoId, target, onSelect }: { repoId: string; target: { path: string; start?: number; end?: number } | null; onSelect: (p: string) => void }) {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [file, setFile] = useState<FileData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.get(`/repos/${repoId}/tree`).then((r) => setTree(r.data)).catch((e) => setError(errMsg(e))); }, [repoId]);
  useEffect(() => {
    if (!target) { setFile(null); return; }
    setLoading(true); setError(null);
    api.get(`/repos/${repoId}/file`, { params: { path: target.path } }).then((r) => setFile(r.data)).catch((e) => setError(errMsg(e))).finally(() => setLoading(false));
  }, [repoId, target?.path]);

  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <aside className="max-h-60 w-full shrink-0 overflow-auto border-b border-ink-700 bg-ink-900 md:max-h-none md:w-72 md:border-b-0 md:border-r">
        {tree ? <FileTree root={tree} selected={target?.path} onSelect={onSelect} /> : <div className="p-4"><Spinner /></div>}
      </aside>
      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        {file && <div className="flex items-center gap-3 border-b border-ink-700 bg-ink-900 px-4 py-2 text-sm"><span className="font-mono text-slate-200">{file.path}</span><span className="text-xs text-slate-500">{file.language} · {file.lines} lines</span>
          {target?.start && <span className="ml-auto text-xs text-accent">cited lines {target.start}{target.end && target.end !== target.start ? `–${target.end}` : ""}</span>}</div>}
        <div className="min-h-0 flex-1">
          {error ? <div className="p-4"><ErrorBox message={error} /></div> : loading ? <div className="p-4"><Spinner /></div>
            : file ? <CodeViewer content={file.content} language={file.language} highlight={target?.start ? { start: target.start, end: target.end ?? target.start } : undefined} />
            : <div className="p-8"><Empty title="Select a file" hint="Pick a file from the tree, or click a citation in chat, review or reports to jump to the cited lines." /></div>}
        </div>
      </section>
    </div>
  );
}
