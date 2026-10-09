"""Small object-store port with an E: drive local implementation.

The application only depends on this interface. A PostgreSQL/S3/OSS adapter
can be added later without changing archive or result contracts.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredObject:
    key: str
    path: Path
    size: int


class LocalObjectStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.getenv("BANBOOS2_ARCHIVE_DIR", "var/archives"))

    def put(self, key: str, content: bytes) -> StoredObject:
        if not key or Path(key).name != key or key in {".", ".."}:
            raise ValueError("对象 key 必须是单层文件名")
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / key
        temporary = target.with_suffix(target.suffix + ".partial")
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        return StoredObject(key=key, path=target, size=len(content))

    def get(self, key: str) -> bytes:
        if not key or Path(key).name != key:
            raise ValueError("对象 key 必须是单层文件名")
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).is_file()
