from packages.application.deployment_preflight import evaluate_preflight


def test_development_preflight_keeps_local_defaults_available():
    report = evaluate_preflight({"BANBOOS2_ENV": "development"}, template_available=True)

    assert report["status"] == "staging-ready"
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["postgres"]["status"] == "pass"
    assert checks["redis"]["status"] == "pass"
    assert checks["tenant_isolation"]["status"] == "warn"


def test_production_preflight_blocks_without_identity_and_strict_tenant_boundary():
    report = evaluate_preflight({
        "BANBOOS2_ENV": "production",
        "BANBOOS2_DATABASE_URL": "postgresql+asyncpg://user:pass@db/banboos2",
        "BANBOOS2_REDIS_URL": "redis://redis:6379/0",
        "BANBOOS2_AUTH_MODE": "identity",
        "BANBOOS2_CORS_ORIGINS": "https://banboos.example.com",
        "BANBOOS2_CONTROL_MODE": "disabled",
        "BANBOOS2_TENANT_ENFORCEMENT": "preview",
    }, template_available=True)

    assert report["status"] == "blocked"
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["identity_service"]["status"] == "fail"
    assert checks["tenant_isolation"]["status"] == "fail"


def test_production_preflight_passes_configuration_boundary():
    report = evaluate_preflight({
        "BANBOOS2_ENV": "production",
        "BANBOOS2_DATABASE_URL": "postgresql+asyncpg://user:pass@db/banboos2",
        "BANBOOS2_REDIS_URL": "redis://redis:6379/0",
        "BANBOOS2_AUTH_MODE": "identity",
        "BANBOOS2_CORS_ORIGINS": "https://banboos.example.com",
        "BANBOOS2_SMS_PROVIDER": "sms-provider",
        "BANBOOS2_EMAIL_PROVIDER": "email-provider",
        "BANBOOS2_WECHAT_CLIENT_ID": "wechat-client",
        "BANBOOS2_IDENTITY_HASH_SECRET": "h" * 32,
        "BANBOOS2_CONTROL_MODE": "disabled",
        "BANBOOS2_TENANT_ENFORCEMENT": "strict",
        "BANBOOS2_FINANCIAL_RELEASE_GATE": "RELEASE_READY",
    }, template_available=True)

    assert report["status"] == "staging-ready"
    assert all(item["status"] == "pass" for item in report["checks"])


def test_production_preflight_blocks_when_financial_release_gate_is_pending():
    report = evaluate_preflight({
        "BANBOOS2_ENV": "production",
        "BANBOOS2_DATABASE_URL": "postgresql+asyncpg://user:pass@db/banboos2",
        "BANBOOS2_REDIS_URL": "redis://redis:6379/0",
        "BANBOOS2_AUTH_MODE": "identity",
        "BANBOOS2_CORS_ORIGINS": "https://banboos.example.com",
        "BANBOOS2_SMS_PROVIDER": "sms-provider",
        "BANBOOS2_EMAIL_PROVIDER": "email-provider",
        "BANBOOS2_WECHAT_CLIENT_ID": "wechat-client",
        "BANBOOS2_IDENTITY_HASH_SECRET": "h" * 32,
        "BANBOOS2_CONTROL_MODE": "disabled",
        "BANBOOS2_TENANT_ENFORCEMENT": "strict",
        "BANBOOS2_FINANCIAL_RELEASE_GATE": "PENDING_CROSS_ENGINE",
    }, template_available=True)

    assert report["status"] == "blocked"
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["financial_release_gate"]["status"] == "fail"
