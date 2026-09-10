"""Managed users and one-time mobile enrollment invitations."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..api.errors import ApiError
from ..db.models import DeviceEnrollment, Jurisdiction, User
from .auth import AuthManager, Principal
from .auth_core import ROLE_PERMISSIONS, hash_password

ENROLLMENT_TTL = timedelta(minutes=15)


class AccountService:
    def __init__(self, auth: AuthManager):
        self.auth = auth

    def list_users(self, principal: Principal) -> list[dict]:
        sessions = self._sessions()
        with sessions() as session:
            query = select(User).order_by(User.full_name, User.email)
            if principal.role != "ADMIN" and principal.jurisdiction_id:
                query = query.where(User.jurisdiction_id == uuid.UUID(principal.jurisdiction_id))
            return [_public_user(row) for row in session.scalars(query)]

    def list_jurisdictions(self) -> list[dict]:
        sessions = self._sessions()
        with sessions() as session:
            rows = session.scalars(select(Jurisdiction).order_by(
                Jurisdiction.state, Jurisdiction.name))
            return [{"id": str(row.id), "name": row.name, "state": row.state,
                     "path": row.path} for row in rows]

    def create_user(self, values: dict, principal: Principal) -> dict:
        sessions = self._sessions()
        role = values["role"]
        if role not in ROLE_PERMISSIONS:
            raise ApiError("E_VALIDATION", "unsupported user role")
        email = values["email"].strip().casefold()
        if "@" not in email or len(email) > 320:
            raise ApiError("E_VALIDATION", "a valid email address is required")
        password = values.get("password")
        try:
            encoded = hash_password(password) if password else None
        except ValueError as exc:
            raise ApiError("E_VALIDATION", str(exc)) from exc
        jurisdiction_id = _uuid_or_none(values.get("jurisdiction_id"), "jurisdiction_id")
        with sessions() as session:
            if jurisdiction_id and session.get(Jurisdiction, jurisdiction_id) is None:
                raise ApiError("E_VALIDATION", "the jurisdiction does not exist")
            row = User(
                full_name=values["full_name"].strip(), email=email, role=role,
                phone=_clean(values.get("phone")), department=_clean(values.get("department")),
                jurisdiction_id=jurisdiction_id, password_hash=encoded,
                is_legal_reviewer=bool(values.get("is_legal_reviewer", False)),
                is_active=True)
            if not row.full_name:
                raise ApiError("E_VALIDATION", "full_name is required")
            session.add(row)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ApiError("E_CONFLICT", "an account with that email already exists") from exc
            result = _public_user(row)
            session.add(_audit_user(principal, row.id, "USER_CREATE", result))
            session.commit()
            return result

    def update_user(self, user_id: str, values: dict, principal: Principal) -> dict:
        parsed = _uuid_or_none(user_id, "user_id")
        sessions = self._sessions()
        with sessions() as session:
            row = session.get(User, parsed)
            if row is None:
                raise ApiError("E_NOT_FOUND", "user not found")
            changes = {}
            for name in ("full_name", "phone", "department"):
                if name in values:
                    setattr(row, name, _clean(values[name]) if name != "full_name"
                            else values[name].strip())
                    changes[name] = getattr(row, name)
            if "role" in values:
                if values["role"] not in ROLE_PERMISSIONS:
                    raise ApiError("E_VALIDATION", "unsupported user role")
                row.role = values["role"]
                changes["role"] = row.role
            if "jurisdiction_id" in values:
                jurisdiction_id = _uuid_or_none(values["jurisdiction_id"], "jurisdiction_id")
                if jurisdiction_id and session.get(Jurisdiction, jurisdiction_id) is None:
                    raise ApiError("E_VALIDATION", "the jurisdiction does not exist")
                row.jurisdiction_id = jurisdiction_id
                changes["jurisdiction_id"] = values["jurisdiction_id"]
            for name in ("is_active", "is_legal_reviewer"):
                if name in values:
                    setattr(row, name, bool(values[name]))
                    changes[name] = getattr(row, name)
            if "password" in values and values["password"]:
                try:
                    row.password_hash = hash_password(values["password"])
                except ValueError as exc:
                    raise ApiError("E_VALIDATION", str(exc)) from exc
                changes["password_changed"] = True
            row.updated_at = datetime.now(UTC)
            session.add(_audit_user(principal, row.id, "USER_UPDATE", changes))
            result = _public_user(row)
            session.commit()
            return result

    def issue_enrollment(self, user_id: str, server_url: str | None,
                         principal: Principal) -> dict:
        parsed = _uuid_or_none(user_id, "user_id")
        sessions = self._sessions()
        advertised = _server_url(server_url or self.auth.settings.public_base_url)
        now = datetime.now(UTC)
        raw = secrets.token_urlsafe(32)
        with sessions() as session:
            user = session.get(User, parsed)
            if user is None:
                raise ApiError("E_NOT_FOUND", "user not found")
            if not user.is_active:
                raise ApiError("E_CONFLICT", "an inactive account cannot enroll a device")
            row = DeviceEnrollment(
                user_id=user.id, created_by=uuid.UUID(principal.id),
                token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                server_url=advertised, expires_at=now + ENROLLMENT_TTL)
            session.add(row)
            session.flush()
            session.add(_audit_user(
                principal, user.id, "DEVICE_ENROLLMENT_ISSUED",
                {"enrollment_id": str(row.id), "expires_at": row.expires_at.isoformat()}))
            invitation = {
                "enrollment_id": str(row.id), "user": _public_user(user),
                "server_url": advertised,
                "server_fingerprint": self.auth.server_fingerprint(),
                "token": raw, "expires_at": row.expires_at.isoformat(),
            }
            invitation["enrollment_uri"] = "lmpc://enroll?" + urlencode({
                "server": advertised, "fingerprint": invitation["server_fingerprint"],
                "token": raw})
            session.commit()
            return invitation

    def _sessions(self):
        if self.auth.disabled or self.auth.sessions is None:
            raise ApiError("E_FORBIDDEN", "account management requires local authentication")
        return self.auth.sessions


def _public_user(row: User) -> dict:
    return {
        "id": str(row.id), "full_name": row.full_name, "email": row.email,
        "phone": row.phone, "role": row.role,
        "jurisdiction_id": str(row.jurisdiction_id) if row.jurisdiction_id else None,
        "department": row.department, "is_active": row.is_active,
        "is_legal_reviewer": row.is_legal_reviewer,
        "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _uuid_or_none(value: str | None, field: str) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApiError("E_VALIDATION", f"{field} must be a UUID") from exc


def _clean(value: str | None) -> str | None:
    cleaned = value.strip() if value else ""
    return cleaned or None


def _server_url(value: str) -> str:
    if not value:
        raise ApiError("E_VALIDATION", "a LAN server URL is required for enrollment")
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ApiError("E_VALIDATION", "server_url must be an HTTP(S) origin")
    if parsed.query or parsed.fragment:
        raise ApiError("E_VALIDATION", "server_url must not contain a query or fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


def _audit_user(principal: Principal, entity_id: uuid.UUID, action: str, diff: dict):
    from ..db.models import AuditLog
    return AuditLog(
        entity_type="user", entity_id=entity_id, actor_id=uuid.UUID(principal.id),
        action=action, diff=diff)
