"""Filesystem layout for uploaded repositories: data/repos/<id>/{src,meta.json,analysis.json,...}"""
import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_lock = threading.Lock()


def new_repo_id() -> str:
    return uuid.uuid4().hex[:12]


def repo_dir(repo_id: str) -> Path:
    if not _ID_RE.match(repo_id or ""):
        raise KeyError("Unknown repository")
    return settings.data_dir / "repos" / repo_id


def repo_root(repo_id: str) -> Path:
    return repo_dir(repo_id) / "src"


def exists(repo_id: str) -> bool:
    try:
        return (repo_dir(repo_id) / "meta.json").exists()
    except KeyError:
        return False


def _read(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_meta(repo_id: str) -> dict | None:
    return _read(repo_dir(repo_id) / "meta.json")


def save_meta(repo_id: str, **updates) -> dict:
    with _lock:
        meta = get_meta(repo_id) or {}
        meta.update(updates)
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write(repo_dir(repo_id) / "meta.json", meta)
        return meta


def list_repos() -> list[dict]:
    base = settings.data_dir / "repos"
    out = []
    if base.exists():
        for d in base.iterdir():
            meta = _read(d / "meta.json")
            if meta:
                out.append(meta)
    return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)


def get_analysis(repo_id: str) -> dict | None:
    return _read(repo_dir(repo_id) / "analysis.json")


def save_analysis(repo_id: str, data: dict) -> None:
    _write(repo_dir(repo_id) / "analysis.json", data)


def get_ai_results(repo_id: str) -> dict:
    return _read(repo_dir(repo_id) / "ai_results.json", {}) or {}


def save_ai_result(repo_id: str, key: str, value) -> None:
    with _lock:
        data = get_ai_results(repo_id)
        data[key] = value
        _write(repo_dir(repo_id) / "ai_results.json", data)


def save_run(repo_id: str, run: dict) -> None:
    _write(repo_dir(repo_id) / "runs" / f"{run['id']}.json", run)


def list_runs(repo_id: str) -> list[dict]:
    d = repo_dir(repo_id) / "runs"
    runs = []
    if d.exists():
        for f in d.glob("*.json"):
            r = _read(f)
            if r:
                runs.append(r)
    return sorted(runs, key=lambda r: r.get("started_at", ""), reverse=True)


def delete_repo(repo_id: str) -> None:
    shutil.rmtree(repo_dir(repo_id), ignore_errors=True)
