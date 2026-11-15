"""Deterministic static review. Every finding here is VERIFIED: a rule matched real code at a
real file and line. AI suggestions are produced separately and labelled as such."""
import ast
import re
from pathlib import Path

from .codeintel import _complexity
from .scanner import read_text

SECRET_RE = re.compile(
    r"""(?i)([A-Za-z0-9_]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token|private[_-]?key)[A-Za-z0-9_]*)\s*[:=]\s*['"]([^'"\s]{6,})['"]""")
PLACEHOLDER = re.compile(r"(?i)(example|your[_-]|changeme|placeholder|xxx|<.*>|\$\{|os\.environ|getenv|dummy|test)")
AWS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")
PRIVATE_KEY = re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")


def _is_test(path: str) -> bool:
    p = path.lower()
    return "/tests/" in "/" + p or "/test/" in "/" + p or Path(p).name.startswith("test_") or ".test." in p or ".spec." in p


def _f(rule, severity, category, path, line, title, explanation, suggestion, lines):
    snippet = lines[line - 1].strip()[:200] if 0 < line <= len(lines) else ""
    return {"id": f"{rule}:{path}:{line}", "origin": "verified", "rule": rule, "severity": severity,
            "category": category, "path": path, "line": line, "title": title,
            "explanation": explanation, "suggestion": suggestion, "snippet": snippet}


def _call_name(node: ast.Call) -> str:
    try:
        return ast.unparse(node.func)
    except Exception:  # pragma: no cover
        return ""


