"""Immutable evidence storage.

The API writes a validated image before it creates processing work. Production uses an
S3-compatible bucket; development uses the same hash-addressed key contract on disk.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Protocol

from ..config import Settings


class ObjectStore(Protocol):
    def put_immutable(self, key: str, data: bytes, media_type: str, sha256: str) -> None: ...


def open_object_store(settings: Settings) -> ObjectStore:
    if settings.s3_bucket:
        return S3ObjectStore(settings.s3_bucket, settings.s3_endpoint or None)
    return LocalObjectStore(settings.storage_root)


class LocalObjectStore:
    """Atomic create-only writes; an existing key must contain the same bytes."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def put_immutable(self, key: str, data: bytes, media_type: str, sha256: str) -> None:
        del media_type
        _verify_digest(data, sha256)
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self._assert_digest(target, sha256)
            return
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)       # create-only, even under a racing upload
            except FileExistsError:
                self._assert_digest(target, sha256)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def _path(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("object key must be relative and may not traverse")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("object key escapes storage root")
        return path

    @staticmethod
    def _assert_digest(path: Path, expected: str) -> None:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"immutable object collision at {path}")


class S3ObjectStore:
    """S3-compatible create-only writes. boto3 is imported only in the S3 process."""

    def __init__(self, bucket: str, endpoint: str | None):
        import boto3
        from botocore.exceptions import ClientError

        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint)
        self.client_error = ClientError

    def put_immutable(self, key: str, data: bytes, media_type: str, sha256: str) -> None:
        _verify_digest(data, sha256)
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=media_type,
                Metadata={"sha256": sha256}, IfNoneMatch="*")
        except self.client_error as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status not in (409, 412):
                raise
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            if head.get("Metadata", {}).get("sha256") != sha256:
                raise RuntimeError(f"immutable object collision at {key}") from exc


def _verify_digest(data: bytes, expected: str) -> None:
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("object bytes do not match their SHA-256")
