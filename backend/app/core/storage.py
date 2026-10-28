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

        self._client = None
        self._local_fallback_dir = Path("data/storage_fallback")

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=1,
                    read_timeout=1,
                    retries={"max_attempts": 0},
                ),
            )
        return self._client

    def ensure_bucket_exists(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                self.client.create_bucket(Bucket=self.bucket)
                logger.info("Created S3 bucket", bucket=self.bucket)
            else:
                logger.warning(
                    "Could not head S3 bucket, using local fallback if needed", error=str(e)
                )

    def upload_bytes(
        self,
        data: bytes,
        storage_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=storage_key,
                Body=data,
                ContentType=content_type,
            )
            return storage_key
        except Exception as e:
            logger.warning(
                "S3 upload failed, using local storage fallback", key=storage_key, error=str(e)
            )
            local_path = self._local_fallback_dir / storage_key
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(data)
            return storage_key

    def download_bytes(self, storage_key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=storage_key)
            return response["Body"].read()
        except Exception as e:
            local_path = self._local_fallback_dir / storage_key
            if local_path.exists():
                return local_path.read_bytes()
            raise FileNotFoundError(
                f"Storage key '{storage_key}' not found in S3 or local fallback"
            ) from e

    def generate_presigned_url(self, storage_key: str, expires_in: int = 3600) -> str:
        try:
            url = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": storage_key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception:
            return f"/api/v1/files/raw/{storage_key}"


storage_service = StorageService()
