"""Append-only, content-addressed dispatch inputs on the 2.0 data volume."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def digest(payload: dict) -> str:
    return hashlib.sha256(encode(payload)).hexdigest()


def encode(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


class DispatchSnapshots:
    def __init__(self, root: Path | None = None):
        default = Path(__file__).resolve().parents[2] / "var" / "dispatch-inputs"
        self.root = Path(root or os.getenv("BANBOOS2_SNAPSHOT_DIR", str(default)))

    def put(self, payload: dict) -> str:
        snapshot_id = digest(payload)
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{snapshot_id}.json"
        try:
            with target.open("xb") as stream:
                stream.write(encode(payload))
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if target.read_bytes() != encode(payload):
                raise ValueError("输入快照已损坏") from None
        return snapshot_id

    def read(self, snapshot_id: str) -> dict:
        if len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise ValueError("无效的快照ID")
        payload = json.loads((self.root / f"{snapshot_id}.json").read_text(encoding="utf-8"))
        if digest(payload) != snapshot_id:
            raise ValueError("输入快照校验失败")
        return payload
