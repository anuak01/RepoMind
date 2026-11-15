import zipfile

import pytest

from app.security import UnsafeZipError, is_secret_file, resolve_in_root, safe_extract_zip


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)


def test_traversal_rejected(tmp_path):
    make_zip(tmp_path / "a.zip", {"../evil.txt": "x"})
    with pytest.raises(UnsafeZipError):
        safe_extract_zip(tmp_path / "a.zip", tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_absolute_and_drive_paths_rejected(tmp_path):
    for bad in ("/etc/passwd", "C:/Windows/x.txt"):
        make_zip(tmp_path / "b.zip", {bad: "x"})
        with pytest.raises(UnsafeZipError):
            safe_extract_zip(tmp_path / "b.zip", tmp_path / "out")


def test_secrets_and_ignored_skipped(tmp_path):
    make_zip(tmp_path / "c.zip", {"p/.env": "K=1", "p/id_rsa": "k", "p/node_modules/x.js": "1",
                                  "p/.git/config": "c", "p/app.py": "print(1)", "p/.env.example": "K="})
    stats = safe_extract_zip(tmp_path / "c.zip", tmp_path / "out")
    names = {p.name for p in (tmp_path / "out").rglob("*") if p.is_file()}
    assert names == {"app.py", ".env.example"}
    assert stats["skipped_secret"] == 2 and stats["skipped_ignored"] == 2


def test_resolve_in_root_blocks_escape(tmp_path):
    (tmp_path / "ok.py").write_text("x")
    assert resolve_in_root(tmp_path, "ok.py").name == "ok.py"
    for bad in ("../x", "/etc/passwd", "a/../../x", ".env", "node_modules/x.js"):
        with pytest.raises(ValueError):
            resolve_in_root(tmp_path, bad)


def test_secret_detection():
    assert is_secret_file("config/.env") and is_secret_file("a/server.pem")
    assert not is_secret_file(".env.example")
