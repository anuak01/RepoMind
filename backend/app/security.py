"""Ignore rules, secret detection, safe ZIP extraction and workspace path guards."""
import re
import zipfile
from pathlib import Path, PurePosixPath

from .config import settings

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env", "virtualenv",
    "__pycache__", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    "dist", "build", ".next", ".nuxt", ".idea", "site-packages", "target",
    "coverage", ".gradle", "__MACOSX",
}
SECRET_NAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc",
    ".htpasswd", "credentials", "credentials.json", "secrets.json", "secrets.yml",
    "secrets.yaml", "service-account.json", "serviceaccount.json",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".crt", ".cer")
ENV_SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist")
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svgz", ".pdf", ".zip",
    ".gz", ".tar", ".tgz", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".class", ".jar", ".pyc", ".pyo", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".mov", ".avi", ".wav", ".sqlite", ".db", ".lock", ".map",
}


class UnsafeZipError(ValueError):
    pass


def is_ignored_dir(name: str) -> bool:
    return name in IGNORED_DIRS or name.endswith(".egg-info")


def is_secret_file(rel_path: str) -> bool:
    name = PurePosixPath(rel_path).name.lower()
    if name == ".env" or (name.startswith(".env") and not name.endswith(ENV_SAFE_SUFFIXES)):
        return True
    if name.endswith(".env") and not name.endswith(ENV_SAFE_SUFFIXES):
        return True
    return name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES)


def is_ignored_path(rel_path: str) -> bool:
    parts = PurePosixPath(rel_path).parts
    if any(is_ignored_dir(p) for p in parts[:-1]):
        return True
    return is_secret_file(rel_path)


def is_binary_name(rel_path: str) -> bool:
    name = rel_path.lower()
    return PurePosixPath(name).suffix in BINARY_SUFFIXES or name.endswith(".min.js")


def resolve_in_root(root: Path, rel_path: str) -> Path:
    """Resolve rel_path inside root or raise ValueError. Blocks traversal, symlink escapes,
    secrets and ignored directories."""
    if rel_path is None or "\x00" in rel_path:
        raise ValueError("Invalid path")
    if rel_path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel_path):
        raise ValueError("Absolute paths are not allowed")
    rel = rel_path.replace("\\", "/")
    root_resolved = root.resolve()
    target = (root_resolved / rel).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError("Path is outside the repository workspace")
    if rel and is_ignored_path(rel):
        raise ValueError("Path is excluded (secret or ignored directory)")
    return target


def safe_extract_zip(zip_path: Path, dest: Path) -> dict:
    """Extract a ZIP into dest. Rejects traversal / absolute paths, skips symlinks, ignored
    dirs, secrets and binary files, and enforces size and count limits."""
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    stats = {"extracted": 0, "skipped_secret": 0, "skipped_ignored": 0,
             "skipped_binary": 0, "skipped_symlink": 0, "skipped_large": 0}
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise UnsafeZipError("File is not a valid ZIP archive") from exc

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > settings.max_files:
            raise UnsafeZipError(f"Archive has too many files (limit {settings.max_files})")
        if sum(i.file_size for i in infos) > settings.max_unzipped_bytes:
            raise UnsafeZipError("Archive is too large when uncompressed")

        entries = []
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts:
                raise UnsafeZipError(f"Unsafe path in archive: {info.filename}")
            entries.append((info, name))

        # Strip a single shared top-level folder (GitHub-style archives)
        tops = {PurePosixPath(n).parts[0] for _, n in entries if len(PurePosixPath(n).parts) > 1}
        single_top = len(tops) == 1 and all(len(PurePosixPath(n).parts) > 1 for _, n in entries)

        for info, name in entries:
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                stats["skipped_symlink"] += 1
                continue
            parts = PurePosixPath(name).parts
            rel = "/".join(parts[1:]) if single_top else name
            if not rel:
                continue
            if is_secret_file(rel):
                stats["skipped_secret"] += 1
                continue
            if is_ignored_path(rel):
                stats["skipped_ignored"] += 1
                continue
            if is_binary_name(rel):
                stats["skipped_binary"] += 1
                continue
            if info.file_size > settings.max_file_bytes:
                stats["skipped_large"] += 1
                continue
            target = (dest_resolved / rel).resolve()
            if dest_resolved not in target.parents:
                raise UnsafeZipError(f"Unsafe path in archive: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(65536):
                    written += len(chunk)
                    if written > settings.max_file_bytes:
                        break
                    out.write(chunk)
            stats["extracted"] += 1
    return stats
