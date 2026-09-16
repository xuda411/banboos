"""Create immutable, verifiable snapshots of a Banboos 1.6.6 SQLite file."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class LegacySnapshotError(RuntimeError):
    """Raised when a legacy snapshot cannot be verified."""


def snapshot_legacy_database(
    source: str | Path,
    destination_root: str | Path = "var/legacy-snapshots",
    migration_version: str = "legacy-snapshot-v1",
) -> Path:
    """Copy a legacy SQLite database and return its JSON manifest path.

    The source is only opened for metadata and is never written. A temporary
    destination is used so an interrupted copy cannot be mistaken for a valid
    snapshot. The copied database is checked with SQLite integrity_check.
    """
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise LegacySnapshotError(f"源数据库不存在：{source_path}")
    if source_path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise LegacySnapshotError("源文件必须是 SQLite 数据库（.db/.sqlite/.sqlite3）")

    created = datetime.now(UTC)
    stamp = created.strftime("%Y%m%d-%H%M%S")
    root = Path(destination_root).expanduser().resolve()
    snapshot_dir = root / f"{stamp}-{uuid4().hex[:8]}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    temporary = snapshot_dir / f"{source_path.name}.partial"
    copied = snapshot_dir / source_path.name
    try:
        shutil.copy2(source_path, temporary)
        temporary.replace(copied)
        digest = _sha256(copied)
        integrity, tables = _sqlite_metadata(copied)
        if integrity != "ok":
            raise LegacySnapshotError(f"快照完整性检查失败：{integrity}")
        manifest = {
            "manifest_version": "1",
            "migration_version": migration_version,
            "created_at_utc": created.isoformat(),
            "source_path": str(source_path),
            "snapshot_path": str(copied),
            "sha256": digest,
            "size_bytes": copied.stat().st_size,
            "sqlite_integrity_check": integrity,
            "tables": tables,
            "read_only_source": True,
        }
        manifest_path = snapshot_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Read-only is an additional guard; the reader still uses mode=ro.
        os.chmod(copied, 0o444)
        return manifest_path
    except Exception:
        for candidate in (temporary, copied):
            if candidate.exists():
                try:
                    os.chmod(candidate, 0o666)
                except OSError:
                    pass
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_metadata(path: Path) -> tuple[str, dict[str, int]]:
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        tables = {}
        for name in names:
            escaped = name.replace('"', '""')
            tables[name] = int(connection.execute(
                f'SELECT COUNT(*) FROM "{escaped}"'
            ).fetchone()[0])
        return integrity, tables
    except sqlite3.Error as error:
        raise LegacySnapshotError(f"无法读取 SQLite 快照：{error}") from error
    finally:
        if connection is not None:
            connection.close()
