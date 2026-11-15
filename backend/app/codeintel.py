"""Static code intelligence: Python AST analysis, JS/TS imports, dependency graph, cycles."""
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

from .scanner import read_text

JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[\w*{}\s,$]+\s+from\s+)?|export\s+[\w*{}\s,$]+\s+from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]""")


def py_module_name(path: str) -> str:
    p = PurePosixPath(path)
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or "__init__"


def _complexity(node: ast.AST) -> int:
    score = 1
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                          ast.IfExp, ast.comprehension, ast.With, ast.Assert)):
            score += 1
        elif isinstance(n, ast.BoolOp):
            score += len(n.values) - 1
    return score


def analyze_python_file(path: str, source: str) -> dict:
    """Return functions, classes and imports found via ast. Raises SyntaxError on bad code."""
    tree = ast.parse(source)
    functions, classes, imports = [], [], []

    def add_func(node, qual, cls=None):
        functions.append({
            "name": node.name, "qualname": qual, "class": cls, "line": node.lineno,
            "end_line": node.end_lineno or node.lineno, "args": [a.arg for a in node.args.args],
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "has_docstring": ast.get_docstring(node) is not None, "complexity": _complexity(node),
        })

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_func(node, node.name)
        elif isinstance(node, ast.ClassDef):
            methods = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_func(sub, f"{node.name}.{sub.name}", node.name)
                    methods.append(sub.name)
            classes.append({"name": node.name, "line": node.lineno,
                            "end_line": node.end_lineno or node.lineno,
                            "bases": [ast.unparse(b) for b in node.bases], "methods": methods,
                            "has_docstring": ast.get_docstring(node) is not None})
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append({"module": a.name, "names": [], "level": 0, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            imports.append({"module": node.module or "", "names": [a.name for a in node.names],
                            "level": node.level, "line": node.lineno})
    return {"functions": functions, "classes": classes, "imports": imports}


class _Resolver:
    def __init__(self, modules: dict[str, dict]):
        self.modules = modules
        self.names = set(modules)
        self.stdlib = set(getattr(sys, "stdlib_module_names", ()))

    def lookup(self, cand: str, allow_suffix: bool) -> str | None:
        if cand in self.names:
            return cand
        if allow_suffix:
            hits = [m for m in self.names if m.endswith("." + cand)]
            if len(hits) == 1:
                return hits[0]
        return None

    def resolve(self, current: str, is_pkg: bool, imp: dict) -> set[str]:
        out: set[str] = set()
        level, module, names = imp["level"], imp["module"], imp["names"]
        if level > 0:
            pkg = current.split(".") if is_pkg else current.split(".")[:-1]
            if level > 1:
                pkg = pkg[: len(pkg) - (level - 1)]
            base = pkg + (module.split(".") if module else [])
            for n in names or [None]:
                cand = ".".join(base + ([n] if n else []))
                hit = self.lookup(cand, False) or self.lookup(".".join(base), False)
                if hit:
                    out.add(hit)
        else:
            top = module.split(".")[0] if module else ""
            allow_suffix = top not in self.stdlib
            if names:  # from a.b import c
                for n in names:
                    hit = self.lookup(f"{module}.{n}", allow_suffix) or self.lookup(module, allow_suffix)
                    if hit:
                        out.add(hit)
            else:  # import a.b.c
                parts = module.split(".")
                for i in range(len(parts), 0, -1):
                    hit = self.lookup(".".join(parts[:i]), allow_suffix)
                    if hit:
                        out.add(hit)
                        break
        out.discard(current)
        return out


def _js_resolve(src_path: str, spec: str, all_paths: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    base = PurePosixPath(src_path).parent
    target = PurePosixPath(*[p for p in (base / spec).parts])
    norm: list[str] = []
    for part in target.parts:
        if part == "..":
            if norm:
                norm.pop()
        elif part != ".":
            norm.append(part)
    cand = "/".join(norm)
    options = [cand] + [cand + e for e in JS_EXTS] + [f"{cand}/index{e}" for e in JS_EXTS]
    return next((o for o in options if o in all_paths), None)


def find_cycles(nodes: list[str], edges: list[tuple[str, str]]) -> list[dict]:
    """Tarjan SCC; each SCC with >1 node (or a self loop) is a circular dependency."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))
    adj: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    sccs: list[list[str]] = []
    counter = [0]

    def strong(v: str):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for n in nodes:
        if n not in index:
            strong(n)

    cycles = []
    for comp in sccs:
        if len(comp) < 2:
            continue
        members = set(comp)
        start = sorted(comp)[0]
        path = _cycle_path(start, adj, members)
        cycles.append({"modules": sorted(comp), "path": path})
    return sorted(cycles, key=lambda c: -len(c["modules"]))


def _cycle_path(start: str, adj: dict, members: set[str]) -> list[str]:
    seen = {start}
    stack = [(start, [start])]
    while stack:
        node, path = stack.pop()
        for nxt in sorted(adj[node], reverse=True):
            if nxt == start and len(path) > 1:
                return path + [start]
            if nxt in members and nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, path + [nxt]))
    return sorted(members) + [start]


