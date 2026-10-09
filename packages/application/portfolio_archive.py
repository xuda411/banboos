"""Verified local archive packages for reproducible portfolio results."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from packages.application.portfolio_dashboard import build_portfolio_dashboard
from packages.contracts.readonly import RunStatus
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots
from packages.infrastructure.object_store import LocalObjectStore


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")


def create_portfolio_archive(run: RunStatus, root: Path | None = None) -> tuple[Path, str]:
    dashboard = build_portfolio_dashboard(run)
    archive_root = Path(root or os.getenv("BANBOOS2_ARCHIVE_DIR", "var/archives"))
    archive_root.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, bytes] = {
        "portfolio-result.json": _json_bytes({"run": run.model_dump(mode="json"), "dashboard": dashboard}),
        "dashboard.json": _json_bytes(dashboard),
        "README.txt": ("Banboos 2.0 组合结果归档\n"
                        "本包保存任务参数、结果、候选来源和校验清单；历史套利估算不等于财务净现金流。\n").encode(),
    }
    snapshot_id = dashboard["candidate_source"].get("snapshot_id")
    if snapshot_id:
        snapshot = DispatchSnapshots().read(str(snapshot_id))
        payloads["candidate-snapshot.json"] = _json_bytes(snapshot)
    manifest = {
        "format": "banboos-portfolio-archive-v1",
        "run_id": run.run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(payloads.items())},
    }
    payloads["manifest.json"] = _json_bytes(manifest)
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(payloads.items()):
            archive.writestr(name, content)
    content = stream.getvalue()
    target = LocalObjectStore(archive_root).put(f"portfolio-{run.run_id}.zip", content).path
    return target, hashlib.sha256(content).hexdigest()
