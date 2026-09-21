import pytest

from packages.application.import_service import ImportService
from packages.contracts.imports import ImportCommitRequest, ImportPreviewRequest


def _row(**overrides):
    row = {"node_id": 786, "run_date": "2026-01-01", "market": "实时", "prices": list(range(96))}
    row.update(overrides)
    return row


def test_import_preview_rejects_quality_labels_and_wrong_shape(tmp_path):
    service = ImportService(tmp_path)
    result = service.preview(ImportPreviewRequest(source_name="x.csv", market="实时",
                                                   rows=[_row(), _row(market="OK"), _row(prices=[1, 2])]))
    assert result.status == "rejected"
    assert result.accepted_count == 1
    assert result.rejected_count == 2
    with pytest.raises(ValueError, match="预览存在"):
        service.commit(ImportCommitRequest(preview_id=result.preview_id, confirm=True))


def test_import_commit_is_atomic_audited_and_does_not_apply(tmp_path):
    service = ImportService(tmp_path)
    preview = service.preview(ImportPreviewRequest(source_name="x.csv", market="实时", rows=[_row()]))
    result = service.commit(ImportCommitRequest(preview_id=preview.preview_id, confirm=True))
    assert result.status == "validated-only"
    assert result.applied is False
    assert service.audit_rows()[0]["preview_id"] == preview.preview_id
