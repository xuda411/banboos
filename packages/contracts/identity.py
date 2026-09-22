"""Contracts for the Banboos account and verification-code identity service."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AuthProvider = Literal["phone", "email", "wechat"]
ChallengePurpose = Literal["login", "register", "bind"]


class AuthProviderDescriptor(BaseModel):
    key: AuthProvider
    label: str
    status: Literal["ready", "pending", "disabled"]
    delivery: str
    hint: str


class AuthMethodsResponse(BaseModel):
    version: str
    default_provider: AuthProvider
    providers: list[AuthProviderDescriptor]
    legacy_token: dict[str, str]


class VerificationChallengeRequest(BaseModel):
    provider: AuthProvider
    identifier: str = Field(min_length=3, max_length=160)
    purpose: ChallengePurpose = "login"


class VerificationChallengeResponse(BaseModel):
    challenge_id: UUID
    provider: AuthProvider
    masked_target: str
    expires_in_seconds: int
    resend_after_seconds: int
    delivery_status: Literal["sent", "preview-only", "not-configured"]
    message: str


class VerificationLoginRequest(BaseModel):
    challenge_id: UUID
    code: str = Field(min_length=4, max_length=12)


class AdminUserSummary(BaseModel):
    id: str
    display_name: str
    status: Literal["active", "suspended", "pending"]
    providers: list[str]
    role: str
    tenant_scope: str
    last_login_at: str | None = None


class AdminUsersResponse(BaseModel):
    mode: Literal["preview-only", "database"]
    users: list[AdminUserSummary]
    total: int
