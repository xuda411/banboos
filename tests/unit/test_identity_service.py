import pytest

from packages.application.identity_service import (
    ChallengeThrottle,
    IdentityInputError,
    identity_hash,
    mask_identifier,
    normalize_identifier,
)


def test_identity_normalization_and_masking():
    phone = normalize_identifier("phone", "+86 138-0013-8000")
    email = normalize_identifier("email", " User@Example.COM ")
    assert phone == "13800138000"
    assert email == "user@example.com"
    assert mask_identifier("phone", phone) == "138****8000"
    assert mask_identifier("email", email) == "u***@example.com"


def test_identity_hash_requires_secret_and_is_provider_scoped():
    with pytest.raises(ValueError):
        identity_hash("phone", "13800138000", secret="short")
    secret = "s" * 32
    assert identity_hash("phone", "13800138000", secret=secret) != identity_hash(
        "email", "13800138000", secret=secret
    )
    assert identity_hash("phone", "13800138000", secret=secret) == identity_hash(
        "phone", "13800138000", secret=secret
    )


def test_challenge_throttle_enforces_cooldown_and_window():
    now = [100.0]
    throttle = ChallengeThrottle(max_attempts=2, window_seconds=30, cooldown_seconds=5,
                                 clock=lambda: now[0])
    throttle.record("phone:abc")
    decision = throttle.check("phone:abc")
    assert not decision.allowed and decision.retry_after_seconds == 5
    now[0] += 5
    throttle.record("phone:abc")
    now[0] += 5
    decision = throttle.check("phone:abc")
    assert not decision.allowed and decision.retry_after_seconds == 20


@pytest.mark.parametrize("provider, value", [("phone", "123"), ("email", "bad"), ("wechat", " ")])
def test_invalid_identity_is_rejected(provider, value):
    with pytest.raises(IdentityInputError):
        normalize_identifier(provider, value)
