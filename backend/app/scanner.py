"""Walks an extracted repository: files, languages, frameworks, dependency manifests."""
import json
import os
import re
from collections import Counter
from pathlib import Path

from .config import settings
from .security import is_binary_name, is_ignored_dir, is_secret_file

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".c": "C", ".h": "C",
    ".cpp": "C++", ".hpp": "C++", ".cs": "C#", ".kt": "Kotlin", ".swift": "Swift",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".json": "JSON", ".md": "Markdown",
    ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML", ".sh": "Shell", ".sql": "SQL",
    ".xml": "XML", ".txt": "Text", ".ini": "INI", ".cfg": "INI",
}
# Languages that count as "source code" for percentages
CODE_LANGS = {"Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "Ruby", "PHP", "C",
              "C++", "C#", "Kotlin", "Swift", "Shell", "SQL"}

FRAMEWORKS = {
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "starlette": "Starlette",
    "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic", "pytest": "pytest", "celery": "Celery",
    "langgraph": "LangGraph", "langchain": "LangChain", "numpy": "NumPy", "pandas": "pandas",
    "torch": "PyTorch", "tensorflow": "TensorFlow", "requests": "Requests",
    "react": "React", "vue": "Vue", "svelte": "Svelte", "next": "Next.js", "express": "Express",
    "vite": "Vite", "tailwindcss": "Tailwind CSS", "jest": "Jest", "vitest": "Vitest",
    "typescript": "TypeScript", "angular": "Angular", "@angular/core": "Angular",
    "spring-boot": "Spring Boot", "gin-gonic/gin": "Gin",
}


def language_for(rel_path: str) -> str:
    name = Path(rel_path).name
    if name == "Dockerfile":
        return "Dockerfile"
    return LANGUAGES.get(Path(rel_path).suffix.lower(), "Other")


def read_text(path: Path, limit: int | None = None) -> str:
    data = path.read_bytes()
    if limit:
        data = data[:limit]
    return data.decode("utf-8", errors="replace")


def scan_files(root: Path) -> list[dict]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_dir(d))
        for fn in sorted(filenames):
            full = Path(dirpath) / fn
            rel = full.relative_to(root).as_posix()
            if is_secret_file(rel) or is_binary_name(rel) or full.is_symlink():
                continue
            size = full.stat().st_size
            if size > settings.max_file_bytes:
                continue
            try:
                text = read_text(full)
            except OSError:
                continue
            if "\x00" in text:
                continue
            files.append({"path": rel, "language": language_for(rel), "size": size,
                          "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0)})
    return files


def language_stats(files: list[dict]) -> list[dict]:
    lines, counts = Counter(), Counter()
    for f in files:
        lines[f["language"]] += f["lines"]
        counts[f["language"]] += 1
    code_total = sum(v for k, v in lines.items() if k in CODE_LANGS) or 1
    stats = [{"language": k, "files": counts[k], "lines": lines[k],
              "percent": round(100 * lines[k] / code_total, 1) if k in CODE_LANGS else None,
              "is_code": k in CODE_LANGS} for k in lines]
    return sorted(stats, key=lambda s: (not s["is_code"], -s["lines"]))


def build_tree(files: list[dict]) -> dict:
    root: dict = {"name": "", "type": "dir", "children": {}}
    for f in files:
        node = root
        parts = f["path"].split("/")
        for p in parts[:-1]:
            node = node["children"].setdefault(p, {"name": p, "type": "dir", "children": {}})
        node["children"][parts[-1]] = {"name": parts[-1], "type": "file", "path": f["path"],
                                       "language": f["language"], "lines": f["lines"]}

    def finish(n: dict) -> dict:
        if n["type"] == "file":
            return n
        kids = [finish(c) for c in n["children"].values()]
        kids.sort(key=lambda c: (c["type"] != "dir", c["name"].lower()))
        return {"name": n["name"], "type": "dir", "children": kids}

    return finish(root)


# ---------- dependency manifests ----------
def _req_name(line: str) -> tuple[str, str] | None:
    line = line.split("#")[0].strip()
    if not line or line.startswith(("-", "git+", "http")):
        return None
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(\[.*?\])?\s*(.*)$", line)
    return (m.group(1), m.group(3).strip()) if m else None


def parse_dependencies(root: Path, files: list[dict]) -> list[dict]:
    manifests = []
    for f in files:
        name = Path(f["path"]).name
        full = root / f["path"]
        deps: list[dict] = []
        kind = None
        try:
            if re.match(r"^requirements.*\.txt$", name):
                kind = "pip"
                for line in read_text(full).splitlines():
                    r = _req_name(line)
                    if r:
                        deps.append({"name": r[0], "version": r[1] or "*", "dev": "dev" in name or "test" in name})
            elif name == "package.json":
                kind = "npm"
                data = json.loads(read_text(full))
                for key, dev in (("dependencies", False), ("devDependencies", True)):
                    for k, v in (data.get(key) or {}).items():
                        deps.append({"name": k, "version": str(v), "dev": dev})
            elif name == "pyproject.toml" and tomllib:
                kind = "pyproject"
                data = tomllib.loads(read_text(full))
                for spec in (data.get("project", {}).get("dependencies") or []):
                    r = _req_name(spec)
                    if r:
                        deps.append({"name": r[0], "version": r[1] or "*", "dev": False})
                for k, v in (data.get("tool", {}).get("poetry", {}).get("dependencies") or {}).items():
                    if k.lower() != "python":
                        deps.append({"name": k, "version": str(v), "dev": False})
            elif name == "go.mod":
                kind = "go"
                for m in re.finditer(r"^\s*([\w.\-/]+\.[\w.\-/]+)\s+(v[\w.\-+]+)", read_text(full), re.M):
                    deps.append({"name": m.group(1), "version": m.group(2), "dev": False})
            elif name == "Cargo.toml" and tomllib:
                kind = "cargo"
                data = tomllib.loads(read_text(full))
                for k, v in (data.get("dependencies") or {}).items():
                    deps.append({"name": k, "version": v if isinstance(v, str) else str(v.get("version", "*")), "dev": False})
            elif name == "pom.xml":
                kind = "maven"
                for m in re.finditer(r"<artifactId>([^<]+)</artifactId>", read_text(full)):
                    deps.append({"name": m.group(1), "version": "*", "dev": False})
        except (ValueError, OSError):
            continue
        if kind:
            manifests.append({"file": f["path"], "type": kind, "dependencies": deps})
    return manifests


def detect_frameworks(manifests: list[dict]) -> list[str]:
    found = set()
    for m in manifests:
        for d in m["dependencies"]:
            key = d["name"].lower()
            for needle, label in FRAMEWORKS.items():
                if key == needle or (("/" in needle or needle == "spring-boot") and needle in key):
                    found.add(label)
    return sorted(found)
