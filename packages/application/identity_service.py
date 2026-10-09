"""Provider-neutral identity primitives for the production login milestone.

This module intentionally does not send messages or create sessions.  It keeps
the sensitive parts that every SMS, email and WeChat adapter must share in one
place: canonical identifiers, keyed hashes, masking and replay/rate-limit
decisions.  Durable challenge/session writes belong in the PostgreSQL adapter.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

_PHONE = re.compile(r"^1[3-9]\d{9}$")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_WECHAT = re.compile(r"^[^\x00-\x1f\x7f]{3,160}$")


class IdentityInputError(ValueError):
    """The provider identifier is malformed or cannot be canonicalized."""


def normalize_identifier(provider: str, identifier: str) -> str:
    """Return a canonical provider identifier without retaining the raw value."""
    value = str(identifier or "").strip()
    if provider == "phone":
        compact = re.sub(r"[\s-]", "", value)
        compact = compact.removeprefix("+86")
        if not _PHONE.fullmatch(compact):
            raise IdentityInputError("手机号格式不正确")
        return compact
    if provider == "email":
        compact = value.casefold()
        if len(compact) > 160 or not _EMAIL.fullmatch(compact):
            raise IdentityInputError("邮箱格式不正确")
        return compact
    if provider == "wechat":
        if not _WECHAT.fullmatch(value):
            raise IdentityInputError("微信身份标识格式不正确")
        return value
    raise IdentityInputError("不支持的登录方式")


def identity_hash(provider: str, normalized_identifier: str, *, secret: str | None = None) -> str:
    """Create a keyed hash suitable for ``user_identities.subject_hash``."""
    key = secret or os.getenv("BANBOOS2_IDENTITY_HASH_SECRET", "")
    if len(key) < 32:
        raise ValueError("BANBOOS2_IDENTITY_HASH_SECRET 至少需要 32 个字符")
    message = f"{provider}:{normalized_identifier}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def mask_identifier(provider: str, normalized_identifier: str) -> str:
    """Return a UI-safe identifier; raw phone/email values never enter logs."""
    if provider == "phone":
        return f"{normalized_identifier[:3]}****{normalized_identifier[-4:]}"
    if provider == "email":
        local, domain = normalized_identifier.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if len(normalized_identifier) <= 6:
        return "***"
    return f"{normalized_identifier[:3]}***{normalized_identifier[-2:]}"


@dataclass(frozen=True)
class ThrottleDecision:
    allowed: bool
    retry_after_seconds: int = 0


class ChallengeThrottle:
    """Small deterministic throttle used by adapters before durable persistence.

    A production deployment should back the same policy with Redis so all API
    workers share counters.  The class remains dependency-free for contract and
    adapter tests.
    """

    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 600,
                 cooldown_seconds: int = 60, clock: Callable[[], float] | None = None):
        if min(max_attempts, window_seconds, cooldown_seconds) <= 0:
            raise ValueError("频控参数必须为正数")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock or time.time
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> ThrottleDecision:
        now = self._clock()
        events = self._events[key]
        while events and now - events[0] >= self.window_seconds:
            events.popleft()
        if events and now - events[-1] < self.cooldown_seconds:
            return ThrottleDecision(False, max(1, int(self.cooldown_seconds - (now - events[-1]))))
        if len(events) >= self.max_attempts:
            return ThrottleDecision(False, max(1, int(self.window_seconds - (now - events[0]))))
        return ThrottleDecision(True)

    def record(self, key: str) -> None:
        decision = self.check(key)
        if not decision.allowed:
            raise IdentityInputError(f"验证码请求过于频繁，请 {decision.retry_after_seconds} 秒后重试")
        self._events[key].append(self._clock())
