# RepoMind — Agentic AI Code Intelligence Platform

Upload a ZIP of a repository, then explore it, ask questions, and let a LangGraph multi-agent team
analyse architecture, review code and plan tests. Answers are grounded in retrieved source code with
file + line citations. **Uploaded code is never executed.**

```
React + TS + Vite + Tailwind  ──/api──►  FastAPI  ──►  LangGraph (Supervisor → Analyst / Architecture / Review / Testing → Synthesizer)
                                                         ├─ Repository tools (list/read/search/graph/findings/tests)
                                                         ├─ ChromaDB + all-MiniLM-L6-v2 (AST-aware chunks, line ranges)
                                                         └─ OpenRouter (function calling + structured output)
```

## Requirements (Windows 10/11)
- **Python 3.11 or 3.12** (https://www.python.org/downloads/ — tick "Add python.exe to PATH")
- **Node.js 18+** (https://nodejs.org)
- **VS Code** (https://code.visualstudio.com)
- An **OpenRouter API key** (https://openrouter.ai/keys) — optional to start, required for AI features
- ~3 GB free disk and internet on first run (PyTorch + the MiniLM model, ~90 MB, download once)

## Setup in VS Code (PowerShell)
1. Unzip, then **File → Open Folder…** → the `repomind` folder. Install the recommended extensions when prompted.
2. Open a terminal (**Terminal → New Terminal**, PowerShell) and set up the backend:
```powershell
cd backend
py -3.12 -m venv .venv          # or: py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1    # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
copy ..\.env.example .env
notepad .env                    # paste your key after OPENROUTER_API_KEY=
```
3. Set up the frontend (second terminal):
```powershell
cd frontend
npm install
```
4. Run both. Either press **Ctrl+Shift+P → Tasks: Run Task → "Run RepoMind (backend + frontend)"**, or in two terminals:
```powershell
# terminal 1
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend; npm run dev
```
5. Open **http://localhost:5173**, then upload `sample/tasktracker-sample.zip` (a demo repo with a circular
   import, security smells and partial tests).

The first upload downloads the MiniLM model, so indexing takes longer once. Restart the backend after editing `.env`.

## Try it
- **Overview**: languages, frameworks, dependency files.  **Explorer**: tree + syntax-highlighted code.
- **Ask codebase**: "Where is SQL executed?" → answer + clickable citations; live agent activity on the right.
- **Architecture**: graph, circular dependency `tracker.models → tracker.storage → tracker.models`.
- **Code review**: *Verified* findings (rule-matched, real lines) vs *AI suggestion* (labelled, unconfirmed).
- **Testing**: existing tests, potentially untested modules, AI test plan (never executed).
- **Report**: consolidated markdown with evidence; download as `.md`.

## Tests
```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest -q     # 21 tests
cd frontend; npm run build                              # type-check + production build
```
Tests use `REPOMIND_EMBEDDINGS=hash` (offline vectors) and a fake OpenRouter model to test the plumbing. They do not prove model quality.

## What works without an OpenRouter key
Upload, safe extraction, explorer, language/framework/dependency detection, AST analysis, dependency graph, cycle
detection, verified static findings, test discovery, semantic code search, SSE activity. With no key the chat returns
retrieved code locations only, and AI summaries/suggestions/test plans are disabled and labelled as such.

## Security model
- ZIP: rejects `..`, absolute and drive paths; skips symlinks; size/count limits; strips `.git`, `node_modules`, venvs, caches, binaries.
- Secrets (`.env*`, `*.pem`, `*.key`, `id_rsa`, …) are never extracted, indexed or served.
- File API resolves every path inside the repo workspace and rejects escapes (403).
- OpenRouter key is read from `backend/.env` only; the browser never sees it.
- Uploaded code is only read as text / parsed with `ast`; it is never imported or run. Test execution is **deferred** (no OS-level sandbox).
- Code snippets from your repo are sent to OpenRouter when AI features are used. Don't upload code you may not share.

## Layout
```
backend/app/   main.py (API+SSE) security.py scanner.py codeintel.py review.py testscan.py chunker.py
               embeddings.py rag.py tools.py llm.py runs.py pipeline.py agents/graph.py
backend/tests/ pytest suite            frontend/src/  pages/ components/ hooks/ api.ts
sample/        demo repo + ZIP          docs/VERIFICATION_REPORT.md
```

## Troubleshooting
- *"Cannot reach the backend"*: start uvicorn on port 8000.  *OpenRouter key missing badge*: check `backend/.env`, restart backend.
- *OpenRouter errors (quota/model name)*: set `OPENROUTER_MODEL` in `.env` to a model available through OpenRouter; the Activity page shows the error event.
- *OpenRouter credit/token limit*: lower `OPENROUTER_MAX_TOKENS` (default `8192`) in `.env` and restart the backend.
- *`pip install` is slow*: PyTorch is large. Offline demo: set `REPOMIND_EMBEDDINGS=hash` (weaker search).
- Data lives in `backend/data/` (delete it to reset).
