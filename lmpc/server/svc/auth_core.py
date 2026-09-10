"""Small, reviewable primitives shared by local authentication and bootstrap."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROLE_PERMISSIONS = {
    "FIELD_OFFICER": {
        "scans:create", "scans:read", "scans:update", "declarations:correct",
        "evaluations:read", "reports:read", "reports:export", "products:read",
        "dashboard:read",
    },
    "REVIEWING_OFFICER": {
        "scans:create", "scans:read", "scans:update", "scans:reevaluate",
        "declarations:correct", "evaluations:read", "evaluations:override",
        "reports:create", "reports:read", "reports:export", "products:read",
        "products:merge", "rules:read", "dashboard:read",
    },
    "ADMIN": {
        "scans:create", "scans:read", "scans:update", "scans:reevaluate",
        "declarations:correct", "evaluations:read", "evaluations:override",
        "reports:create", "reports:read", "reports:export", "products:read",
        "products:merge", "rules:read", "rules:approve", "users:read", "users:manage",
        "jurisdictions:manage", "dashboard:read", "dashboard:read_all", "audit:read",
    },
    "AUDITOR": {
        "scans:read", "evaluations:read", "reports:read", "reports:export",
        "products:read", "rules:read", "users:read", "dashboard:read", "audit:read",
    },
}
ALL_PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values())


@dataclass(frozen=True)
class Principal:
    id: str
    full_name: str
    email: str
    role: str
    jurisdiction_id: str | None
    is_legal_reviewer: bool
    permissions: frozenset[str]
    disabled_auth: bool = False

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def public(self) -> dict:
        return {
            "id": self.id, "full_name": self.full_name, "email": self.email,
            "role": self.role, "jurisdiction": self.jurisdiction_id,
            "is_legal_reviewer": self.is_legal_reviewer,
            "permissions": sorted(self.permissions),
        }


def password_hasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16,
        type=Type.ID)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("local passwords must contain at least 12 characters")
    if password.casefold() in {"password1234", "123456789012", "qwertyuiop12"}:
        raise ValueError("the password is too common")
    return password_hasher().hash(password)


def password_matches(encoded: str | None, password: str) -> bool:
    if not encoded:
        return False
    try:
        return password_hasher().verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def load_or_create_keys(path: str) -> tuple[bytes, bytes]:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        encoded = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())
        fd, temporary = tempfile.mkstemp(prefix=".jwt-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    private = serialization.load_pem_private_key(target.read_bytes(), password=None)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return target.read_bytes(), public
