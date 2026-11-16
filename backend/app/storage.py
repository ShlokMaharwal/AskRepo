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