def _python_findings(path: str, source: str, lines: list[str]) -> list[dict]:
    out = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [_f("syntax-error", "high", "bug", path, exc.lineno or 1, "File has a syntax error",
                   f"Python cannot parse this file: {exc.msg}.", "Fix the syntax so the module can be imported.", lines)]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in ("eval", "exec"):
                out.append(_f("dangerous-eval", "high", "security", path, node.lineno, f"Use of {name}()",
                              f"{name}() executes arbitrary code; if any input is user-controlled this is code injection.",
                              "Use ast.literal_eval for data, or a dispatch table instead of executing strings.", lines))
            elif name.startswith("subprocess.") or name in ("os.system", "os.popen"):
                shell = any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords)
                if shell or name in ("os.system", "os.popen"):
                    out.append(_f("shell-injection", "high", "security", path, node.lineno, "Shell command execution",
                                  "Commands run through a shell are vulnerable to injection when they include untrusted input.",
                                  "Pass an argument list with shell=False and validate inputs.", lines))
            elif name in ("pickle.load", "pickle.loads", "marshal.loads"):
                out.append(_f("unsafe-deserialization", "high", "security", path, node.lineno, f"Unsafe deserialization ({name})",
                              "Deserializing untrusted pickle data can execute arbitrary code.",
                              "Use JSON or another data-only format for untrusted input.", lines))
            elif name == "yaml.load" and not any(k.arg == "Loader" for k in node.keywords):
                out.append(_f("yaml-load", "medium", "security", path, node.lineno, "yaml.load without a safe Loader",
                              "yaml.load can construct arbitrary Python objects.", "Use yaml.safe_load.", lines))
            elif name in ("hashlib.md5", "hashlib.sha1"):
                out.append(_f("weak-hash", "medium", "security", path, node.lineno, f"Weak hash {name}",
                              "MD5/SHA-1 are broken for security purposes (passwords, signatures).",
                              "Use hashlib.sha256 or a password KDF (bcrypt/argon2) for credentials.", lines))
            elif any(k.arg == "verify" and isinstance(k.value, ast.Constant) and k.value.value is False for k in node.keywords):
                out.append(_f("tls-verify-off", "high", "security", path, node.lineno, "TLS verification disabled",
                              "verify=False makes the connection vulnerable to man-in-the-middle attacks.",
                              "Remove verify=False or point it at a trusted CA bundle.", lines))
            elif name.endswith(".run") and any(k.arg == "debug" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                out.append(_f("debug-enabled", "medium", "security", path, node.lineno, "Debug mode enabled",
                              "Debug servers can expose an interactive console and stack traces.", "Disable debug outside local development.", lines))
            if name.endswith(".execute") and node.args:
                a = node.args[0]
                dynamic = isinstance(a, ast.JoinedStr) or (isinstance(a, ast.BinOp) and isinstance(a.op, (ast.Mod, ast.Add))) \
                    or (isinstance(a, ast.Call) and _call_name(a).endswith(".format"))
                if dynamic:
                    out.append(_f("sql-injection", "high", "security", path, node.lineno, "SQL built with string formatting",
                                  "Interpolating values into SQL text allows SQL injection.",
                                  "Use parameterized queries: cursor.execute('... WHERE id = ?', (value,)).", lines))
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                out.append(_f("bare-except", "medium", "quality", path, node.lineno, "Bare except clause",
                              "Catching everything hides real bugs and swallows KeyboardInterrupt/SystemExit.",
                              "Catch specific exceptions and log them.", lines))
            elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                out.append(_f("swallowed-exception", "low", "quality", path, node.lineno, "Exception silently ignored",
                              "An except block that only passes hides failures.", "Log the exception or handle it explicitly.", lines))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.args.defaults + [k for k in node.args.kw_defaults if k is not None]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    out.append(_f("mutable-default", "medium", "bug", path, node.lineno, f"Mutable default argument in {node.name}()",
                                  "Default values are created once and shared between calls, causing surprising state.",
                                  "Default to None and create the list/dict inside the function.", lines))
                    break
            length = (node.end_lineno or node.lineno) - node.lineno + 1

            cx = _complexity(node)
            if cx >= 15:
                out.append(_f("high-complexity", "low", "quality", path, node.lineno, f"{node.name}() has high complexity ({cx})",
                              f"Cyclomatic-style complexity of {cx} over {length} lines makes the function hard to test.",
                              "Split into smaller functions.", lines))
    return out


def _generic_findings(path: str, lines: list[str]) -> list[dict]:
    out = []
    is_js = path.lower().endswith((".js", ".jsx", ".ts", ".tsx"))
    for i, text in enumerate(lines, 1):
        m = SECRET_RE.search(text)
        if m and not PLACEHOLDER.search(m.group(2)) and not text.strip().startswith(("#", "//")):
            out.append(_f("hardcoded-secret", "high", "security", path, i, f"Possible hardcoded {m.group(1).lower()}",
                          "A credential-looking literal is assigned in source code and would be committed to version control.",
                          "Load it from an environment variable or secret manager and rotate the exposed value.", lines))
        if AWS_KEY.search(text) or PRIVATE_KEY.search(text):
            out.append(_f("hardcoded-secret", "high", "security", path, i, "Embedded key material",
                          "An access key or private key appears in the source.", "Remove it, rotate it, and load from a secret store.", lines))
        if is_js:
            if re.search(r"\beval\s*\(", text):
                out.append(_f("dangerous-eval", "high", "security", path, i, "Use of eval()",
                              "eval executes arbitrary strings as code.", "Parse data with JSON.parse or use explicit logic.", lines))
            if "dangerouslySetInnerHTML" in text or re.search(r"\.innerHTML\s*=", text):
                out.append(_f("xss-sink", "medium", "security", path, i, "Raw HTML injection",
                              "Assigning raw HTML can enable cross-site scripting if the value is user-controlled.",
                              "Render text via React/DOM text nodes or sanitize with DOMPurify.", lines))
    return out


def run_static_review(root: Path, files: list[dict]) -> list[dict]:
    findings = []
    for f in files:
        if f["language"] in ("Markdown", "Text", "JSON", "Other"):
            continue
        full = root / f["path"]
        try:
            source = read_text(full)
        except OSError:
            continue
        lines = source.splitlines()
        if f["language"] == "Python":
            findings += _python_findings(f["path"], source, lines)
        findings += _generic_findings(f["path"], lines)
    order = {"high": 0, "medium": 1, "low": 2}
    seen, unique = set(), []
    for x in sorted(findings, key=lambda x: (order[x["severity"]], x["path"], x["line"])):
        if x["id"] not in seen:
            seen.add(x["id"])
            unique.append(x)
    return unique
