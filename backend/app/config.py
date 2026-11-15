"""Central configuration. All secrets come from backend environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")


class Settings:
    @property
    def openrouter_api_key(self) -> str:
        return os.getenv("OPENROUTER_API_KEY", "").strip()

    @property
    def openrouter_model(self) -> str:
        return os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    @property
    def openrouter_max_tokens(self) -> int:
        return int(os.getenv("OPENROUTER_MAX_TOKENS", "8192"))

    @property
    def data_dir(self) -> Path:
        return Path(os.getenv("REPOMIND_DATA_DIR", str(BACKEND_DIR / "data"))).resolve()

    @property
    def embeddings(self) -> str:
        return os.getenv("REPOMIND_EMBEDDINGS", "minilm").lower()

    @property
    def max_upload_bytes(self) -> int:
        return int(os.getenv("MAX_UPLOAD_MB", "100")) * 1024 * 1024

    max_unzipped_bytes = 300 * 1024 * 1024
    max_files = 10_000
    max_file_bytes = 1_000_000  # files larger than this are not read/indexed

    @property
    def cors_origins(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
