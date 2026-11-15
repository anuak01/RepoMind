"""Discovers existing tests and flags potentially untested modules (heuristic, nothing is run)."""
import ast
import re
from pathlib import Path

from .scanner import read_text

_TEST_NAME = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|[^/]*\.(test|spec)\.[jt]sx?|[^/]*_test\.go)$")


def is_test_path(path: str) -> bool:
    p = path.lower()
    return bool(_TEST_NAME.search(p)) or "/__tests__/" in "/" + p or p.startswith("tests/") or "/tests/" in p


def discover_tests(root: Path, files: list[dict], graph: dict) -> dict:
    tests = []
    frameworks = set()
    for f in files:
        if not is_test_path(f["path"]) or f["language"] not in ("Python", "JavaScript", "TypeScript", "Go"):
            continue
        text = read_text(root / f["path"])
        cases = []
        if f["language"] == "Python":
            try:
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                        cases.append({"name": node.name, "line": node.lineno})
            except SyntaxError:
                pass
            if "pytest" in text:
                frameworks.add("pytest")
            if "unittest" in text:
                frameworks.add("unittest")
        else:
            for m in re.finditer(r"\b(?:it|test)\s*\(\s*['\"`]([^'\"`]+)", text):
                cases.append({"name": m.group(1), "line": text.count("\n", 0, m.start()) + 1})
            for fw in ("vitest", "jest", "mocha"):
                if fw in text:
                    frameworks.add(fw)
        tests.append({"path": f["path"], "language": f["language"], "cases": cases, "case_count": len(cases)})

    test_paths = {t["path"] for t in tests}
    tested_by: dict[str, set[str]] = {}
    for e in graph["edges"]:
        if e["source"] in test_paths or graph["modules"].get(e["source"], {}).get("path") in test_paths:
            tested_by.setdefault(e["target"], set()).add(graph["modules"].get(e["source"], {}).get("path", e["source"]))

    untested = []
    for node in graph["nodes"]:
        path = node["path"]
        if path in test_paths or is_test_path(path) or Path(path).name in ("__init__.py", "conftest.py", "setup.py"):
            continue
        if node["functions"] == 0 and node["classes"] == 0:
            continue
        stem = Path(path).stem
        by_name = any(stem in Path(t).stem for t in test_paths)
        if node["id"] not in tested_by and not by_name:
            untested.append({"module": node["id"], "path": path, "functions": node["functions"],
                             "classes": node["classes"], "lines": node["lines"]})
    untested.sort(key=lambda u: -(u["functions"] + u["classes"]))
    return {"tests": tests, "total_cases": sum(t["case_count"] for t in tests), "frameworks": sorted(frameworks),
            "untested_modules": untested,
            "note": "Untested modules are a heuristic (no test imports the module and no test file shares its name). "
                    "No tests were executed."}
