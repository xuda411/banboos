from pathlib import Path

from fastapi.testclient import TestClient

from packages.application.price_conflict_review import PriceConflictReviewStore
from packages.application.readonly_service import ReadonlyService


def test_real_staging_conflict_review_contract(tmp_path, monkeypatch):
    from apps.api import main

    staging = Path(r"E:\Banboos2.0\var\migrations\legacy-full-20260923.sqlite3")
    cleaning = Path(r"E:\Banboos2.0\var\data-quality\legacy-price-clean-20261003.sqlite3")
    if not staging.is_file() or not cleaning.is_file():
        return
    monkeypatch.setattr(main, "readonly_service", ReadonlyService(legacy_db=cleaning, staging_db=staging))
    monkeypatch.setattr(main, "price_conflict_review_store", PriceConflictReviewStore(tmp_path / "review.sqlite3"))
    client = TestClient(main.app)
    response = client.get("/api/v1/quality/conflicts", params={"market": "实时", "limit": 100})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 22
    source_row_id = rows[0]["source_row_id"]
    detail = client.get(f"/api/v1/quality/conflicts/{source_row_id}")
    assert detail.status_code == 200
    assert detail.json()["evidence_id"] == rows[0]["evidence_id"]
    payload = {"action": "defer", "actor": "dev-user", "note": "等待业务复核",
               "evidence_id": rows[0]["evidence_id"], "expected_revision": 0,
               "idempotency_key": "contract-review-001"}
    reviewed = client.post(f"/api/v1/quality/conflicts/{source_row_id}/review", json=payload)
    assert reviewed.status_code == 200 and reviewed.json()["review_status"] == "deferred"
    assert client.post(f"/api/v1/quality/conflicts/{source_row_id}/review", json=payload).status_code == 200
    stale = {**payload, "idempotency_key": "contract-review-002"}
    assert client.post(f"/api/v1/quality/conflicts/{source_row_id}/review", json=stale).status_code == 409
    assert client.post(f"/api/v1/quality/conflicts/{source_row_id}/review", json={**payload, "note": ""}).status_code == 422
    assert client.get("/api/v1/quality/duplicate-audit", params={"limit": 2}).status_code == 200


def test_conflict_write_roles_and_apply_intent_never_apply(tmp_path, monkeypatch):
    from apps.api import main

    staging = Path(r"E:\Banboos2.0\var\migrations\legacy-full-20260923.sqlite3")
    cleaning = Path(r"E:\Banboos2.0\var\data-quality\legacy-price-clean-20261003.sqlite3")
    if not staging.is_file() or not cleaning.is_file():
        return
    monkeypatch.setattr(main, "readonly_service", ReadonlyService(legacy_db=cleaning, staging_db=staging))
    monkeypatch.setattr(main, "price_conflict_review_store", PriceConflictReviewStore(tmp_path / "review.sqlite3"))
    monkeypatch.setenv("BANBOOS2_API_TOKEN", "t" * 32)
    baseline = [(p.stat().st_size, p.stat().st_mtime_ns) for p in (staging, cleaning)]
    headers = {"X-API-Key": "t" * 32}
    client = TestClient(main.app)
    row = client.get("/api/v1/quality/conflicts", params={"market": "实时", "limit": 1}, headers=headers).json()[0]
    endpoint = f"/api/v1/quality/conflicts/{row['source_row_id']}"
    payload = {"action": "confirm_canonical", "actor": "token-owner", "note": "业务确认来源",
               "evidence_id": row["evidence_id"], "expected_revision": 0,
               "idempotency_key": "role-review-001"}
    monkeypatch.setenv("BANBOOS2_TOKEN_ROLE", "finance_analyst")
    assert client.post(endpoint + "/review", json=payload, headers=headers).status_code == 403
    monkeypatch.setenv("BANBOOS2_TOKEN_ROLE", "auditor")
    assert client.get(endpoint, headers=headers).status_code == 200
    assert client.post(endpoint + "/review", json=payload, headers=headers).status_code == 403
    monkeypatch.setenv("BANBOOS2_TOKEN_ROLE", "unknown-role")
    assert client.get(endpoint, headers=headers).status_code == 403
    monkeypatch.setenv("BANBOOS2_TOKEN_ROLE", "platform_admin")
    monkeypatch.setenv("BANBOOS2_TENANT_ID", "other-tenant")
    assert client.get(endpoint, headers=headers).status_code == 403
    assert client.post(endpoint + "/review", json=payload, headers=headers).status_code == 403
    monkeypatch.setenv("BANBOOS2_TENANT_ID", "staging-tenant")
    assert client.get(endpoint, headers=headers).status_code == 200
    assert client.post(endpoint + "/review", json={**payload, "actor": "forged"}, headers=headers).status_code == 403
    monkeypatch.setenv("BANBOOS2_TOKEN_ROLE", "operations_analyst")
    reviewed = client.post(endpoint + "/review", json=payload, headers=headers)
    assert reviewed.status_code == 200 and reviewed.json()["review_status"] == "approved"
    apply_payload = {"evidence_id": row["evidence_id"], "expected_revision": 1,
                     "note": "生成待应用审计记录", "idempotency_key": "role-apply-001"}
    applied = client.post(endpoint + "/apply", json=apply_payload, headers=headers)
    assert applied.status_code == 200
    assert applied.json()["apply_status"] == "pending_apply" and applied.json()["applied"] is False
    assert client.post(endpoint + "/apply", json=apply_payload, headers=headers).json()["intent_id"] == applied.json()["intent_id"]
    assert client.post(endpoint + "/review", json=payload).status_code == 401
    assert baseline == [(p.stat().st_size, p.stat().st_mtime_ns) for p in (staging, cleaning)]
    monkeypatch.delenv("BANBOOS2_API_TOKEN")
