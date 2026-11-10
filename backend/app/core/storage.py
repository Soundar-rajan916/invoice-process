from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.logging import logger


class StorageService:
    def __init__(self) -> None:
        self.endpoint_url = settings.S3_ENDPOINT
        self.bucket = settings.S3_BUCKET
        self.access_key = settings.S3_ACCESS_KEY
        self.secret_key = settings.S3_SECRET_KEY
        self.region = settings.S3_REGION

        self._client: Any = None
        self._s3_available: bool | None = None
        # Support both Docker (/app/data/storage_fallback) and local host dev (./data/storage_fallback)
        if Path("/app/data/storage_fallback").exists() or Path("/app/data").exists():
            self._local_fallback_dir = Path("/app/data/storage_fallback")
        else:
            self._local_fallback_dir = (
                Path(__file__).resolve().parent.parent.parent.parent / "data" / "storage_fallback"
            )
            if not self._local_fallback_dir.exists():
                self._local_fallback_dir = Path("data/storage_fallback").resolve()

    @property
    def client(self) -> Any:
        if self._client is None:
            endpoint = self.endpoint_url.strip() if self.endpoint_url and self.endpoint_url.strip() else None
            is_real_s3 = endpoint is None or "amazonaws.com" in (endpoint or "")
            connect_timeout = 5.0 if is_real_s3 else 0.5
            read_timeout = 10.0 if is_real_s3 else 0.5
            max_retries = 3 if is_real_s3 else 0

            kwargs: dict[str, Any] = {
                "service_name": "s3",
                "region_name": self.region,
                "config": Config(
                    signature_version="s3v4",
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                    retries={"max_attempts": max_retries},
                ),
            }
            if endpoint:
                kwargs["endpoint_url"] = endpoint
            if self.access_key and self.access_key.strip():
                kwargs["aws_access_key_id"] = self.access_key.strip()
            if self.secret_key and self.secret_key.strip():
                kwargs["aws_secret_access_key"] = self.secret_key.strip()

            self._client = boto3.client(**kwargs)
        return self._client

    def ensure_bucket_exists(self) -> None:
        if self._s3_available is False:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
            self._s3_available = True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                create_kwargs: dict[str, Any] = {"Bucket": self.bucket}
                if self.region and self.region != "us-east-1":
                    create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
                self.client.create_bucket(**create_kwargs)
                self._s3_available = True
                logger.info("Created S3 bucket", bucket=self.bucket, region=self.region)
            else:
                self._s3_available = False
                logger.warning("S3 bucket check failed, using local storage fallback", error=str(e))
        except Exception as e:
            self._s3_available = False
            logger.warning("Could not reach S3 endpoint, using local fallback", error=str(e))

    def upload_bytes(
        self,
        data: bytes,
        storage_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        if self._s3_available is False:
            local_path = self._local_fallback_dir / storage_key
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(data)
            return storage_key

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=storage_key,
                Body=data,
                ContentType=content_type,
            )
            self._s3_available = True
            return storage_key
        except Exception:
            self._s3_available = False
            local_path = self._local_fallback_dir / storage_key
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(data)
            return storage_key

    def download_bytes(self, storage_key: str) -> bytes:
        candidate_dirs = (
            self._local_fallback_dir,
            Path("data/storage_fallback"),
            Path("/app/data/storage_fallback"),
            Path("../data/storage_fallback"),
        )

        # Attempt download from S3 first
        if self.bucket and self._s3_available is not False:
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=storage_key)
                self._s3_available = True
                return response["Body"].read()
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchKey", "404"):
                    # Object does not exist in S3; do NOT kill S3 availability
                    pass
                else:
                    logger.warning("S3 download ClientError", key=storage_key, error=str(e))
                    self._s3_available = False
            except Exception as e:
                logger.warning("S3 download exception", key=storage_key, error=str(e))
                self._s3_available = False

        # Fallback to local files if S3 unavailable or key missing in S3
        for base in candidate_dirs:
            local_path = base / storage_key
            if local_path.exists():
                return local_path.read_bytes()

        raise FileNotFoundError(
            f"Storage key '{storage_key}' not found in S3 or local fallback"
        )

    def delete_object(self, storage_key: str) -> bool:
        """Deletes an object from S3 or local fallback."""
        deleted = False
        if self._s3_available is not False:
            try:
                self.client.delete_object(Bucket=self.bucket, Key=storage_key)
                deleted = True
            except Exception as e:
                logger.warning("Failed to delete object from S3", key=storage_key, error=str(e))

        candidate_dirs = (
            self._local_fallback_dir,
            Path("data/storage_fallback"),
            Path("/app/data/storage_fallback"),
            Path("../data/storage_fallback"),
        )
        for base in candidate_dirs:
            local_path = base / storage_key
            if local_path.exists():
                try:
                    local_path.unlink()
                    deleted = True
                except Exception as e:
                    logger.warning("Failed to delete local fallback file", path=str(local_path), error=str(e))
        return deleted

    def generate_presigned_url(self, storage_key: str, expires_in: int = 300) -> str:
        # Route through API raw streaming endpoint to ensure seamless rendering
        # without S3 cross-origin CORS blocks or private bucket access issues.
        return f"/api/v1/files/raw/{storage_key}"


storage_service = StorageService()
