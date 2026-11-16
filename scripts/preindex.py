"""Explicit demo ingestion. Run from anywhere; nothing is indexed on API startup."""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos",
        nargs="+",
        choices=("Seekr", "CodeNest", "DPTrace"),
        default=["Seekr", "CodeNest", "DPTrace"],
    )
    parser.add_argument(
        "--force", action="store_true", help="Create new snapshots even when indexed"
    )
    args = parser.parse_args()
    os.chdir(ROOT / "backend")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import Settings
    from app.index.vectors import Vectors, get_embedder
    from app.jobs import Jobs
    from app.retrieve.hybrid import Retriever
    from app.storage import Storage

    settings = Settings()
    storage = Storage(settings.data_dir)
    retriever = Retriever(storage, Vectors(settings, get_embedder(settings)), settings)
    jobs = Jobs(settings, storage, retriever.build)
    try:
        pending = {}
        existing = {
            repo.repo_url: repo.repo_id
            for repo in storage.repos()
            if storage.metadata(repo.repo_id)["embedding_model"] == retriever.vectors.embedder.name
        }
        for repo in args.repos:
            url = f"https://github.com/ShlokMaharwal/{repo}"
            if url in existing and not args.force:
                print(f"{repo}: already ready ({existing[url]})", flush=True)
                continue
            job_id, repo_id = jobs.submit(url)
            pending[job_id] = (repo, repo_id)
        last = {}
        failed = []
        while pending:
            for job_id, (name, repo_id) in list(pending.items()):
                status = jobs.get(job_id)
                summary = (
                    status.status,
                    status.files_parsed,
                    status.chunks_created,
                    status.queued,
                )
                if last.get(job_id) != summary:
                    print(
                        f"{name}: {status.status} files={status.files_parsed} "
                        f"chunks={status.chunks_created} queued={status.queued}",
                        flush=True,
                    )
                    last[job_id] = summary
                if status.status in {"ready", "failed"}:
                    if status.status == "failed":
                        failed.append(name)
                        print(f"{name}: {status.error}", flush=True)
                    else:
                        print(f"{name}: ready repoId={repo_id}", flush=True)
                    del pending[job_id]
            if pending:
                time.sleep(0.25)
        if failed:
            raise SystemExit("Indexing failed: " + ", ".join(failed))
    finally:
        jobs.close()
        retriever.close()


if __name__ == "__main__":
    main()
