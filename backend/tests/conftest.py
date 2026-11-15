import os
import time
from pathlib import Path

import pytest

SAMPLE_ZIP = Path(__file__).resolve().parents[2] / "sample" / "tasktracker-sample.zip"


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    os.environ["REPOMIND_DATA_DIR"] = str(tmp_path_factory.mktemp("data"))
    os.environ["REPOMIND_EMBEDDINGS"] = "hash"  # offline test vectors; real runs use MiniLM
    os.environ["OPENROUTER_API_KEY"] = ""


@pytest.fixture(scope="session")
def client(_env):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="session")
def repo_id(client):
    with open(SAMPLE_ZIP, "rb") as f:
        r = client.post("/api/repos", files={"file": ("tasktracker.zip", f, "application/zip")})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    for _ in range(100):
        meta = client.get(f"/api/repos/{rid}").json()
        if meta["status"] in ("ready", "error"):
            break
        time.sleep(0.2)
    assert meta["status"] == "ready", meta
    return rid
