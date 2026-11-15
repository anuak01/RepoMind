"""Upload processing pipeline: extract -> scan -> analyze -> review -> test discovery -> index."""
import threading
import traceback
from pathlib import Path

from . import rag, store
from .codeintel import analyze_repository, summarize_architecture
from .review import run_static_review
from .scanner import detect_frameworks, language_stats, parse_dependencies, scan_files
from .testscan import discover_tests

STAGES = ["extracting", "scanning", "analyzing", "indexing", "ready"]


def analyze_and_index(repo_id: str) -> None:
    root = store.repo_root(repo_id)
    try:
        store.save_meta(repo_id, status="processing", stage="scanning", progress=20)
        files = scan_files(root)
        if not files:
            raise ValueError("No readable source files were found in the archive")
        manifests = parse_dependencies(root, files)

        store.save_meta(repo_id, stage="analyzing", progress=40)
        graph = analyze_repository(root, files)
        findings = run_static_review(root, files)
        testing = discover_tests(root, files, graph)
        store.save_analysis(repo_id, {
            "files": files, "languages": language_stats(files), "frameworks": detect_frameworks(manifests),
            "manifests": manifests, "graph": graph, "architecture_facts": summarize_architecture(graph),
            "static_findings": findings, "testing": testing,
        })

        store.save_meta(repo_id, stage="indexing", progress=60)

        def progress(done, total):
            store.save_meta(repo_id, progress=60 + int(38 * done / max(total, 1)))

        idx = rag.index_repository(repo_id, root, files, progress)
        store.save_meta(repo_id, status="ready", stage="ready", progress=100, index=idx, error=None,
                        counts={"files": len(files), "lines": sum(f["lines"] for f in files),
                                "modules": len(graph["nodes"]), "findings": len(findings)})
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        traceback.print_exc()
        store.save_meta(repo_id, status="error", stage="error", error=f"{type(exc).__name__}: {exc}")


def start_background(repo_id: str) -> None:
    threading.Thread(target=analyze_and_index, args=(repo_id,), daemon=True).start()
