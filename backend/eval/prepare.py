import argparse
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.ingest.clone import clone_repository
from app.jobs import cleanup_clone

DEMO_REPOS = ("Seekr", "CodeNest", "DPTrace")


def main():
    parser = argparse.ArgumentParser(description="Fetch bounded public evaluation source snapshots")
    parser.add_argument("--output", type=Path, default=Path("data/eval-sources"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name in DEMO_REPOS:
        destination = args.output / name
        if destination.exists():
            print(f"{name}: using existing snapshot at {destination}")
            continue
        staging = args.output / f"snapshot-{uuid4().hex}"
        try:
            revision = clone_repository(
                f"https://github.com/ShlokMaharwal/{name}", staging, Settings(_env_file=None)
            )
            if not destination.resolve().is_relative_to(args.output.resolve()):
                raise ValueError("Unsafe evaluation snapshot path")
            staging.rename(destination)
        finally:
            cleanup_clone(staging, args.output)
        print(f"{name}: {revision}")


if __name__ == "__main__":
    main()
