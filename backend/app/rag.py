"""ChromaDB vector index with source-grounded retrieval (every hit carries file + line range)."""
from pathlib import Path

import chromadb

from . import embeddings
from .chunker import chunk_file
from .config import settings
from .scanner import read_text

MAX_CHUNKS = 8000
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}
_client = None


def _get_client():
    global _client
    path = str(settings.data_dir / "chroma")
    if _client is None or getattr(_client, "_repomind_path", None) != path:
        settings.data_dir.joinpath("chroma").mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=path)
        _client._repomind_path = path
    return _client


def _name(repo_id: str) -> str:
    return f"repo_{repo_id}"


def delete_index(repo_id: str) -> None:
    try:
        _get_client().delete_collection(_name(repo_id))
    except Exception:
        pass


def index_repository(repo_id: str, root: Path, files: list[dict], progress=None) -> dict:
    delete_index(repo_id)
    col = _get_client().get_or_create_collection(_name(repo_id), metadata={"hnsw:space": "cosine"})
    ids, docs, metas = [], [], []
    truncated = False
    for f in files:
        if f["language"] in ("Other",) or Path(f["path"]).name in SKIP_NAMES:
            continue
        if f["language"] == "JSON" and f["size"] > 100_000:
            continue
        text = read_text(root / f["path"])
        for i, c in enumerate(chunk_file(f["path"], text, f["language"])):
            if len(ids) >= MAX_CHUNKS:
                truncated = True
                break
            ids.append(f"{f['path']}#{i}")
            header = f"{f['path']} ({c['kind']} {c['name']})\n"
            docs.append(c["text"])
            metas.append({"path": f["path"], "start": c["start"], "end": c["end"], "kind": c["kind"],
                          "name": c["name"], "language": f["language"], "_embed": header + c["text"]})
    batch = 64
    for i in range(0, len(ids), batch):
        sl = slice(i, i + batch)
        to_embed = [m.pop("_embed") for m in metas[sl]]
        col.add(ids=ids[sl], documents=docs[sl], metadatas=metas[sl], embeddings=embeddings.embed(to_embed))
        if progress:
            progress(min(i + batch, len(ids)), len(ids))
    return {"chunks": len(ids), "truncated": truncated, "embedding_backend": embeddings.backend_name()}


def search(repo_id: str, query: str, top_k: int = 6) -> list[dict]:
    try:
        col = _get_client().get_collection(_name(repo_id))
    except Exception:
        return []
    n = col.count()
    if n == 0 or not query.strip():
        return []
    res = col.query(query_embeddings=embeddings.embed([query]), n_results=min(top_k, n))
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"path": meta["path"], "start": meta["start"], "end": meta["end"], "kind": meta["kind"],
                     "name": meta["name"], "score": round(1 - dist, 4), "text": doc})
    return hits