def analyze_repository(root: Path, files: list[dict]) -> dict:
    """Build per-module facts and an internal dependency graph for Python and JS/TS."""
    modules: dict[str, dict] = {}
    parse_errors: list[dict] = []
    py_files = [f for f in files if f["language"] == "Python"]
    js_files = [f for f in files if f["path"].lower().endswith(JS_EXTS)]

    for f in py_files:
        name = py_module_name(f["path"])
        if name in modules:  # duplicate dotted names (e.g. two scripts) -> keep path to disambiguate
            name = f["path"]
        try:
            facts = analyze_python_file(f["path"], read_text(root / f["path"]))
        except SyntaxError as exc:
            parse_errors.append({"path": f["path"], "line": exc.lineno or 1, "message": str(exc.msg)})
            facts = {"functions": [], "classes": [], "imports": []}
        modules[name] = {"id": name, "path": f["path"], "language": "Python", "lines": f["lines"],
                         "is_package": f["path"].endswith("__init__.py"), **facts}

    resolver = _Resolver(modules)
    edges: dict[tuple[str, str], list[int]] = defaultdict(list)
    external: dict[str, set[str]] = defaultdict(set)
    stdlib = resolver.stdlib
    for name, m in modules.items():
        for imp in m["imports"]:
            targets = resolver.resolve(name, m["is_package"], imp)
            for t in targets:
                edges[(name, t)].append(imp["line"])
            top = imp["module"].split(".")[0]
            if not targets and imp["level"] == 0 and top and top not in stdlib:
                external[name].add(top)

    all_paths = {f["path"] for f in files}
    for f in js_files:
        text = read_text(root / f["path"])
        imports = []
        for m_ in _JS_IMPORT.finditer(text):
            line = text.count("\n", 0, m_.start()) + 1
            spec = m_.group(1)
            imports.append({"module": spec, "names": [], "level": 0, "line": line})
            target = _js_resolve(f["path"], spec, all_paths)
            if target:
                edges[(f["path"], target)].append(line)
            elif not spec.startswith("."):
                external[f["path"]].add(spec.split("/")[0] if not spec.startswith("@") else "/".join(spec.split("/")[:2]))
        funcs = [{"name": m2.group(1) or m2.group(2), "line": text.count("\n", 0, m2.start()) + 1}
                 for m2 in re.finditer(r"function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(", text)]
        modules[f["path"]] = {"id": f["path"], "path": f["path"], "language": f["language"],
                              "lines": f["lines"], "is_package": False, "functions": [
                                  {"name": x["name"], "qualname": x["name"], "line": x["line"], "end_line": x["line"],
                                   "class": None, "args": [], "is_async": False, "has_docstring": False, "complexity": 0}
                                  for x in funcs if x["name"]],
                              "classes": [], "imports": imports}

    edge_list = [{"source": a, "target": b, "lines": sorted(set(ls))} for (a, b), ls in edges.items()]
    fan_in, fan_out = defaultdict(int), defaultdict(int)
    for e in edge_list:
        fan_out[e["source"]] += 1
        fan_in[e["target"]] += 1

    nodes = []
    for name, m in modules.items():
        nodes.append({"id": name, "path": m["path"], "language": m["language"], "lines": m["lines"],
                      "functions": len(m["functions"]), "classes": len(m["classes"]),
                      "fan_in": fan_in[name], "fan_out": fan_out[name],
                      "external_imports": sorted(external.get(name, []))})
    cycles = find_cycles([n["id"] for n in nodes], [(e["source"], e["target"]) for e in edge_list])
    return {"modules": modules, "nodes": sorted(nodes, key=lambda n: n["id"]), "edges": edge_list,
            "cycles": cycles, "parse_errors": parse_errors}


def summarize_architecture(analysis: dict) -> dict:
    """Deterministic, fact-only architecture summary (no AI involved)."""
    nodes, edges, cycles = analysis["nodes"], analysis["edges"], analysis["cycles"]
    hubs = sorted(nodes, key=lambda n: -n["fan_in"])[:5]
    hubs = [h for h in hubs if h["fan_in"] > 0]
    coupled = [n for n in sorted(nodes, key=lambda n: -n["fan_out"])[:5] if n["fan_out"] > 0]
    isolated = [n["id"] for n in nodes if n["fan_in"] == 0 and n["fan_out"] == 0]
    entry = [n["id"] for n in nodes if n["fan_in"] == 0 and n["fan_out"] > 0]
    ext = defaultdict(int)
    for n in nodes:
        for e in n["external_imports"]:
            ext[e] += 1
    lines = [f"{len(nodes)} modules with {len(edges)} internal import relationships."]
    if hubs:
        lines.append("Most depended-on modules: " + ", ".join(f"{h['id']} ({h['fan_in']} dependents)" for h in hubs) + ".")
    if entry:
        lines.append("Likely entry points (nothing imports them): " + ", ".join(entry[:6]) + ".")
    lines.append(f"{len(cycles)} circular dependency group(s) detected." if cycles else "No circular dependencies detected.")
    return {"facts": lines, "hubs": hubs, "most_coupled": coupled, "isolated": isolated,
            "entry_points": entry, "top_external": sorted(ext.items(), key=lambda kv: -kv[1])[:10]}
