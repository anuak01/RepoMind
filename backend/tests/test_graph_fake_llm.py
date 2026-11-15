"""Exercises the full LangGraph path with a FAKE OpenRouter model that calls the tools.
This validates our plumbing (tool calling, citation verification, suggestion filtering) -
it does NOT validate OpenRouter itself."""
import time

import pytest

from app import llm
from app.agents import graph as G


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(G.llm, "available", lambda: True)

    def run_tool_agent(system, prompt, tools, max_calls=8):
        by = {t.__name__: t for t in tools}
        if "search_code" in by:
            hits = by["search_code"](query="subprocess run report")
            h = hits["results"][0]
            return f"Found it [{h['path']}:{h['start_line']}-{h['end_line']}] and also made up [nope/fake.py:1-5]."
        return "notes"

    def generate_structured(system, prompt, schema):
        n = schema.__name__
        if n == "SupervisorPlan":
            return schema(intent="question", agents=["analyst"], plan=["search", "answer"], rationale="code question")
        if n == "AISuggestions":
            return schema(suggestions=[
                schema.model_fields["suggestions"].annotation.__args__[0](path="ghost/none.py", line=3, severity="low", category="quality", title="Real", explanation="e", suggestion="s"),
            ])
        raise AssertionError(n)

    monkeypatch.setattr(G.llm, "run_tool_agent", run_tool_agent)
    monkeypatch.setattr(G.llm, "generate_structured", generate_structured)


def wait(client, run_id):
    for _ in range(100):
        r = client.get(f"/api/runs/{run_id}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.2)


def test_chat_graph_verifies_citations(client, repo_id, fake_llm):
    rid = client.post(f"/api/repos/{repo_id}/runs", json={"mode": "chat", "message": "where are reports run?"}).json()["run_id"]
    r = wait(client, rid)
    res = r["result"]
    assert r["status"] == "completed" and res["ai_enabled"] is True
    assert len(res["citations"]) == 1 and res["citations"][0]["path"].startswith("tracker/")
    assert "[nope/fake.py:1-5]" in res["unverified_citations"]  # fabricated citation caught
    tool_calls = [e for e in r["events"] if e["type"] == "tool_call"]
    assert any(e["data"]["tool"] == "search_code" for e in tool_calls)


def test_review_drops_unread_ai_suggestions(client, repo_id, fake_llm):
    rid = client.post(f"/api/repos/{repo_id}/runs", json={"mode": "review"}).json()["run_id"]
    r = wait(client, rid)
    assert r["status"] == "completed"
    ai = r["result"]["review"]["ai_suggestions"]
    assert ai == []  # fake review agent never read ghost/none.py, so the suggestion must be dropped
    assert any(e["type"] == "info" and "Dropped" in e["message"] for e in r["events"])
