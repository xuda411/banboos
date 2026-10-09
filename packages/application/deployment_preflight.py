"""Configuration-only deployment preflight for Banboos 2.0.

The preflight deliberately does not pretend to verify external credentials or
hardware.  It verifies that the deployment declares the required boundaries so
that a production process cannot start with the development fallback enabled.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _env(config: Mapping[str, str] | None, key: str, default: str = "") -> str:
    if config is not None and key in config:
        return str(config[key]).strip()
    return os.getenv(key, default).strip()


def evaluate_preflight(
    config: Mapping[str, str] | None = None,
    *,
    template_available: bool | None = None,
) -> dict[str, object]:
    """Evaluate deployment declarations without making network calls.

    ``template_available`` is injectable for tests and callers that already
    resolved the template path.  External provider credentials remain a
    release dependency; their presence only proves that configuration exists.
    """
    environment = _env(config, "BANBOOS2_ENV", "development").lower()
    production = environment in {"prod", "production"}
    database_url = _env(config, "BANBOOS2_DATABASE_URL")
    redis_url = _env(config, "BANBOOS2_REDIS_URL")
    cors_origins = [item.strip() for item in _env(config, "BANBOOS2_CORS_ORIGINS").split(",") if item.strip()]
    auth_mode = _env(config, "BANBOOS2_AUTH_MODE", "development-open" if not production else "identity").lower()
    tenant_mode = _env(config, "BANBOOS2_TENANT_ENFORCEMENT", "preview")
    control_mode = _env(config, "BANBOOS2_CONTROL_MODE", "disabled").lower()
    financial_gate = _env(config, "BANBOOS2_FINANCIAL_RELEASE_GATE").upper()
    identity_hash_secret = _env(config, "BANBOOS2_IDENTITY_HASH_SECRET")

    if template_available is None:
        from packages.application.financial_template_xlsm import financial_template_path

        template_available = financial_template_path() is not None

    identity_keys = ("BANBOOS2_SMS_PROVIDER", "BANBOOS2_EMAIL_PROVIDER", "BANBOOS2_WECHAT_CLIENT_ID")
    identity_missing = [key for key in identity_keys if not _env(config, key)]

    tenant_status = "pass" if tenant_mode.lower() == "strict" else ("fail" if production else "warn")
    financial_gate_status = (
        "pass" if financial_gate == "RELEASE_READY"
        else "fail" if production
        else "warn"
    )
    identity_hash_status = (
        "pass" if len(identity_hash_secret) >= 32
        else "fail" if production
        else "warn"
    )
    checks = [
        PreflightCheck(
            "environment",
            "pass",
            f"运行环境：{environment or 'development'}",
        ),
        PreflightCheck(
            "postgres",
            "pass" if (database_url.startswith("postgresql") or not production) else "fail",
            "PostgreSQL URL 已声明" if database_url.startswith("postgresql") else
            "开发环境允许本地运行时" if not production else "生产环境必须声明 BANBOOS2_DATABASE_URL",
        ),
        PreflightCheck(
            "redis",
            "pass" if (redis_url or not production) else "fail",
            "Redis URL 已声明" if redis_url else
            "开发环境允许进程内队列" if not production else "生产环境必须声明 BANBOOS2_REDIS_URL",
        ),
        PreflightCheck(
            "identity_service",
            "pass" if not identity_missing else ("fail" if production else "warn"),
            "短信、邮件和微信身份服务配置已声明" if not identity_missing else
            f"待配置：{', '.join(identity_missing)}",
        ),
        PreflightCheck(
            "identity_hash_secret",
            identity_hash_status,
            "身份标识哈希密钥已配置" if identity_hash_status == "pass" else
            "生产环境必须配置至少 32 位身份标识哈希密钥",
        ),
        PreflightCheck(
            "api_auth",
            "pass" if (not production and auth_mode in {"development-open", "token"}) or
            (production and auth_mode in {"identity", "oidc", "oauth2"}) else "fail",
            "开发联调认证模式" if not production else
            "生产使用身份服务认证" if auth_mode in {"identity", "oidc", "oauth2"} else
            "生产禁止使用 API token fallback",
        ),
        PreflightCheck(
            "cors",
            "pass" if (cors_origins and "*" not in cors_origins) or not production else "fail",
            "CORS 已限定到明确域名" if cors_origins and "*" not in cors_origins else
            "开发环境由本地启动参数管理" if not production else "生产环境必须配置明确的 CORS 域名",
        ),
        PreflightCheck(
            "financial_template",
            "pass" if template_available else ("fail" if production else "warn"),
            "1.6.6 财务模板可用" if template_available else "未找到 1.6.6 财务模板",
        ),
        PreflightCheck(
            "financial_release_gate",
            financial_gate_status,
            "XLSM 发布门禁已通过" if financial_gate == "RELEASE_READY" else
            f"XLSM 发布门禁状态：{financial_gate or '未声明'}；生产环境必须为 RELEASE_READY",
        ),
        PreflightCheck(
            "production_control",
            "pass" if control_mode == "disabled" else "fail",
            "生产控制保持关闭" if control_mode == "disabled" else "生产控制必须保持 disabled",
        ),
        PreflightCheck(
            "tenant_isolation",
            tenant_status,
            "租户范围强制检查已启用" if tenant_mode.lower() == "strict" else
            "开发环境保留租户隔离预览" if not production else
            "生产环境必须设置 BANBOOS2_TENANT_ENFORCEMENT=strict",
        ),
    ]
    blocked = any(item.status == "fail" for item in checks)
    return {
        "status": "blocked" if blocked else "staging-ready",
        "environment": environment or "development",
        "production": production,
        "checks": [item.as_dict() for item in checks],
    }
