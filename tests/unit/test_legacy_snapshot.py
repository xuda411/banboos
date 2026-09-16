import json
import sqlite3

import pytest

from packages.application.legacy_snapshot import LegacySnapshotError, snapshot_legacy_database


def test_snapshot_creates_hash_manifest_and_readonly_copy(tmp_path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES (1, '演示节点')")
    manifest_path = snapshot_legacy_database(source, tmp_path / "snapshots")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = manifest_path.parent / source.name
    assert manifest["sqlite_integrity_check"] == "ok"
    assert manifest["tables"] == {"nodes": 1}
    assert manifest["size_bytes"] == snapshot.stat().st_size
    assert len(manifest["sha256"]) == 64
    with pytest.raises(sqlite3.OperationalError), sqlite3.connect(snapshot) as connection:
        connection.execute("INSERT INTO nodes VALUES (2, '禁止写入')")


def test_snapshot_removes_partial_output_on_integrity_failure(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    source.write_bytes(b"not sqlite")
    with pytest.raises(LegacySnapshotError):
        snapshot_legacy_database(source, tmp_path / "snapshots")
    assert list((tmp_path / "snapshots").iterdir()) == []
