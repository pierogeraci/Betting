"""Archivio dei file.

Due secchi: l'archivio, indirizzato per sha256 e visibile solo dalla rete interna,
e il secchio di arrivo, dove i contenitori di raccolta possono soltanto scrivere.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Protocol

from core.config import get_settings


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_key(digest: str) -> str:
    return f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"


class ObjectStore(Protocol):
    def put(
        self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None: ...
    def get(self, bucket: str, key: str) -> bytes: ...
    def exists(self, bucket: str, key: str) -> bool: ...
    def delete(self, bucket: str, key: str) -> None: ...
    def ensure_bucket(self, bucket: str) -> None: ...


class MemoryStore:
    """Archivio in memoria, per i test."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.objects[(bucket, key)] = bytes(data)

    def get(self, bucket: str, key: str) -> bytes:
        try:
            return self.objects[(bucket, key)]
        except KeyError as exc:
            raise FileNotFoundError(f"{bucket}/{key}") from exc

    def exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self.objects

    def delete(self, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)

    def ensure_bucket(self, bucket: str) -> None:
        return None


class S3Store:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, region: str) -> None:
        import boto3
        from botocore.config import Config

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3},
                proxies={},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def put(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, bucket: str, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            return self._client.get_object(Bucket=bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise FileNotFoundError(f"{bucket}/{key}") from exc
            raise

    def exists(self, bucket: str, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)

    def ensure_bucket(self, bucket: str) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=bucket)
        except ClientError:
            self._client.create_bucket(Bucket=bucket)


_override: ObjectStore | None = None


def set_store(store: ObjectStore | None) -> None:
    """Sostituisce l'archivio (usato dai test)."""
    global _override
    _override = store


@lru_cache
def _internal_store() -> ObjectStore:
    s = get_settings()
    return S3Store(s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_region)


def get_store() -> ObjectStore:
    return _override or _internal_store()


def archive_bytes(data: bytes, content_type: str = "application/octet-stream") -> tuple[str, str]:
    """Salva nell'archivio e restituisce (sha256, chiave). Lo stesso contenuto si salva una volta sola."""
    digest = sha256_hex(data)
    key = archive_key(digest)
    store = get_store()
    bucket = get_settings().s3_archive_bucket
    if not store.exists(bucket, key):
        store.put(bucket, key, data, content_type)
    return digest, key


def read_archive(key: str) -> bytes:
    return get_store().get(get_settings().s3_archive_bucket, key)
