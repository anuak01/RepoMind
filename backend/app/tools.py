"""Repository tools shared by all agents. Every call is instrumented: it emits real tool_call /
tool_result events and records the source ranges it returned as evidence for citations."""
import functools
import json
import re
from pathlib import Path
from typing import Callable

from . import rag, store
from .scanner import language_for, read_text
from .security import resolve_in_root

CITE_RE = re.compile(r"\[([\w./\\@\- ]+?):(\d+)(?:\s*-\s*(\d+))?\]")


def _short(obj, n=280) -> str:
    s = json.dumps(obj, default=str) if not isinstance(obj, str) else obj
    return s if len(s) <= n else s[:n] + "…"


class ToolBox:
    def __init__(self, repo_id: str, emit: Callable[..., None] | None = None):
        self.repo_id = repo_id
        self.root = store.repo_root(repo_id)
        self.analysis = store.get_analysis(repo_id) or {}
        self.emit = emit or (lambda *a, **k: None)
        self.agent = "system"
        self.evidence: list[dict] = []
        self._files = {f["path"]: f for f in self.analysis.get("files", [])}

    # ---------- instrumentation ----------
    def instrument(self, fn: Callable) -> Callable:
        tb = self

        @functools.wraps(fn)
        def inner(*args, **kwargs):
            tb.emit(tb.agent, "tool_call", f"{fn.__name__}", {"tool": fn.__name__, "args": kwargs or list(args)})
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                result = {"error": f"{type(exc).__name__}: {exc}"}
            tb.emit(tb.agent, "tool_result", f"{fn.__name__} returned", {"tool": fn.__name__, "summary": _short(result)})
            return result
        return inner

    def agent_tools(self, names: list[str]) -> list[Callable]:
        return [self.instrument(getattr(self, n)) for n in names]

    def call(self, name: str, **kwargs):
        """Run a tool deterministically (still instrumented) without the LLM."""
        return self.instrument(getattr(self, name))(**kwargs)

    def _add_evidence(self, path: str, start: int, end: int, source: str) -> None:
        self.evidence.append({"path": path, "start": start, "end": end, "source": source})

    # ---------- tools exposed to agents ----------
    def list_files(self, directory: str = "", max_items: int = 200) -> dict:
        """List source files in the repository, optionally under a directory prefix (e.g. 'app/')."""
        prefix = directory.strip("/")
        items = [f for p, f in self._files.items() if not prefix or p.startswith(prefix + "/") or p == prefix]
        return {"count": len(items), "files": [{"path": f["path"], "language": f["language"], "lines": f["lines"]}
                                               for f in items[:max_items]]}

    def read_file(self, path: str, start_line: int = 1, end_line: int = 200) -> dict:
        """Read lines start_line..end_line (1-based, max 250 lines) of a repository file. Returns numbered source."""
        target = resolve_in_root(self.root, path)
        if not target.is_file() or path.replace("\\", "/").lstrip("/") not in self._files:
            return {"error": f"File not found in repository: {path}"}
        rel = path.replace("\\", "/").lstrip("/")
        lines = read_text(target).splitlines()
        start = max(1, int(start_line))
        end = min(len(lines), int(end_line), start + 249)
        if start > len(lines):
            return {"error": f"File has only {len(lines)} lines"}
        self._add_evidence(rel, start, end, "read_file")
        return {"path": rel, "start_line": start, "end_line": end, "total_lines": len(lines),
                "content": "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))}

    def search_code(self, query: str, top_k: int = 6) -> dict:
        """Semantic search over the indexed repository. Returns code chunks with file path and line range."""
        hits = rag.search(self.repo_id, query, min(int(top_k), 10))
        for h in hits:
            self._add_evidence(h["path"], h["start"], h["end"], "search_code")
        return {"query": query, "results": [{"path": h["path"], "start_line": h["start"], "end_line": h["end"],
                                             "kind": h["kind"], "name": h["name"], "score": h["score"],
                                             "code": h["text"][:1800]} for h in hits]}

    def get_architecture(self) -> dict:
        """Module dependency graph summary: hub modules, entry points, internal edges, external packages."""
        g, facts = self.analysis["graph"], self.analysis["architecture_facts"]
        return {"facts": facts["facts"], "hubs": [h["id"] for h in facts["hubs"]], "entry_points": facts["entry_points"][:10],
                "top_external_packages": facts["top_external"], "modules": len(g["nodes"]), "edges": len(g["edges"]),
                "sample_edges": [f"{e['source']} -> {e['target']}" for e in g["edges"][:40]],
                "languages": self.analysis["languages"][:6], "frameworks": self.analysis["frameworks"]}

    def find_circular_dependencies(self) -> dict:
        """Return circular import groups with a concrete cycle path for each."""
        return {"cycles": self.analysis["graph"]["cycles"]}

    def get_static_findings(self, path: str = "", max_items: int = 40) -> dict:
        """Verified static-analysis findings (rule-based, with file and line). Optionally filter by path prefix."""
        items = [f for f in self.analysis.get("static_findings", []) if not path or f["path"].startswith(path)]
        for f in items[:max_items]:
            self._add_evidence(f["path"], max(1, f["line"] - 2), f["line"] + 2, "get_static_findings")
        return {"count": len(items), "findings": [{k: f[k] for k in ("severity", "rule", "path", "line", "title", "snippet")}
                                                  for f in items[:max_items]]}

    def get_symbols(self, path: str) -> dict:
        """Functions, classes and imports of one file (AST-derived for Python)."""
        mod = next((m for m in self.analysis["graph"]["modules"].values() if m["path"] == path), None)
        if not mod:
            return {"error": f"No analyzed module at {path}"}
        return {"path": path, "functions": [{"name": f["qualname"], "line": f["line"], "end_line": f["end_line"]} for f in mod["functions"]],
                "classes": [{"name": c["name"], "line": c["line"], "end_line": c["end_line"]} for c in mod["classes"]],
                "imports": [f"{'.' * i['level']}{i['module']}" for i in mod["imports"]][:40]}

    def discover_tests(self) -> dict:
        """Existing test files, case counts, frameworks, and modules that no test imports (heuristic)."""
        t = self.analysis["testing"]
        return {"test_files": [{"path": x["path"], "cases": x["case_count"]} for x in t["tests"]],
                "frameworks": t["frameworks"], "total_cases": t["total_cases"],
                "potentially_untested": [u["path"] for u in t["untested_modules"][:15]]}

    def get_dependencies(self) -> dict:
        """Third-party dependencies declared in manifests (requirements.txt, package.json, ...)."""
        return {"manifests": [{"file": m["file"], "type": m["type"], "count": len(m["dependencies"]),
                               "dependencies": [d["name"] for d in m["dependencies"][:40]]} for m in self.analysis["manifests"]]}

    # ---------- citation verification ----------
    def verify_citations(self, text: str) -> tuple[list[dict], list[str]]:
        """Only citations that overlap source ranges the agents actually retrieved are verified."""
        verified, unverified, seen = [], [], set()
        for m in CITE_RE.finditer(text or ""):
            path = m.group(1).replace("\\", "/").strip()
            start, end = int(m.group(2)), int(m.group(3) or m.group(2))
            key = (path, start, end)
            if key in seen:
                continue
            seen.add(key)
            ok = path in self._files and any(
                e["path"] == path and start <= e["end"] and end >= e["start"] for e in self.evidence)
            if ok:
                lines = read_text(self.root / path).splitlines()
                end = min(end, len(lines))
                verified.append({"path": path, "start": start, "end": end, "language": language_for(path),
                                 "snippet": "\n".join(lines[start - 1:min(end, start + 11)])})
            else:
                unverified.append(m.group(0))
        return verified, unverified
