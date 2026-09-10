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
    redis_url: str = ""
    s3_endpoint: str = ""
    s3_bucket: str = ""
    storage_root: str = ".lmpc-data/objects"  # durable local fallback for development
    max_image_bytes: int = 20_971_520     # Appendix B
    max_image_pixels: int = 100_000_000
    ocr_max_edge: int = 1800
    rate_limit_per_min: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        return cls(
            rulepack_path=e.get("LMPC_RULEPACK_PATH", cls.rulepack_path),
            log_level=e.get("LMPC_LOG_LEVEL", cls.log_level),
            db_url=e.get("LMPC_DB_URL", ""),
            officer_uuid=e.get("LMPC_OFFICER_UUID", ""),
            jurisdiction_uuid=e.get("LMPC_JURISDICTION_UUID", ""),
            redis_url=e.get("LMPC_REDIS_URL", ""),
            s3_endpoint=e.get("LMPC_S3_ENDPOINT", ""),
            s3_bucket=e.get("LMPC_S3_BUCKET", ""),
            storage_root=e.get("LMPC_STORAGE_ROOT", cls.storage_root),
            max_image_bytes=int(e.get("LMPC_MAX_IMAGE_BYTES", cls.max_image_bytes)),
            max_image_pixels=int(e.get("LMPC_MAX_IMAGE_PIXELS", cls.max_image_pixels)),
            ocr_max_edge=int(e.get("LMPC_OCR_MAX_EDGE", cls.ocr_max_edge)),
            rate_limit_per_min=int(e.get("LMPC_RATE_LIMIT_PER_MIN",
                                         cls.rate_limit_per_min)))
