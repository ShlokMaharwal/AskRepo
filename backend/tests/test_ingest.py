import threading

import pytest

from app.config import Settings
from app.ingest.chunker import chunk_file
from app.ingest.clone import IngestError, source_files, tree_entries
from app.jobs import Jobs
from app.models import JobStatus
from app.storage import Storage, contained_path


def test_python_symbols_and_exact_ranges():
    source = (
        '"""Module docs."""\nimport os\n\nclass Worker:\n'
        "    def run(self):\n        return os.name\n\ndef start():\n    return Worker()\n"
    )
    chunks = chunk_file("repo", "app.py", source)
    method = next(chunk for chunk in chunks if chunk.symbol_name == "run")
    assert (method.start_line, method.end_line, method.parent_symbol) == (5, 6, "Worker")
    assert "app.py | python | Worker.run" in method.text
    assert any(chunk.kind == "class_header" for chunk in chunks)
    assert any(chunk.kind == "imports" and "Module docs" in chunk.code for chunk in chunks)
    for chunk in chunks:
        assert chunk.code == "\n".join(source.splitlines()[chunk.start_line - 1 : chunk.end_line])


@pytest.mark.parametrize(
    ("path", "source", "name"),
    [
        ("main.js", "export function crawl(url) { return url; }", "crawl"),
        ("main.ts", "export const rank = (score: number) => score + 1;", "rank"),
        ("Main.java", "class Main { public int run() { return 1; } }", "run"),
        ("main.c", "int run(void) { return 1; }", "run"),
        ("main.cpp", "class Main { public: int run() { return 1; } };", "run"),
    ],
)
def test_supported_languages(path, source, name):
    assert any(chunk.symbol_name == name for chunk in chunk_file("repo", path, source))


def test_fixed_fallback_markdown_and_oversized_chunks():
    source = "\n".join(f"line {index}" for index in range(130))
    chunks = chunk_file("repo", "notes.txt", source)
    assert [(item.start_line, item.end_line) for item in chunks] == [(1, 60), (51, 110), (101, 130)]
    assert len(chunk_file("repo", "main.py", source, "fixed")) == 3
    headings = chunk_file("repo", "README.md", "# Intro\nhello\n## Setup\ninstall\n")
    assert [item.symbol_name for item in headings] == ["Intro", "Setup"]
    source = "def large():\n" + "\n".join("    value = '" + "a" * 90 + "'" for _ in range(100))
    chunks = chunk_file("repo", "large.py", source, max_chars=1000)
    assert len(chunks) > 2
    assert all(len(chunk.code) <= 1000 for chunk in chunks)
    assert len({chunk.id for chunk in chunks}) == len(chunks)


def test_filtering_and_limits(tmp_path):
    (tmp_path / "app.py").write_text("def run(): return 1", encoding="utf-8")
    for filename, content in [
        (".env", "SECRET=private"),
        ("a.min.js", "minified"),
        ("image.png", "image"),
        ("package-lock.json", "{}"),
    ]:
        (tmp_path / filename).write_text(content)
    (tmp_path / "binary.txt").write_bytes(b"\0binary")
    (tmp_path / "large.txt").write_text("a" * 400)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignore.js").write_text("ignore")
    settings = Settings(_env_file=None, max_file_bytes=300)
    assert [path for path, _ in source_files(tmp_path, settings)] == ["app.py"]
    with pytest.raises(IngestError, match="file count"):
        source_files(tmp_path, Settings(_env_file=None, max_files=1))
    with pytest.raises(IngestError, match="size limit"):
        source_files(tmp_path, Settings(_env_file=None, max_repo_bytes=10))


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "a/../../secret",
        "/etc/passwd",
        "C:/secret",
        "C:secret",
        "a\\..\\secret",
        "a\x00b",
        "a/./b",
        "//host/file",
    ],
)
def test_path_traversal(tmp_path, path):
    with pytest.raises(ValueError):
        contained_path(tmp_path, path)


def test_symlink_escape_if_supported(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    try:
        (root / "link").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks require additional Windows privileges")
    with pytest.raises(ValueError):
        contained_path(root, "link/secret")


def test_ingestion_storage_queue_and_clone_cleanup(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    storage = Storage(tmp_path)

    def clone(url, path, settings):
        path.mkdir()
        (path / "app.py").write_text("def run():\n    return 1\n")
        return "fixture-revision"

    jobs = Jobs(settings, storage, cloner=clone)
    job_id, repo_id = jobs.submit("https://github.com/owner/repo")
    jobs.close()
    assert jobs.get(job_id).status == "ready"
    assert storage.repos()[0].repo_id == repo_id
    assert storage.file(repo_id, "app.py")[0].startswith("def run")
    assert storage.metadata(repo_id)["revision"] == "fixture-revision"
    assert not (tmp_path / "tmp" / repo_id).exists()
    assert Storage(tmp_path).chunks(repo_id)[0].symbol_name == "run"


def test_queue_is_bounded_and_failures_are_terminal(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def clone(url, path, settings):
        entered.set()
        release.wait(timeout=5)
        raise IngestError("Cannot clone repository")

    jobs = Jobs(Settings(_env_file=None, max_queued_jobs=1), Storage(tmp_path), cloner=clone)
    first, _ = jobs.submit("https://github.com/owner/repo")
    assert entered.wait(timeout=2)
    second, _ = jobs.submit("https://github.com/owner/other")
    assert jobs.get(second).queued
    try:
        with pytest.raises(OverflowError):
            jobs.submit("https://github.com/owner/third")
    finally:
        release.set()
        jobs.close()
    assert jobs.get(first).status == "failed"
    assert jobs.get(second).status == "failed"


def test_invalid_strategy():
    with pytest.raises(ValueError):
        chunk_file("repo", "a.py", "pass", "invalid")
    assert JobStatus(status="cloning").queued is False


def test_nested_functions_are_individually_searchable():
    source = "function outer() { function inner() { return 1; } return inner(); }"
    names = {chunk.symbol_name for chunk in chunk_file("repo", "nested.js", source)}
    assert {"outer", "inner"} <= names


def test_tree_listing_limits_are_enforced_before_full_output_is_read():
    from io import BytesIO

    raw = b"100644 blob abc 12\tfile.py\0" * 20
    assert len(list(tree_entries(BytesIO(raw), Settings(_env_file=None)))) == 20
    with pytest.raises(IngestError, match="file count"):
        list(tree_entries(BytesIO(raw), Settings(_env_file=None, max_files=1)))
    with pytest.raises(IngestError, match="size limit"):
        list(tree_entries(BytesIO(raw), Settings(_env_file=None, max_repo_bytes=10)))
