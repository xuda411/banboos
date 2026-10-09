from pathlib import Path
from uuid import uuid4

import pytest

from packages.application.portfolio_review import PortfolioReviewStore
from packages.infrastructure.object_store import LocalObjectStore


def test_portfolio_review_requires_ordered_transitions():
    root = Path("E:/Banboos2.0/var/tests") / f"review-{uuid4().hex}.sqlite"
    store = PortfolioReviewStore(root)
    assert store.get("run-1").status == "draft"
    assert store.transition("run-1", "submit", "分析员", "已检查输入").status == "pending"
    with pytest.raises(ValueError, match="当前状态"):
        store.transition("run-1", "archive", "分析员")
    approved = store.transition("run-1", "approve", "复核员", "通过")
    assert approved.status == "approved"
    archived = store.transition("run-1", "archive", "归档员")
    assert archived.status == "archived"
    assert len(archived.history) == 3


def test_local_object_store_writes_single_level_key():
    root = Path("E:/Banboos2.0/var/tests") / f"objects-{uuid4().hex}"
    store = LocalObjectStore(root)
    item = store.put("result.zip", b"PK-test")
    assert item.path == root / "result.zip"
    assert store.exists("result.zip")
    assert store.get("result.zip") == b"PK-test"
    with pytest.raises(ValueError):
        store.put("nested/result.zip", b"bad")
