import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class Storage(Protocol):
    def put_bytes(self, key: str, data: bytes) -> None: ...
    def get_local_path(self, key: str) -> Path: ...
    def list_keys(self, prefix: str) -> list[str]: ...


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


class LocalStorage:
    """Files on local disk. Fine for development."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put_bytes(self, key: str, data: bytes) -> None:
        _write_atomic(self._path(key), data)

    def get_local_path(self, key: str) -> Path:
        return self._path(key)

    def list_keys(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())


class S3Storage:
    """
    Files in any S3-compatible bucket (Supabase Storage, Cloudflare R2, Backblaze B2, AWS S3).
    DuckDB and pandas need real files, so objects are downloaded into a local cache on first use.
    The cache lives in temp storage and is rebuilt after every restart, which is fine.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        cache_dir: str,
    ):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.cache = Path(cache_dir).resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 4, "mode": "standard"},
                connect_timeout=10,
                read_timeout=60,
            ),
        )

    def _cache_path(self, key: str) -> Path:
        path = (self.cache / key).resolve()
        if not path.is_relative_to(self.cache):
            raise ValueError("Invalid storage key")
        return path

    def put_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        _write_atomic(self._cache_path(key), data)  # keep the cache current (e.g. after a retry)

    def get_local_path(self, key: str) -> Path:
        from botocore.exceptions import ClientError

        path = self._cache_path(key)
        if path.exists():
            return path

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
        os.close(fd)
        try:
            self.client.download_file(self.bucket, key, tmp)
            os.replace(tmp, path)
        except ClientError as exc:
            Path(tmp).unlink(missing_ok=True)
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError(key) from exc
            raise
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path

    def list_keys(self, prefix: str) -> list[str]:
        prefix = prefix.rstrip("/") + "/"
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)


@lru_cache
def get_storage() -> Storage:
    backend = settings.storage_backend.lower()

    if backend == "local":
        return LocalStorage(settings.upload_dir)

    if backend == "s3":
        required = {
            "S3_ENDPOINT_URL": settings.s3_endpoint_url,
            "S3_BUCKET": settings.s3_bucket,
            "S3_ACCESS_KEY_ID": settings.s3_access_key_id,
            "S3_SECRET_ACCESS_KEY": settings.s3_secret_access_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing storage settings: {', '.join(missing)}")
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            cache_dir=settings.s3_cache_dir
            or str(Path(tempfile.gettempdir()) / "octoproc-cache"),
        )

    raise ValueError(f"Unsupported STORAGE_BACKEND: {settings.storage_backend}")