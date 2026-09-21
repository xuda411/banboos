"""Safe import preview and audit storage for isolated data onboarding."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date
from math import isfinite
from pathlib import Path
from uuid import uuid4

from packages.contracts.imports import (
    ImportCommitRequest,
    ImportCommitResult,
    ImportPreviewRequest,
    ImportPreviewResult,
)
from packages.infrastructure.database_fields import PRICE_FIELDS


def _encode(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class ImportService:
    def __init__(self, root: str | Path | None = None):
        base = Path(root or os.getenv("BANBOOS2_IMPORT_DIR", "var/imports"))
        self.root = base
        self.previews = base / "previews"
        self.audit = base / "audit"

    def preview(self, request: ImportPreviewRequest) -> ImportPreviewResult:
        if request.market not in {"日前", "实时"}:
            raise ValueError("market 只能是 日前 或 实时")
        accepted: list[dict] = []
        errors: list[str] = []
        for index, row in enumerate(request.rows, start=1):
            normalized, error = self._normalize_row(row, request.market, index)
            if error:
                errors.append(error)
            else:
                accepted.append(normalized)
        payload = {"kind": "price-import-preview", "source_name": request.source_name,
                   "market": request.market, "rows": accepted, "errors": errors,
                   "row_count": len(request.rows)}
        preview_id = hashlib.sha256(_encode(payload)).hexdigest()
        self._atomic_write(self.previews / f"{preview_id}.json", payload)
        status = "ready" if not errors else "rejected"
        return ImportPreviewResult(preview_id=preview_id, source_name=request.source_name,
                                   market=request.market, status=status,
                                   row_count=len(request.rows), accepted_count=len(accepted),
                                   rejected_count=len(errors), errors=errors[:100])

    def commit(self, request: ImportCommitRequest) -> ImportCommitResult:
        if not request.confirm:
            raise ValueError("必须明确确认导入预览后才能提交")
        path = self.previews / f"{request.preview_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
            raise ValueError("导入预览不存在或已损坏") from error
        if payload.get("kind") != "price-import-preview":
            raise ValueError("预览类型不受支持")
        if payload.get("errors"):
            raise ValueError("预览存在字段或数据错误，修正后重新预览")
        audit_id = uuid4().hex
        event = {"audit_id": audit_id, "action": "import-commit", "preview_id": request.preview_id,
                 "source_name": payload.get("source_name"), "market": payload.get("market"),
                 "accepted_count": len(payload.get("rows") or []), "applied": False,
                 "control_mode": "disabled"}
        self._atomic_write(self.audit / f"{audit_id}.json", event)
        return ImportCommitResult(preview_id=request.preview_id, audit_id=audit_id,
                                  status="validated-only", applied=False,
                                  accepted_count=event["accepted_count"])

    def audit_rows(self, limit: int = 100) -> list[dict]:
        if limit < 1 or limit > 500:
            raise ValueError("limit 必须在 1 至 500 之间")
        if not self.audit.exists():
            return []
        rows = []
        for path in sorted(self.audit.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return rows

    @staticmethod
    def _normalize_row(row: dict, market: str, index: int) -> tuple[dict | None, str | None]:
        try:
            node_id = int(row.get("node_id"))
            run_date = date.fromisoformat(str(row.get("run_date"))[:10]).isoformat()
            row_market = str(row.get("market") or market)
            if node_id <= 0 or row_market != market:
                raise ValueError("节点或市场不匹配")
            values = row.get("prices")
            if values is None:
                values = [row.get(field) for field in PRICE_FIELDS]
            if not isinstance(values, list) or len(values) != 96:
                raise ValueError("必须提供 96 个 15 分钟电价点")
            prices = [float(value) for value in values]
            if not all(isfinite(value) for value in prices):
                raise ValueError("电价不能包含空值、NaN 或无穷值")
            return {"node_id": node_id, "run_date": run_date, "market": market,
                    "prices": prices, "source_mode": "import-preview"}, None
        except (TypeError, ValueError, OverflowError) as error:
            return None, f"第 {index} 行：{error}"

    @staticmethod
    def _atomic_write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_encode(payload))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
