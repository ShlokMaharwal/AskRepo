"""SQLite repository registry and an immutable, validated source-file store."""

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.ingest.chunker import Chunk, language_for
from app.models import RepoSummary


def contained_path(root: Path, relative: str) -> Path:
    if (
        not relative
        or "\0" in relative
        or "\\" in relative
        or PurePosixPath(relative).is_absolute()
        or PureWindowsPath(relative).drive
        or any(part in {"..", "."} for part in relative.split("/"))
        or ":" in relative
    ):
        raise ValueError("Invalid repository file path")
    root = root.resolve()
    candidate = root.joinpath(relative).resolve()
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError("File path escapes the repository")
    return candidate


class Storage:
    def __init__(self, data_dir: Path):
        self.root = data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS repos (
                id TEXT PRIMARY KEY, url TEXT NOT NULL, files INTEGER NOT NULL,
                chunks INTEGER NOT NULL, indexed_at TEXT NOT NULL, revision TEXT NOT NULL,
                status TEXT NOT NULL, embedding_model TEXT NOT NULL DEFAULT '')""")
            connection.execute("""CREATE TABLE IF NOT EXISTS index_admissions (
                day TEXT NOT NULL, url TEXT NOT NULL, PRIMARY KEY(day, url))""")

    def admit_index(self, url, limit):
        """One UTC-day allowance shared by every client of this registry."""
        today = datetime.now(UTC).date().isoformat()
        with self.lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM index_admissions WHERE day < ?", (today,))
            if connection.execute(
                "SELECT 1 FROM index_admissions WHERE day=? AND url=?", (today, url.lower())
            ).fetchone():
                return True
            count = connection.execute(
                "SELECT COUNT(*) FROM index_admissions WHERE day=?", (today,)
            ).fetchone()[0]
            if count >= limit:
                return False
            connection.execute("INSERT INTO index_admissions VALUES (?,?)", (today, url.lower()))
            return True

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.root / "registry.sqlite", timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def repo_dir(self, repo_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", repo_id):
            raise ValueError("Invalid repository identifier")
        return self.root / "repos" / repo_id

    def save(
        self,
        repo_id: str,
        url: str,
        files: list[tuple[str, str]],
        chunks: list[Chunk],
        revision: str,
    ):
        directory = self.repo_dir(repo_id)
        directory.mkdir(parents=True, exist_ok=True)
        source_root = directory / "files"
        expected = {path for path, _ in files}
        # Stable demo IDs can be rebuilt from a newer commit. Remove only obsolete
        # files in this snapshot so its file count stays consistent on next boot.
        for previous in source_root.rglob("*"):
            relative = previous.relative_to(source_root).as_posix()
            if previous.is_file() and relative not in expected:
                contained_path(source_root, relative)
                previous.unlink()
        for path, content in files:
            destination = contained_path(directory / "files", path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
        (directory / "chunks.json").write_text(
            json.dumps([chunk.to_dict() for chunk in chunks]), encoding="utf-8"
        )
        with self.lock, self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO repos VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    repo_id,
                    url,
                    len(files),
                    len(chunks),
                    datetime.now(UTC).isoformat(),
                    revision,
                    "indexing",
                    "",
                ),
            )

    def ready(self, repo_id: str, embedding_model: str = ""):
        with self.lock, self.connect() as connection:
            connection.execute(
                "UPDATE repos SET status='ready', embedding_model=? WHERE id=?",
                (embedding_model, repo_id),
            )

    def fail(self, repo_id: str):
        with self.lock, self.connect() as connection:
            connection.execute("UPDATE repos SET status='failed' WHERE id=?", (repo_id,))

    def recover_interrupted(self):
        with self.lock, self.connect() as connection:
            connection.execute("UPDATE repos SET status='failed' WHERE status='indexing'")

    def entries(self):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM repos")]

    def stale(self, repo_id):
        with self.lock, self.connect() as connection:
            connection.execute("UPDATE repos SET status='stale' WHERE id=?", (repo_id,))

    def healthy_local(self, repo_id, embedding_model):
        """Validate persisted artifacts in the background, never in /health."""
        from app.index.bm25 import BM25

        try:
            metadata = self.metadata(repo_id)
            if metadata["status"] != "ready" or metadata["embedding_model"] != embedding_model:
                return False
            chunks = self.chunks(repo_id)
            keyword = BM25.load(self.repo_dir(repo_id) / "bm25.json")
            if not chunks or len(chunks) != metadata["chunks"]:
                return False
            if keyword.ids != [chunk.id for chunk in chunks]:
                return False
            files = self.files(repo_id)
            paths = {item["path"] for item in files}
            return len(files) == metadata["files"] and all(chunk.path in paths for chunk in chunks)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def metadata(self, repo_id: str):
        self.repo_dir(repo_id)
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM repos WHERE id=?", (repo_id,)).fetchone()
        if row is None:
            raise KeyError("Repository not found")
        return dict(row)

    def repos(self) -> list[RepoSummary]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM repos WHERE status='ready' ORDER BY indexed_at DESC"
            )
            return [
                RepoSummary(
                    repo_id=row["id"],
                    repo_url=row["url"],
                    files=row["files"],
                    chunks=row["chunks"],
                    indexed_at=row["indexed_at"],
                )
                for row in rows
            ]

    def chunks(self, repo_id: str) -> list[Chunk]:
        self.metadata(repo_id)
        data = json.loads((self.repo_dir(repo_id) / "chunks.json").read_text(encoding="utf-8"))
        return [Chunk(**item) for item in data]

    def file(self, repo_id: str, path: str) -> tuple[str, str]:
        metadata = self.metadata(repo_id)
        if metadata["status"] != "ready":
            raise KeyError("Repository is not ready")
        candidate = contained_path(self.repo_dir(repo_id) / "files", path)
        if not candidate.is_file():
            raise FileNotFoundError("File not found")
        return candidate.read_text(encoding="utf-8"), language_for(path)

    def files(self, repo_id: str) -> list[dict]:
        metadata = self.metadata(repo_id)
        if metadata["status"] != "ready":
            raise KeyError("Repository is not ready")
        root = self.repo_dir(repo_id) / "files"
        return [
            {"path": path.relative_to(root).as_posix(), "language": language_for(path.name)}
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.is_symlink()
        ]
