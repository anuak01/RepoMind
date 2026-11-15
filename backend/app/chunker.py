"""AST-aware chunking. Python is split at function/class boundaries; other files use overlapping line windows."""
import ast

WINDOW, OVERLAP, MAX_CHUNK_LINES = 60, 10, 120


def _window(lines: list[str], base: int, kind: str, name: str) -> list[dict]:
    out, i = [], 0
    while i < len(lines):
        part = lines[i:i + WINDOW]
        if "".join(part).strip():
            out.append({"start": base + i, "end": base + i + len(part) - 1, "kind": kind, "name": name,
                        "text": "\n".join(part)})
        if i + WINDOW >= len(lines):
            break
        i += WINDOW - OVERLAP
    return out


def _span(node) -> tuple[int, int]:
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return start, node.end_lineno or node.lineno


def chunk_file(path: str, source: str, language: str) -> list[dict]:
    lines = source.splitlines()
    if not lines:
        return []
    chunks: list[dict] = []
    if language == "Python":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None:
            covered = [False] * (len(lines) + 2)

            def add(start, end, kind, name):
                seg = lines[start - 1:end]
                if end - start + 1 > MAX_CHUNK_LINES:
                    chunks.extend(_window(seg, start, kind, name))
                else:
                    chunks.append({"start": start, "end": end, "kind": kind, "name": name, "text": "\n".join(seg)})
                for n in range(start, end + 1):
                    covered[n] = True

            for node in tree.body:
                s, e = _span(node)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(s, e, "function", node.name)
                elif isinstance(node, ast.ClassDef):
                    if e - s + 1 <= MAX_CHUNK_LINES:
                        add(s, e, "class", node.name)
                    else:
                        methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                        first = _span(methods[0])[0] if methods else e
                        add(s, max(s, first - 1), "class", node.name)
                        for m in methods:
                            ms, me = _span(m)
                            add(ms, me, "method", f"{node.name}.{m.name}")
                        for n in range(s, e + 1):
                            covered[n] = True
            # leftover module-level code (imports, constants, scripts)
            i = 1
            while i <= len(lines):
                if covered[i]:
                    i += 1
                    continue
                j = i
                while j <= len(lines) and not covered[j]:
                    j += 1
                seg = lines[i - 1:j - 1]
                if "".join(seg).strip():
                    chunks.extend(_window(seg, i, "module", path))
                i = j
            return sorted(chunks, key=lambda c: c["start"])
    chunks = _window(lines, 1, "block", path)
    return chunks
