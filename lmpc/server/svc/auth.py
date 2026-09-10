"""Local identity provider and the role/permission boundary.

OIDC remains the production integration point. This module implements the spec's
on-premises fallback: Argon2id passwords, short RS256 access tokens and opaque rotating
refresh tokens whose plaintext is never stored in PostgreSQL.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select, text, update

from ..api.errors import ApiError
from ..config import Settings
from ..db import sessionmaker_of
from ..db.models import AuditLog, RefreshToken, User
from .auth_core import (ALL_PERMISSIONS, ROLE_PERMISSIONS, Principal, hash_password,
                        load_or_create_keys, password_hasher, password_matches)

ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
LOCK_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)

class AuthManager:
    def __init__(self, settings: Settings):
        if settings.auth_mode not in {"disabled", "local"}:
            raise RuntimeError("LMPC_AUTH_MODE must be 'disabled' or 'local'")
        if settings.auth_mode == "local" and not settings.db_url:
            raise RuntimeError("LMPC_AUTH_MODE=local requires LMPC_DB_URL")
        self.settings = settings
        self.disabled = settings.auth_mode == "disabled"
        self.sessions = sessionmaker_of(settings.db_url) if not self.disabled else None
        self.hasher = password_hasher()
        self._dummy_hash = self.hasher.hash("not-a-real-user-password")
        self.private_key = self.public_key = b""
        if not self.disabled:
            self.private_key, self.public_key = load_or_create_keys(settings.jwt_key_path)

    def current(self, access_token: str | None) -> Principal:
        if self.disabled:
            return Principal(
                id=self.settings.officer_uuid or str(uuid.UUID(int=0)),
                full_name="Development principal", email="disabled-auth@local.invalid",
                role="ADMIN", jurisdiction_id=self.settings.jurisdiction_uuid or None,
                is_legal_reviewer=True, permissions=ALL_PERMISSIONS,
                disabled_auth=True)
        if not access_token:
            raise ApiError("E_BAD_CREDENTIALS", "a bearer access token is required")
        try:
            claims = jwt.decode(
                access_token, self.public_key, algorithms=["RS256"],
                audience=self.settings.jwt_audience, issuer=self.settings.jwt_issuer,
                options={"require": ["sub", "jti", "iat", "exp", "aud", "iss"]})
            user_id = uuid.UUID(claims["sub"])
        except jwt.ExpiredSignatureError as exc:
            raise ApiError("E_TOKEN_EXPIRED", "the access token has expired") from exc
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise ApiError("E_BAD_CREDENTIALS", "the access token is invalid") from exc
        with self.sessions() as session:  # type: ignore[operator]
            user = session.get(User, user_id)
            if user is None or not user.is_active:
                raise ApiError("E_BAD_CREDENTIALS", "the account is unavailable")
            return _principal(user)

    def login(self, email: str, password: str, *, user_agent: str | None,
              ip: str | None) -> tuple[str, str, Principal]:
        self._require_local()
        now = datetime.now(UTC)
        with self.sessions() as session:  # type: ignore[operator]
            user = session.scalar(select(User).where(User.email == email.strip()).with_for_update())
            if user is None:
                self._verify_dummy(password)
                session.add(_audit("LOGIN_FAILED", None, ip, user_agent,
                                   {"email_hash": _email_fingerprint(email)}))
                session.commit()
                raise ApiError("E_BAD_CREDENTIALS", "email or password is incorrect")
            if user.locked_until and user.locked_until > now:
                session.add(_audit("LOGIN_FAILED", user.id, ip, user_agent,
                                   {"reason": "account_locked"}))
                session.commit()
                raise ApiError("E_BAD_CREDENTIALS", "email or password is incorrect")
            valid = user.is_active and user.password_hash and self._verify(
                user.password_hash, password)
            if not valid:
                _record_failure(user, now)
                session.add(_audit("LOGIN_FAILED", user.id, ip, user_agent,
                                   {"reason": "bad_credentials"}))
                session.commit()
                raise ApiError("E_BAD_CREDENTIALS", "email or password is incorrect")
            user.failed_login_count = 0
            user.failed_login_window_at = None
            user.locked_until = None
            user.last_login_at = now
            principal = _principal(user)
            refresh, row = _new_refresh(user.id, now, user_agent, ip)
            session.add(row)
            session.add(_audit("LOGIN", user.id, ip, user_agent, None))
            session.commit()
        return self._access(principal, now), refresh, principal

    def refresh(self, raw_token: str | None, *, user_agent: str | None,
                ip: str | None) -> tuple[str, str, Principal]:
        self._require_local()
        if not raw_token:
            raise ApiError("E_REFRESH_REVOKED", "a refresh token is required")
        now = datetime.now(UTC)
        token_hash = _hash(raw_token)
        with self.sessions() as session:  # type: ignore[operator]
            row = session.scalar(select(RefreshToken).where(
                RefreshToken.token_hash == token_hash).with_for_update())
            if row is None:
                raise ApiError("E_REFRESH_REVOKED", "the refresh token is invalid")
            if row.revoked_at is not None:
                session.execute(update(RefreshToken).where(
                    RefreshToken.family_id == row.family_id,
                    RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
                session.add(_audit("REFRESH_REUSE", row.user_id, ip, user_agent,
                                   {"family_id": str(row.family_id)}))
                session.commit()
                raise ApiError("E_REFRESH_REVOKED", "refresh-token reuse revoked the session")
            if row.expires_at <= now:
                row.revoked_at = now
                session.commit()
                raise ApiError("E_REFRESH_REVOKED", "the refresh token has expired")
            user = session.get(User, row.user_id)
            if user is None or not user.is_active:
                row.revoked_at = now
                session.commit()
                raise ApiError("E_REFRESH_REVOKED", "the account is unavailable")
            row.revoked_at = now
            refresh, replacement = _new_refresh(
                user.id, now, user_agent, ip, family_id=row.family_id)
            session.add(replacement)
            principal = _principal(user)
            session.commit()
        return self._access(principal, now), refresh, principal

    def logout(self, raw_token: str | None, *, user_agent: str | None,
               ip: str | None) -> None:
        self._require_local()
        if not raw_token:
            return
        now = datetime.now(UTC)
        with self.sessions() as session:  # type: ignore[operator]
            row = session.scalar(select(RefreshToken).where(
                RefreshToken.token_hash == _hash(raw_token)).with_for_update())
            if row and row.revoked_at is None:
                row.revoked_at = now
                session.add(_audit("LOGOUT", row.user_id, ip, user_agent, None))
                session.commit()

    def ensure_scan_scope(self, principal: Principal, scan) -> None:
        if self.disabled or principal.role == "ADMIN":
            return
        if principal.role == "FIELD_OFFICER":
            allowed = scan.officer_id == principal.id
        else:
            allowed = self._jurisdiction_contains(
                principal.jurisdiction_id, scan.jurisdiction_id)
        if not allowed:
            self.audit_denial(principal, "scan", scan.id)
            raise ApiError("E_FORBIDDEN", "the scan is outside your authorised scope")

    def audit_denial(self, principal: Principal, entity_type: str,
                     entity_id: str | None) -> None:
        if self.disabled:
            return
        try:
            parsed = uuid.UUID(entity_id) if entity_id else None
        except ValueError:
            parsed = None
        with self.sessions() as session:  # type: ignore[operator]
            session.add(AuditLog(
                entity_type=entity_type, entity_id=parsed, actor_id=uuid.UUID(principal.id),
                action="PERMISSION_DENIED", diff=None))
            session.commit()

    def _jurisdiction_contains(self, root: str | None, target: str | None) -> bool:
        if not root or not target:
            return False
        with self.sessions() as session:  # type: ignore[operator]
            return bool(session.scalar(text(
                "SELECT target.path <@ root.path FROM jurisdictions AS target "
                "CROSS JOIN jurisdictions AS root "
                "WHERE target.id = :target AND root.id = :root"),
                {"target": uuid.UUID(target), "root": uuid.UUID(root)}))

    def _access(self, principal: Principal, now: datetime) -> str:
        claims = {
            "sub": principal.id, "role": principal.role,
            "jurisdiction_id": principal.jurisdiction_id,
            "permissions": sorted(principal.permissions), "jti": str(uuid.uuid4()),
            "iat": now, "exp": now + ACCESS_TTL,
            "aud": self.settings.jwt_audience, "iss": self.settings.jwt_issuer,
        }
        return jwt.encode(claims, self.private_key, algorithm="RS256")

    def _verify(self, encoded: str, password: str) -> bool:
        try:
            return self.hasher.verify(encoded, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def _verify_dummy(self, password: str) -> None:
        self._verify(self._dummy_hash, password)

    def _require_local(self) -> None:
        if self.disabled:
            raise ApiError("E_FORBIDDEN", "local authentication is disabled")


def _principal(user: User) -> Principal:
    permissions = ROLE_PERMISSIONS.get(user.role)
    if permissions is None:
        raise ApiError("E_FORBIDDEN", "the account has an unsupported role")
    return Principal(
        id=str(user.id), full_name=user.full_name, email=user.email, role=user.role,
        jurisdiction_id=str(user.jurisdiction_id) if user.jurisdiction_id else None,
        is_legal_reviewer=user.is_legal_reviewer,
        permissions=frozenset(permissions))


def _record_failure(user: User, now: datetime) -> None:
    if not user.failed_login_window_at or now - user.failed_login_window_at > LOCK_WINDOW:
        user.failed_login_window_at = now
        user.failed_login_count = 1
    else:
        user.failed_login_count += 1
    if user.failed_login_count >= 5:
        user.locked_until = now + LOCK_DURATION


def _new_refresh(user_id: uuid.UUID, now: datetime, user_agent: str | None,
                 ip: str | None, family_id: uuid.UUID | None = None) -> tuple[str, RefreshToken]:
    raw = secrets.token_urlsafe(48)
    return raw, RefreshToken(
        user_id=user_id, family_id=family_id or uuid.uuid4(), token_hash=_hash(raw),
        expires_at=now + REFRESH_TTL, user_agent=user_agent, ip=ip)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _email_fingerprint(email: str) -> str:
    return hashlib.sha256(email.strip().casefold().encode()).hexdigest()[:16]


def _audit(action: str, actor_id: uuid.UUID | None, ip: str | None,
           user_agent: str | None, diff: dict | None) -> AuditLog:
    return AuditLog(
        entity_type="user", entity_id=actor_id, actor_id=actor_id, action=action,
        diff=diff, ip=ip, user_agent=user_agent)

