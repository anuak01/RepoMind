import json
import time


def test_health_reports_no_openrouter(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["openrouter_configured"] is False


def test_non_zip_rejected(client):
    r = client.post("/api/repos", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_traversal_zip_rejected_via_api(client, tmp_path):
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../evil.py", "x")
    r = client.post("/api/repos", files={"file": ("e.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400


def test_upload_excludes_secrets_and_ignored(client, repo_id):
    tree = json.dumps(client.get(f"/api/repos/{repo_id}/tree").json())
    assert ".env" not in tree.replace(".env.example", "") and "node_modules" not in tree
    assert "storage.py" in tree


def test_overview(client, repo_id):
    o = client.get(f"/api/repos/{repo_id}/overview").json()
    assert o["total_files"] >= 7 and any(l["language"] == "Python" for l in o["languages"])
    assert "Flask" in o["frameworks"]


def test_file_view_and_path_guard(client, repo_id):
    ok = client.get(f"/api/repos/{repo_id}/file", params={"path": "tracker/utils.py"})
    assert ok.status_code == 200 and "slugify" in ok.json()["content"]
    for bad in ("../../../etc/passwd", ".env", "tracker/../../meta.json", "/etc/passwd"):
        assert client.get(f"/api/repos/{repo_id}/file", params={"path": bad}).status_code in (403, 404)


def test_architecture_finds_cycle(client, repo_id):
    a = client.get(f"/api/repos/{repo_id}/architecture").json()
    assert a["cycles"], "circular import models<->storage must be detected"
    assert set(a["cycles"][0]["modules"]) >= {"tracker.models", "tracker.storage"}


def test_review_verified_findings(client, repo_id):
    rules = {f["rule"] for f in client.get(f"/api/repos/{repo_id}/review").json()["verified"]}
    assert {"dangerous-eval", "shell-injection", "sql-injection", "hardcoded-secret", "bare-except",
            "unsafe-deserialization", "weak-hash", "mutable-default"} <= rules


def test_review_lines_are_real(client, repo_id):
    for f in client.get(f"/api/repos/{repo_id}/review").json()["verified"]:
        src = client.get(f"/api/repos/{repo_id}/file", params={"path": f["path"]}).json()["content"].splitlines()
        assert 0 < f["line"] <= len(src)


def test_testing_discovery(client, repo_id):
    t = client.get(f"/api/repos/{repo_id}/testing").json()
    assert t["executed"] is False and t["total_cases"] == 1
    untested = {u["path"] for u in t["untested_modules"]}
    assert "tracker/service.py" in untested and "tracker/utils.py" not in untested


def test_rag_returns_cited_chunks(client, repo_id):
    r = client.get(f"/api/repos/{repo_id}/search", params={"q": "sql query find task by title"}).json()
    top = r["results"][0]
    assert top["path"] == "tracker/storage.py" and top["start"] <= top["end"]


def test_chat_without_key_is_honest_and_streams_real_events(client, repo_id):
    run_id = client.post(f"/api/repos/{repo_id}/runs", json={"mode": "chat", "message": "how is sql executed?"}).json()["run_id"]
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as s:
        assert s.headers["content-type"].startswith("text/event-stream")
        for line in s.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    types = [e["type"] for e in events]
    assert types[0] == "run_started" and types[-1] == "run_finished"
    assert "tool_call" in types and "tool_result" in types
    assert {e["agent"] for e in events} >= {"supervisor", "analyst", "synthesizer"}
    result = client.get(f"/api/runs/{run_id}").json()["result"]
    assert result["ai_enabled"] is False and "unavailable" in result["answer"]
    for c in result["citations"]:  # citations only for retrieved code
        assert client.get(f"/api/repos/{repo_id}/file", params={"path": c["path"]}).status_code == 200


def test_report_mode_without_key(client, repo_id):
    run_id = client.post(f"/api/repos/{repo_id}/runs", json={"mode": "report", "message": ""}).json()["run_id"]
    for _ in range(100):
        r = client.get(f"/api/runs/{run_id}").json()
        if r["status"] != "running":
            break
        time.sleep(0.2)
    assert r["status"] == "completed", r
    md = r["result"]["report_markdown"]
    assert "Circular dependencies" in md and "Verified findings" in md and "not executed" in md
    assert client.get(f"/api/repos/{repo_id}/report").json()["markdown"] == md


def test_chat_requires_message(client, repo_id):
    assert client.post(f"/api/repos/{repo_id}/runs", json={"mode": "chat", "message": " "}).status_code == 400
