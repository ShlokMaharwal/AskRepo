"""Copy immutable ready indexes using SQLite's online backup, without taking Qdrant's lock."""

import argparse
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import Settings


def backup_database(source, destination):
    source_db = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    destination_db = sqlite3.connect(destination)
    try:
        source_db.backup(destination_db, pages=128, sleep=0.01)
    finally:
        destination_db.close()
        source_db.close()


def snapshot_indexes(source: Path, destination: Path, urls=None):
    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("Snapshot must be outside the live data directory")
    destination.mkdir(parents=True, exist_ok=False)
    backup_database(source / "registry.sqlite", destination / "registry.sqlite")
    connection = sqlite3.connect(destination / "registry.sqlite")
    try:
        rows = connection.execute("SELECT id, url FROM repos WHERE status='ready'").fetchall()
        selected = [
            (repo_id, url)
            for repo_id, url in rows
            if urls is None or url.lower() in {value.lower() for value in urls}
        ]
        if not selected:
            raise ValueError("No completed repositories to snapshot")
        ids = [repo_id for repo_id, _ in selected]
        connection.execute(
            "DELETE FROM repos WHERE id NOT IN (" + ",".join("?" for _ in ids) + ")", ids
        )
        connection.commit()
    finally:
        connection.close()
    metadata = json.loads((source / "qdrant/meta.json").read_text(encoding="utf-8"))
    names = {f"askrepo_{repo_id}" for repo_id, _ in selected}
    metadata["collections"] = {
        name: value for name, value in metadata["collections"].items() if name in names
    }
    if set(metadata["collections"]) != names:
        raise ValueError("Ready snapshot is missing a Qdrant collection")
    metadata["aliases"] = {
        name: target for name, target in metadata.get("aliases", {}).items() if target in names
    }
    metadata["text_indexes"] = {
        name: value for name, value in metadata.get("text_indexes", {}).items() if name in names
    }
    target_qdrant = destination / "qdrant"
    target_qdrant.mkdir()
    for repo_id, _ in selected:
        if not re.fullmatch(r"[a-f0-9]{32}", repo_id):
            raise ValueError("Invalid stored repository identifier")
        directory = source / "repos" / repo_id
        if not directory.resolve().is_relative_to(source):
            raise ValueError("Unsafe stored repository directory")
        shutil.copytree(directory, destination / "repos" / repo_id)
        name = f"askrepo_{repo_id}"
        target_collection = target_qdrant / "collection" / name
        target_collection.mkdir(parents=True)
        backup_database(
            source / "qdrant/collection" / name / "storage.sqlite",
            target_collection / "storage.sqlite",
        )
    (target_qdrant / "meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    manifest = {
        "source": str(source),
        "created_at": datetime.now(UTC).isoformat(),
        "repositories": selected,
        "method": "SQLite online backup of ready immutable indexes; live source left unchanged",
    }
    (destination / "snapshot.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Settings().data_dir)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("data") / f"advanced-snapshot-{uuid4().hex}"
    manifest = snapshot_indexes(args.source, output)
    print(f"Snapshot: {output.resolve()}")
    print(f"Ready repositories: {len(manifest['repositories'])}")


if __name__ == "__main__":
    main()
