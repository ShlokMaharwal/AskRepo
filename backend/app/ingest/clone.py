"""Clone public GitHub repositories without credentials, redirects, or repository hooks."""

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from app.config import Settings
from app.models import IndexRequest

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "vendor",
    ".venv",
    "venv",
    ".next",
    ".nuxt",
    ".output",
    "__pycache__",
    ".cache",
    "coverage",
    "target",
}
SKIP_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "poetry.lock",
    "uv.lock",
    "Cargo.lock",
    "Pipfile.lock",
    ".env",
}
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".mp4",
    ".mp3",
    ".wav",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".exe",
    ".dll",
    ".so",
    ".pyc",
    ".class",
    ".jar",
    ".db",
    ".sqlite",
    ".bin",
    ".map",
    ".wasm",
    ".lock",
    ".pem",
    ".key",
    ".p12",
}


class IngestError(ValueError):
    pass


def repository_limits(settings):
    if settings.lite_mode:
        return min(settings.max_files, settings.lite_max_files), min(
            settings.max_repo_bytes, settings.lite_max_repo_bytes
        )
    return settings.max_files, settings.max_repo_bytes


def limit_message(settings):
    if settings.lite_mode:
        files, size = repository_limits(settings)
        return (
            f"Repository exceeds lightweight hosting limits: at most {files} files "
            f"and {size / (1024 * 1024):g} MB. Try a smaller repository."
        )
    return "Repository exceeds the configured total file count or size limit"


def tree_entries(stream, settings):
    """Bound ls-tree output while reading, before allocating an entire remote tree listing."""
    pending = b""
    count = total = 0
    max_files, max_bytes = repository_limits(settings)
    while block := stream.read(8192):
        pending += block
        while b"\0" in pending:
            entry, pending = pending.split(b"\0", 1)
            if not entry:
                continue
            if len(entry) > 8192:
                raise IngestError("Repository contains an unsupported file path")
            metadata, _ = entry.split(b"\t", 1)
            mode, kind, _, length = metadata.split()
            count += 1
            if kind == b"blob" and mode != b"120000":
                total += int(length)
            if count > max_files or total > max_bytes:
                raise IngestError(limit_message(settings))
            yield entry
        if len(pending) > 8192:
            raise IngestError("Repository contains an unsupported file path")
    if pending:
        raise IngestError("Cannot read the repository tree")


def directory_bytes(path: Path) -> int:
    total = 0
    for directory, _, files in os.walk(path, followlinks=False):
        for filename in files:
            item = Path(directory) / filename
            if not item.is_symlink():
                try:
                    total += item.stat().st_size
                except FileNotFoundError:
                    pass
    return total


def clone_repository(url: str, destination: Path, settings: Settings) -> str:
    url = IndexRequest(repo_url=url).repo_url
    destination.mkdir(parents=True, exist_ok=False)
    # A fresh HOME and config isolation prevent inherited URL rewrites, credential helpers,
    # filters and hooks. git -c values alone cannot neutralize all inherited configuration.
    isolated_home = destination.parent / f"{destination.name}-git-home"
    isolated_home.mkdir()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ALLOW_PROTOCOL": "https",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "HOME": str(isolated_home),
            "XDG_CONFIG_HOME": str(isolated_home),
            "GCM_INTERACTIVE": "never",
        }
    )
    command = [
        "git",
        "-c",
        "http.followRedirects=false",
        "-c",
        "credential.helper=",
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "protocol.file.allow=never",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        "--no-checkout",
        "--",
        url + ".git",
        str(destination),
    ]
    try:
        # Do not capture unbounded stderr into memory. Failure text is intentionally generic
        # so inherited network/proxy configuration cannot leak into the API or logs.
        with subprocess.Popen(
            command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ) as process:
            started = time.monotonic()
            while process.poll() is None:
                if time.monotonic() - started > settings.clone_timeout_seconds:
                    process.kill()
                    raise IngestError("Cloning exceeded the configured time limit")
                if directory_bytes(destination) > settings.max_clone_bytes:
                    process.kill()
                    raise IngestError("Cloned repository exceeds the configured size limit")
                time.sleep(0.1)
            if process.returncode:
                raise IngestError(
                    "Cannot clone repository. It must be public and accessible on GitHub"
                )
        # Bound the checkout before materializing any tracked content (including .gitattributes).
        with subprocess.Popen(
            ["git", "-C", str(destination), "ls-tree", "-rlz", "HEAD"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as process:
            deadline = threading.Timer(30, process.kill)
            deadline.start()
            try:
                entries = list(tree_entries(process.stdout, settings))
                if process.wait():
                    raise IngestError("Cannot read the repository tree within its time limit")
            except Exception:
                process.kill()
                raise
            finally:
                deadline.cancel()
        subprocess.run(
            [
                "git",
                "-C",
                str(destination),
                "-c",
                "core.symlinks=false",
                "-c",
                "core.hooksPath=" + os.devnull,
                "checkout",
                "--force",
                "HEAD",
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=settings.clone_timeout_seconds,
        )
        revision = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        # Remove symlink entries even on Windows, where checkout may materialize them as text.
        for entry in entries:
            if entry.startswith(b"120000 "):
                path = destination / entry.split(b"\t", 1)[1].decode("utf-8", errors="replace")
                if path.is_symlink() or path.is_file():
                    path.unlink()
        return revision
    except (OSError, subprocess.SubprocessError) as error:
        raise IngestError("Git could not safely read the repository") from error
    finally:
        shutil.rmtree(isolated_home, ignore_errors=True)


def source_files(root: Path, settings: Settings) -> list[tuple[str, str]]:
    result = []
    total = count = 0
    max_files, max_bytes = repository_limits(settings)
    for directory, subdirs, files in os.walk(root, followlinks=False):
        subdirs[:] = sorted(
            name
            for name in subdirs
            if name not in SKIP_DIRS and not (Path(directory) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            count += 1
            size = path.stat().st_size
            total += size
            if count > max_files or total > max_bytes:
                raise IngestError(limit_message(settings))
            if (
                name in SKIP_NAMES
                or name.startswith(".env.")
                or path.suffix.lower() in SKIP_SUFFIXES
                or ".min." in name
                or size > settings.max_file_bytes
            ):
                continue
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                continue
            if not text.strip() or any(len(line) > 2000 for line in text.splitlines()):
                continue
            result.append((path.relative_to(root).as_posix(), text))
    return result
