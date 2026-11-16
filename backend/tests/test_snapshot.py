import pytest

from app.config import Settings
from app.index.vectors import Vectors
from app.storage import Storage
from eval.snapshot import snapshot_indexes
from tests.fakes import FakeEmbedder
from tests.test_contract import client as client
from tests.test_contract import index_fixture


def test_online_snapshot_is_queryable_while_original_qdrant_remains_open(client, tmp_path):
    repo_id = index_fixture(client)
    source = client.app.state.storage.root
    before = client.app.state.retriever.vectors.search(repo_id, "redis frontier", 5)
    destination = tmp_path.parent / (tmp_path.name + "-snapshot")
    manifest = snapshot_indexes(source, destination)
    assert manifest["repositories"][0][0] == repo_id
    assert Storage(destination).file(repo_id, "frontier.py") == client.app.state.storage.file(
        repo_id, "frontier.py"
    )
    vectors = Vectors(Settings(_env_file=None, data_dir=destination), FakeEmbedder())
    try:
        copied = vectors.search(repo_id, "redis frontier", 5)
        assert [identifier for identifier, _ in copied] == [identifier for identifier, _ in before]
        assert [score for _, score in copied] == pytest.approx(
            [score for _, score in before], abs=1e-6
        )
        original = client.app.state.retriever.vectors.search(repo_id, "redis frontier", 5)
        assert [identifier for identifier, _ in original] == [
            identifier for identifier, _ in before
        ]
        assert [score for _, score in original] == pytest.approx(
            [score for _, score in before], abs=1e-6
        )
    finally:
        vectors.close()
