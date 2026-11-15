"""Agent runs and their real execution events (consumed by the SSE endpoint)."""
import threading
import time
import uuid
from datetime import datetime, timezone

from . import store

RUNS: dict[str, "Run"] = {}


class Run:
    def __init__(self, repo_id: str, mode: str, message: str):
        self.id = uuid.uuid4().hex[:12]
        self.repo_id, self.mode, self.message = repo_id, mode, message
        self.status = "running"
        self.events: list[dict] = []
        self.result: dict | None = None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: str | None = None
        self._lock = threading.Lock()
        self._t0 = time.time()

    def emit(self, agent: str, type_: str, message: str, data: dict | None = None) -> None:
        with self._lock:
            self.events.append({"seq": len(self.events), "t": round(time.time() - self._t0, 3), "agent": agent,
                                "type": type_, "message": message, "data": data or {}})

    def snapshot_events(self, start: int) -> list[dict]:
        with self._lock:
            return self.events[start:]

    def to_dict(self, include_events: bool = True) -> dict:
        d = {"id": self.id, "repo_id": self.repo_id, "mode": self.mode, "message": self.message,
             "status": self.status, "result": self.result, "started_at": self.started_at,
             "finished_at": self.finished_at, "event_count": len(self.events)}
        if include_events:
            d["events"] = list(self.events)
        return d


def get_run(run_id: str) -> Run | None:
    return RUNS.get(run_id)


def start_run(repo_id: str, mode: str, message: str, runner) -> Run:
    run = Run(repo_id, mode, message)
    RUNS[run.id] = run

    def work():
        run.emit("system", "run_started", f"Run started ({mode})", {"mode": mode, "message": message})
        try:
            run.result = runner(run)
            run.status = "completed"
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.result = {"error": f"{type(exc).__name__}: {exc}"}
            run.emit("system", "error", run.result["error"])
        run.finished_at = datetime.now(timezone.utc).isoformat()
        run.emit("system", "run_finished", f"Run {run.status}", {"status": run.status})
        try:
            store.save_run(repo_id, run.to_dict())
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, daemon=True).start()
    return run
