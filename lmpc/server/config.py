"""Twelve-factor configuration: every knob arrives as an LMPC_* environment variable
(Appendix B). Nothing here invents a service that was not configured."""
from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    rulepack_path: str = "rulepack/current.json"
    log_level: str = "INFO"
    db_url: str = ""                      # empty until persistence is wired (Part 13)
    officer_uuid: str = ""                # bootstrap officer until Part 14 auth lands
    jurisdiction_uuid: str = ""
    auth_mode: str = "disabled"           # disabled for engine tests; local in .env.example
    bootstrap_email: str = "reviewer@local.invalid"
    bootstrap_password: str = ""
    jwt_key_path: str = ".lmpc-data/auth/jwt-private.pem"
    jwt_issuer: str = "lmpc-local"
    jwt_audience: str = "lmpc-api"
    cookie_secure: bool = False
    allow_self_review: bool = False
    redis_url: str = ""
    s3_endpoint: str = ""
    s3_bucket: str = ""
    storage_root: str = ".lmpc-data/objects"  # durable local fallback for development
    max_image_bytes: int = 20_971_520     # Appendix B
    max_image_pixels: int = 100_000_000
    ocr_max_edge: int = 1800
    rate_limit_per_min: int = 60
    git_sha: str = ""
    container_digest: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        return cls(
            rulepack_path=e.get("LMPC_RULEPACK_PATH", cls.rulepack_path),
            log_level=e.get("LMPC_LOG_LEVEL", cls.log_level),
            db_url=e.get("LMPC_DB_URL", ""),
            officer_uuid=e.get("LMPC_OFFICER_UUID", ""),
            jurisdiction_uuid=e.get("LMPC_JURISDICTION_UUID", ""),
            auth_mode=e.get("LMPC_AUTH_MODE", cls.auth_mode),
            bootstrap_email=e.get("LMPC_BOOTSTRAP_EMAIL", cls.bootstrap_email),
            bootstrap_password=e.get("LMPC_BOOTSTRAP_PASSWORD", ""),
            jwt_key_path=e.get("LMPC_JWT_KEY_PATH", cls.jwt_key_path),
            jwt_issuer=e.get("LMPC_JWT_ISSUER", cls.jwt_issuer),
            jwt_audience=e.get("LMPC_JWT_AUDIENCE", cls.jwt_audience),
            cookie_secure=_bool(e.get("LMPC_COOKIE_SECURE", "false")),
            allow_self_review=_bool(e.get("LMPC_ALLOW_SELF_REVIEW", "false")),
            redis_url=e.get("LMPC_REDIS_URL", ""),
            s3_endpoint=e.get("LMPC_S3_ENDPOINT", ""),
            s3_bucket=e.get("LMPC_S3_BUCKET", ""),
            storage_root=e.get("LMPC_STORAGE_ROOT", cls.storage_root),
            max_image_bytes=int(e.get("LMPC_MAX_IMAGE_BYTES", cls.max_image_bytes)),
            max_image_pixels=int(e.get("LMPC_MAX_IMAGE_PIXELS", cls.max_image_pixels)),
            ocr_max_edge=int(e.get("LMPC_OCR_MAX_EDGE", cls.ocr_max_edge)),
            rate_limit_per_min=int(e.get("LMPC_RATE_LIMIT_PER_MIN",
                                         cls.rate_limit_per_min)),
            git_sha=e.get("LMPC_GIT_SHA", ""),
            container_digest=e.get("LMPC_CONTAINER_DIGEST", ""))


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean setting: {value}")
