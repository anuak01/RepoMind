import { ChevronDown, ChevronRight, FileCode2, Folder } from "lucide-react";
import { useState } from "react";
import { TreeNode } from "../api";

function Node({ node, depth, selected, onSelect, defaultOpen }: { node: TreeNode; depth: number; selected?: string; onSelect: (p: string) => void; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const pad = { paddingLeft: 8 + depth * 14 };
  if (node.type === "file") {
    const active = selected === node.path;
    return (
      <button style={pad} onClick={() => onSelect(node.path!)} className={`flex w-full items-center gap-1.5 rounded py-1 pr-2 text-left text-[13px] ${active ? "bg-accent-dim/25 text-white" : "text-slate-300 hover:bg-ink-800"}`}>
        <FileCode2 className="h-3.5 w-3.5 shrink-0 text-slate-500" /><span className="truncate">{node.name}</span>
        <span className="ml-auto text-[10px] text-slate-600">{node.lines}</span>
      </button>
    );
  }
  return (
    <div>
      <button style={pad} onClick={() => setOpen(!open)} className="flex w-full items-center gap-1 rounded py-1 pr-2 text-left text-[13px] text-slate-200 hover:bg-ink-800">
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}<Folder className="h-3.5 w-3.5 text-accent" /><span className="truncate">{node.name}</span>
      </button>
      {open && node.children?.map((c) => <Node key={c.name + c.type} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} defaultOpen={depth < 1} />)}
    </div>
  );
}

export function FileTree({ root, selected, onSelect }: { root: TreeNode; selected?: string; onSelect: (p: string) => void }) {
  return <div className="py-1">{root.children?.map((c) => <Node key={c.name + c.type} node={c} depth={0} selected={selected} onSelect={onSelect} defaultOpen={true} />)}</div>;
}
