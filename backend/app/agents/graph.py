"""LangGraph multi-agent workflow.

supervisor -> (analyst | architecture | review | testing)* -> synthesizer

All agents share one structured state (RepoState) and one instrumented ToolBox, so every tool
call is a real backend event. Deterministic analysis always runs; OpenRouter adds reasoning on top
and is clearly labelled. Without OPENROUTER_API_KEY the AI parts are skipped and the result says so.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from .. import llm, store
from ..tools import ToolBox

AGENTS = ["architecture", "review", "testing", "analyst"]
MODE_AGENTS = {"architecture": ["architecture"], "review": ["review"], "testing": ["testing"],
               "report": ["architecture", "review", "testing", "analyst"]}
LABELS = {"supervisor": "Supervisor", "analyst": "Repository Analyst", "architecture": "Architecture Agent",
          "review": "Code Review Agent", "testing": "Testing Agent", "synthesizer": "Synthesizer"}


class RepoState(TypedDict, total=False):
    repo_id: str
    request: str
    mode: str
    intent: str
    plan: list[str]
    agents: list[str]
    completed: list[str]
    architecture: dict
    review: dict
    testing: dict
    answer: str
    errors: list[str]
    result: dict


# ---------- structured outputs ----------
class SupervisorPlan(BaseModel):
    intent: Literal["question", "architecture", "review", "testing"]
    agents: list[Literal["analyst", "architecture", "review", "testing"]]
    plan: list[str] = Field(description="2-4 short steps")
    rationale: str


class AISuggestion(BaseModel):
    path: str
    line: int
    severity: Literal["high", "medium", "low"]
    category: Literal["security", "bug", "quality", "performance"]
    title: str
    explanation: str
    suggestion: str


class AISuggestions(BaseModel):
    suggestions: list[AISuggestion]


class SampleTest(BaseModel):
    target: str = Field(description="repo path of the module under test")
    framework: str
    description: str
    code: str


class TestPlan(BaseModel):
    summary: str
    priorities: list[str]
    sample_tests: list[SampleTest]


class ArchSummary(BaseModel):
    summary: str
    risks: list[str]
    recommendations: list[str]


# ---------- helpers ----------
def _keyword_intent(text: str) -> tuple[str, list[str]]:
    t = text.lower()
    if any(w in t for w in ("circular", "dependenc", "architecture", "module", "structure", "layer")):
        return "architecture", ["architecture", "analyst"]
    if any(w in t for w in ("bug", "security", "vulnerab", "review", "smell", "unsafe", "quality")):
        return "review", ["review", "analyst"]
    if any(w in t for w in ("test", "coverage", "pytest", "untested")):
        return "testing", ["testing", "analyst"]
    return "question", ["analyst"]


def build_graph(repo_id: str, run) -> tuple:
    tb = ToolBox(repo_id, run.emit)
    ai = llm.available()

    def say(agent, type_, msg, data=None):
        run.emit(agent, type_, msg, data)

    def start(agent, task):
        tb.agent = agent
        say(agent, "agent_started", LABELS[agent], {"task": task})
        say(agent, "task", task)

    def done(agent, summary):
        say(agent, "agent_finished", summary)

    def ai_failed(agent, exc, state):
        msg = f"{type(exc).__name__}: {exc}"
        say(agent, "error", f"OpenRouter call failed - continuing with deterministic results ({msg[:200]})")
        return (state.get("errors") or []) + [f"{agent}: {msg[:300]}"]

    # ---------- supervisor ----------
    def supervisor(state: RepoState):
        start("supervisor", "Classify the request and plan which agents to run")
        mode = state["mode"]
        if mode in MODE_AGENTS:
            agents, intent = MODE_AGENTS[mode], mode
            plan = [f"Run {LABELS[a]}" for a in agents]
            say("supervisor", "plan", f"Mode '{mode}' selected by the user; delegating to {', '.join(agents)}", {"agents": agents})
        else:
            agents, intent, plan = None, None, []
            if ai:
                try:
                    p = llm.generate_structured(
                        "You are the Supervisor of a code-intelligence agent team. Classify the user's question about a "
                        "software repository and choose agents. Use 'analyst' for general code questions; add "
                        "'architecture' for module/dependency questions, 'review' for bugs/security, 'testing' for tests. "
                        "Always include 'analyst' last so it can write the final answer.",
                        state["request"], SupervisorPlan)
                    intent, agents, plan = p.intent, list(dict.fromkeys(p.agents)) or ["analyst"], p.plan
                    if "analyst" not in agents:
                        agents.append("analyst")
                    say("supervisor", "plan", p.rationale, {"agents": agents, "plan": plan, "classifier": "openrouter"})
                except Exception as exc:  # noqa: BLE001
                    state["errors"] = ai_failed("supervisor", exc, state)
            if agents is None:
                intent, agents = _keyword_intent(state["request"])
                plan = [f"Run {LABELS[a]}" for a in agents]
                say("supervisor", "plan", "Keyword routing used" + ("" if not ai else " (OpenRouter classification failed)")
                    + (" because OPENROUTER_API_KEY is not set" if not ai else ""), {"agents": agents, "classifier": "keywords"})
        done("supervisor", f"Intent: {intent}; agents: {', '.join(agents)}")
        return {"intent": intent, "agents": agents, "plan": plan, "completed": [], "errors": state.get("errors", [])}

    # ---------- architecture ----------
    def architecture(state: RepoState):
        start("architecture", "Analyse modules, dependency edges and circular imports")
        arch = tb.call("get_architecture")
        cyc = tb.call("find_circular_dependencies")
        facts = tb.analysis["architecture_facts"]
        out = {"facts": facts["facts"], "hubs": facts["hubs"], "entry_points": facts["entry_points"],
               "top_external": facts["top_external"], "cycles": cyc["cycles"], "ai_summary": None}
        errors = state.get("errors", [])
        if ai:
            try:
                text = llm.run_tool_agent(
                    "You are the Architecture Agent. Use tools to inspect real modules; never invent modules.",
                    "Explore the architecture: call get_architecture, find_circular_dependencies, and read key modules "
                    "(hubs/entry points) with read_file. Write findings notes with [path:start-end] citations.",
                    tb.agent_tools(["get_architecture", "find_circular_dependencies", "get_symbols", "read_file", "search_code"]), 8)
                s = llm.generate_structured(
                    "Summarise the architecture for a developer using ONLY the notes and facts given.",
                    f"Facts:\n{arch}\n\nCycles:\n{cyc}\n\nNotes:\n{text}", ArchSummary)
                out["ai_summary"] = s.model_dump()
                store.save_ai_result(repo_id, "architecture", out["ai_summary"])
            except Exception as exc:  # noqa: BLE001
                errors = ai_failed("architecture", exc, state)
        else:
            say("architecture", "info", "AI summary skipped: OPENROUTER_API_KEY not set (graph facts are still real)")
        done("architecture", f"{len(cyc['cycles'])} cycle group(s), {arch['modules']} modules")
        return {"architecture": out, "completed": state["completed"] + ["architecture"], "errors": errors}

    # ---------- review ----------
    def review(state: RepoState):
        start("review", "Collect verified static findings, then look for deeper issues")
        static = tb.call("get_static_findings")
        verified = [f for f in tb.analysis["static_findings"]]
        suggestions, errors = [], state.get("errors", [])
        if ai:
            try:
                notes = llm.run_tool_agent(
                    "You are the Code Review Agent. Read real code with tools. Only report issues you can point to "
                    "at an exact file and line that you have read.",
                    f"Static analysis already found {static['count']} issues (get_static_findings). Look for ADDITIONAL "
                    "bugs, security problems or design smells by reading the riskiest files (auth, input handling, "
                    "db, network, subprocess). Summarise candidate issues with path and line.",
                    tb.agent_tools(["get_static_findings", "list_files", "read_file", "search_code", "get_symbols"]), 10)
                parsed = llm.generate_structured(
                    "Turn the review notes into structured suggestions. Include only items grounded in the notes.",
                    notes, AISuggestions)
                known = {(f["path"], f["line"]) for f in verified}
                for s in parsed.suggestions:
                    if (s.path, s.line) in known:
                        continue
                    rng = [e for e in tb.evidence if e["path"] == s.path and e["start"] <= s.line <= e["end"]]
                    if not rng:  # never keep a suggestion pointing at code the agent did not read
                        say("review", "info", f"Dropped unverifiable suggestion at {s.path}:{s.line}")
                        continue
                    lines = (tb.root / s.path).read_text(encoding="utf-8", errors="replace").splitlines()
                    d = s.model_dump()
                    d.update({"id": f"ai:{s.path}:{s.line}", "origin": "ai_suggestion", "rule": "ai-review",
                              "snippet": lines[s.line - 1].strip()[:200] if 0 < s.line <= len(lines) else ""})
                    suggestions.append(d)
                store.save_ai_result(repo_id, "review", suggestions)
            except Exception as exc:  # noqa: BLE001
                errors = ai_failed("review", exc, state)
        else:
            say("review", "info", "AI review skipped: OPENROUTER_API_KEY not set (verified static findings are still real)")
        done("review", f"{len(verified)} verified finding(s), {len(suggestions)} AI suggestion(s)")
        return {"review": {"verified": verified, "ai_suggestions": suggestions}, "completed": state["completed"] + ["review"], "errors": errors}

    # ---------- testing ----------
    def testing(state: RepoState):
        start("testing", "Discover existing tests and untested modules; draft a test plan")
        found = tb.call("discover_tests")
        t = tb.analysis["testing"]
        out = {"existing": t["tests"], "frameworks": t["frameworks"], "total_cases": t["total_cases"],
               "untested_modules": t["untested_modules"], "plan": None, "executed": False,
               "note": "Tests were NOT executed. Generated tests are unverified drafts."}
        errors = state.get("errors", [])
        if ai:
            try:
                targets = [u["path"] for u in t["untested_modules"][:4]]
                notes = llm.run_tool_agent(
                    "You are the Testing Agent. Read the real modules before proposing tests. Never claim tests pass.",
                    f"Frameworks in use: {t['frameworks'] or 'none found'}. Read these untested modules and understand their "
                    f"public functions: {targets}. Describe behaviours worth testing.",
                    tb.agent_tools(["read_file", "get_symbols", "search_code", "discover_tests"]), 8)
                plan = llm.generate_structured(
                    "Write a test plan and 2-4 sample test cases (pytest for Python, vitest/jest for JS) for the modules "
                    "described. Use only functions that exist in the notes.", notes, TestPlan)
                out["plan"] = plan.model_dump()
                store.save_ai_result(repo_id, "testing", out["plan"])
            except Exception as exc:  # noqa: BLE001
                errors = ai_failed("testing", exc, state)
        else:
            say("testing", "info", "AI test plan skipped: OPENROUTER_API_KEY not set (test discovery is still real)")
        done("testing", f"{len(t['tests'])} test file(s), {len(t['untested_modules'])} potentially untested module(s)")
        return {"testing": out, "completed": state["completed"] + ["testing"], "errors": errors}

    # ---------- analyst ----------
    def analyst(state: RepoState):
        is_report = state["mode"] == "report"
        task = "Write an executive summary of the repository" if is_report else "Answer the question using retrieved source code"
        start("analyst", task)
        question = state["request"] if not is_report else "Give a concise executive summary of this repository: purpose, structure, main risks."
        context = {k: state.get(k) for k in ("architecture", "review", "testing") if state.get(k)}
        errors = state.get("errors", [])
        if ai:
            try:
                brief = ""
                if context.get("architecture"):
                    brief += "Architecture facts: " + " ".join(context["architecture"]["facts"]) + "\n"
                if context.get("review"):
                    brief += f"Verified findings: {len(context['review']['verified'])}\n"
                if context.get("testing"):
                    brief += f"Untested modules (heuristic): {len(context['testing']['untested_modules'])}\n"
                answer = llm.run_tool_agent(
                    "You are the Repository Analyst. ALWAYS use search_code / read_file before answering. Ground every claim in "
                    "code you retrieved and cite it as [path:start-end] using ONLY line ranges returned by the tools. "
                    "If the code does not contain the answer, say so plainly. Do not invent files, functions or line numbers.",
                    f"{brief}\nQuestion: {question}", tb.agent_tools(
                        ["search_code", "read_file", "list_files", "get_symbols", "get_architecture", "get_dependencies",
                         "find_circular_dependencies", "get_static_findings", "discover_tests"]), 10)
                done("analyst", "Answer written")
                return {"answer": answer, "completed": state["completed"] + ["analyst"], "errors": errors}
            except Exception as exc:  # noqa: BLE001
                errors = ai_failed("analyst", exc, state)
        # honest fallback: retrieval only
        hits = tb.call("search_code", query=question, top_k=5)
        lines = ["AI answering is unavailable" + (" (OPENROUTER_API_KEY is not set in backend/.env)." if not ai else " (the OpenRouter call failed).")
                 , "Here is the most relevant source code retrieved from your repository:", ""]
        for h in hits["results"]:
            lines.append(f"- [{h['path']}:{h['start_line']}-{h['end_line']}] {h['kind']} `{h['name']}` (relevance {h['score']})")
        if not hits["results"]:
            lines.append("No indexed code matched this question.")
        done("analyst", "Returned retrieval-only results")
        return {"answer": "\n".join(lines), "completed": state["completed"] + ["analyst"], "errors": errors}

    # ---------- synthesizer ----------
    def synthesizer(state: RepoState):
        tb.agent = "synthesizer"
        say("synthesizer", "agent_started", LABELS["synthesizer"], {"task": "Verify citations and assemble the result"})
        answer = state.get("answer", "")
        citations, unverified = tb.verify_citations(answer)
        if unverified:
            say("synthesizer", "info", f"{len(unverified)} citation(s) did not match retrieved code and are marked unverified")
        result = {"intent": state.get("intent"), "agents": state.get("agents"), "plan": state.get("plan"),
                  "answer": answer, "citations": citations, "unverified_citations": unverified,
                  "ai_enabled": ai, "errors": state.get("errors", []),
                  "architecture": state.get("architecture"), "review": state.get("review"), "testing": state.get("testing")}
        if state["mode"] == "report":
            result["report_markdown"] = build_report(repo_id, tb, result)
            store.save_ai_result(repo_id, "report", {"markdown": result["report_markdown"], "citations": citations,
                                                      "ai_enabled": ai})
        say("synthesizer", "agent_finished", f"Result ready with {len(citations)} verified citation(s)")
        return {"result": result}

    # ---------- routing ----------
    def route(state: RepoState) -> str:
        for a in state["agents"]:
            if a not in state["completed"]:
                return a
        return "synthesizer"

    g = StateGraph(RepoState)
    for name, fn in (("supervisor", supervisor), ("architecture", architecture), ("review", review),
                     ("testing", testing), ("analyst", analyst), ("synthesizer", synthesizer)):
        g.add_node(name, fn)
    g.add_edge(START, "supervisor")
    targets = {"architecture": "architecture", "review": "review", "testing": "testing", "analyst": "analyst", "synthesizer": "synthesizer"}
    for n in ("supervisor", "architecture", "review", "testing", "analyst"):
        g.add_conditional_edges(n, route, targets)
    g.add_edge("synthesizer", END)
    return g.compile(), tb


def build_report(repo_id: str, tb: ToolBox, result: dict) -> str:
    a = tb.analysis
    meta = store.get_meta(repo_id) or {}
    md = [f"# RepoMind analysis: {meta.get('name', repo_id)}", ""]
    md += ["## Overview", f"- Files: {len(a['files'])}, lines: {sum(f['lines'] for f in a['files'])}",
           "- Languages: " + ", ".join(f"{l['language']} ({l['lines']} lines)" for l in a["languages"] if l["is_code"]),
           "- Frameworks: " + (", ".join(a["frameworks"]) or "none detected"), ""]
    if result["answer"]:
        md += ["## Executive summary" + ("" if result["ai_enabled"] else " (retrieval only - AI not configured)"), result["answer"], ""]
    arch = result.get("architecture") or {}
    md += ["## Architecture"] + [f"- {x}" for x in arch.get("facts", [])]
    if arch.get("ai_summary"):
        s = arch["ai_summary"]
        md += ["", "**AI summary (generated):** " + s["summary"]] + [f"- Risk: {r}" for r in s["risks"]] + [f"- Recommendation: {r}" for r in s["recommendations"]]
    md += ["", "### Circular dependencies"]
    md += [f"- {' -> '.join(c['path'])}" for c in arch.get("cycles", [])] or ["- None detected"]
    md += ["", "### Declared dependencies"]
    for m in a["manifests"]:
        md.append(f"- `{m['file']}` ({m['type']}): " + ", ".join(d["name"] for d in m["dependencies"][:25]))
    if not a["manifests"]:
        md.append("- No dependency manifests found")
    rv = result.get("review") or {"verified": [], "ai_suggestions": []}
    md += ["", "## Code review", f"### Verified findings ({len(rv['verified'])}) - rule-based, real file and line"]
    for f in rv["verified"][:40]:
        md.append(f"- **{f['severity'].upper()}** [{f['path']}:{f['line']}] {f['title']} - fix: {f['suggestion']}")
    md += ["", f"### AI suggestions ({len(rv['ai_suggestions'])}) - generated, needs human confirmation"]
    for f in rv["ai_suggestions"]:
        md.append(f"- **{f['severity'].upper()}** [{f['path']}:{f['line']}] {f['title']} - {f['suggestion']}")
    if not rv["ai_suggestions"]:
        md.append("- None (AI review not run or nothing found)")
    t = result.get("testing") or {}
    md += ["", "## Testing", f"- Test files: {len(t.get('existing', []))}, cases: {t.get('total_cases', 0)}",
           "- Tests were not executed; no pass/fail claims are made.", "- Potentially untested modules (heuristic): "
           + (", ".join(u["path"] for u in t.get("untested_modules", [])[:10]) or "none")]
    if t.get("plan"):
        md += ["", "**AI test plan (generated, unverified):** " + t["plan"]["summary"]] + [f"- {p}" for p in t["plan"]["priorities"]]
    cites = result["citations"]
    if cites:
        md += ["", "## Evidence"] + [f"- [{c['path']}:{c['start']}-{c['end']}]" for c in cites]
    return "\n".join(md)


def execute(repo_id: str, mode: str, message: str, run) -> dict:
    graph, _tb = build_graph(repo_id, run)
    final = graph.invoke({"repo_id": repo_id, "request": message, "mode": mode, "completed": [], "errors": []})
    return final["result"]
