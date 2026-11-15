"""RepoMind FastAPI application."""
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import embeddings, llm, pipeline, rag, runs, store
from .agents.graph import execute
from .config import settings
from .scanner import build_tree, language_for, read_text
from .security import UnsafeZipError, resolve_in_root, safe_extract_zip

app = FastAPI(title="RepoMind API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    mode: str = Field("chat", pattern="^(chat|architecture|review|testing|report)$")
    message: str = Field("", max_length=2000)


def _ready(repo_id: str) -> dict:
    if not store.exists(repo_id):
        raise HTTPException(404, "Repository not found")
    meta = store.get_meta(repo_id)
    if meta.get("status") != "ready":
        raise HTTPException(409, f"Repository is not ready (status: {meta.get('status')})")
    return meta


@app.get("/api/health")
def health():
    return {"status": "ok", "openrouter_configured": llm.available(), "model": settings.openrouter_model,
            "embeddings": embeddings.backend_name()}


@app.post("/api/repos", status_code=201)
async def upload_repo(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "Please upload a .zip file")
    repo_id = store.new_repo_id()
    d = store.repo_dir(repo_id)
    d.mkdir(parents=True, exist_ok=True)
    store.save_meta(repo_id, id=repo_id, name=Path(file.filename).stem, status="processing", stage="extracting",
                    progress=5, created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, f"Upload exceeds {settings.max_upload_bytes // 1048576} MB")
                tmp.write(chunk)
        stats = safe_extract_zip(Path(tmp.name), store.repo_root(repo_id))
        Path(tmp.name).unlink(missing_ok=True)
        store.save_meta(repo_id, extraction=stats, progress=15)
    except UnsafeZipError as exc:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, str(exc))
    except HTTPException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    pipeline.start_background(repo_id)
    return store.get_meta(repo_id)


@app.get("/api/repos")
def list_repos():
    return store.list_repos()


@app.get("/api/repos/{repo_id}")
def get_repo(repo_id: str):
    if not store.exists(repo_id):
        raise HTTPException(404, "Repository not found")
    return store.get_meta(repo_id)


@app.delete("/api/repos/{repo_id}")
def delete_repo(repo_id: str):
    if not store.exists(repo_id):
        raise HTTPException(404, "Repository not found")
    rag.delete_index(repo_id)
    store.delete_repo(repo_id)
    return {"deleted": repo_id}


@app.get("/api/repos/{repo_id}/overview")
def overview(repo_id: str):
    meta = _ready(repo_id)
    a = store.get_analysis(repo_id)
    return {"meta": meta, "languages": a["languages"], "frameworks": a["frameworks"], "manifests": a["manifests"],
            "total_files": len(a["files"]), "total_lines": sum(f["lines"] for f in a["files"]),
            "parse_errors": a["graph"]["parse_errors"]}


@app.get("/api/repos/{repo_id}/tree")
def tree(repo_id: str):
    _ready(repo_id)
    return build_tree(store.get_analysis(repo_id)["files"])


@app.get("/api/repos/{repo_id}/file")
def get_file(repo_id: str, path: str = Query(..., min_length=1)):
    _ready(repo_id)
    try:
        target = resolve_in_root(store.repo_root(repo_id), path)
    except ValueError as exc:
        raise HTTPException(403, str(exc))
    rel = path.replace("\\", "/").lstrip("/")
    known = {f["path"] for f in store.get_analysis(repo_id)["files"]}
    if rel not in known or not target.is_file():
        raise HTTPException(404, "File not found")
    content = read_text(target)
    return {"path": rel, "language": language_for(rel), "content": content, "lines": content.count("\n") + 1}


@app.get("/api/repos/{repo_id}/architecture")
def architecture(repo_id: str):
    _ready(repo_id)
    a = store.get_analysis(repo_id)
    g = a["graph"]
    return {"nodes": g["nodes"], "edges": g["edges"], "cycles": g["cycles"], "facts": a["architecture_facts"],
            "ai_summary": store.get_ai_results(repo_id).get("architecture"), "ai_enabled": llm.available()}


@app.get("/api/repos/{repo_id}/review")
def review(repo_id: str):
    _ready(repo_id)
    return {"verified": store.get_analysis(repo_id)["static_findings"],
            "ai_suggestions": store.get_ai_results(repo_id).get("review", []), "ai_enabled": llm.available()}


@app.get("/api/repos/{repo_id}/testing")
def testing(repo_id: str):
    _ready(repo_id)
    t = store.get_analysis(repo_id)["testing"]
    return {**t, "executed": False, "plan": store.get_ai_results(repo_id).get("testing"), "ai_enabled": llm.available()}


@app.get("/api/repos/{repo_id}/report")
def report(repo_id: str):
    _ready(repo_id)
    return store.get_ai_results(repo_id).get("report")


@app.get("/api/repos/{repo_id}/search")
def search(repo_id: str, q: str = Query(..., min_length=2), top_k: int = 6):
    _ready(repo_id)
    return {"query": q, "results": rag.search(repo_id, q, min(top_k, 10))}


@app.post("/api/repos/{repo_id}/runs", status_code=202)
def create_run(repo_id: str, body: RunRequest):
    _ready(repo_id)
    if body.mode == "chat" and not body.message.strip():
        raise HTTPException(400, "A message is required for chat")
    run = runs.start_run(repo_id, body.mode, body.message, lambda r: execute(repo_id, body.mode, body.message, r))
    return {"run_id": run.id}


@app.get("/api/repos/{repo_id}/runs")
def list_runs(repo_id: str):
    if not store.exists(repo_id):
        raise HTTPException(404, "Repository not found")
    return [{k: r.get(k) for k in ("id", "mode", "message", "status", "started_at", "finished_at", "event_count")}
            for r in store.list_runs(repo_id)]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = runs.get_run(run_id)
    if run:
        return run.to_dict()
    for meta in store.list_repos():
        for r in store.list_runs(meta["id"]):
            if r["id"] == run_id:
                return r
    raise HTTPException(404, "Run not found")


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, start: int = 0):
    run = runs.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found or no longer live")

    async def stream():
        idx = start
        idle = 0
        while True:
            batch = run.snapshot_events(idx)
            for ev in batch:
                yield f"id: {ev['seq']}\nevent: agent_event\ndata: {json.dumps(ev)}\n\n"
                idx = ev["seq"] + 1
            if run.status != "running" and not run.snapshot_events(idx):
                break
            idle = 0 if batch else idle + 1
            if idle and idle % 50 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
