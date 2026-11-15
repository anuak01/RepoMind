"""Embedding backends. Default: sentence-transformers/all-MiniLM-L6-v2.
REPOMIND_EMBEDDINGS=hash selects a deterministic keyword-hash vectoriser that needs no model
download. It exists for offline automated tests only and is far weaker than MiniLM."""
import hashlib
import math
import re

from .config import settings

DIM = 384
_model = None


def _tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).replace("_", " ")
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9]{1,}", text)]


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for tok in _tokens(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % DIM] += 1.0 if (h >> 8) % 2 else -1.0
        vec[(h >> 16) % DIM] += 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def backend_name() -> str:
    return "hash (offline test mode)" if settings.embeddings == "hash" else "sentence-transformers/all-MiniLM-L6-v2"


def embed(texts: list[str]) -> list[list[float]]:
    global _model
    if settings.embeddings == "hash":
        return [_hash_embed(t) for t in texts]
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False).tolist()
