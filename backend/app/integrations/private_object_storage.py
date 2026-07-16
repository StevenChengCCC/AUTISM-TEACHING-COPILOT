from __future__ import annotations

from abc import ABC, abstractmethod
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from app.core.config import Settings, settings
from app.core.exceptions import ObjectStorageUnavailableError, ValidationError


@dataclass(frozen=True)
class PrivateObjectMetadata:
    key: str
    size_bytes: int
    content_type: str
    etag: str | None = None


@dataclass(frozen=True)
class PresignedPut:
    url: str
    required_headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True)
class PresignedGet:
    url: str
    expires_at: datetime


class PrivateObjectStorage(ABC):
    @abstractmethod
    def create_presigned_put(self, key: str, content_type: str) -> PresignedPut: ...

    @abstractmethod
    def create_presigned_get(self, key: str, download_name: str) -> PresignedGet: ...

    @abstractmethod
    def write_bytes(self, key: str, body: bytes, content_type: str) -> None: ...

    @abstractmethod
    def head(self, key: str) -> PrivateObjectMetadata: ...

    @abstractmethod
    def read_bytes(self, key: str, max_bytes: int) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalPrivateObjectStorage(PrivateObjectStorage):
    """Private local test adapter. It deliberately exposes no GET URL."""

    def __init__(self, config: Settings = settings):
        self.config = config
        self.root = Path(config.LOCAL_PRIVATE_STORAGE_DIR).resolve()

    def create_presigned_put(self, key: str, content_type: str) -> PresignedPut:
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.config.S3_PRESIGNED_TTL_SECONDS
        )
        payload = {
            "key": key,
            "contentType": content_type,
            "expires": int(expires_at.timestamp()),
        }
        encoded = (
            urlsafe_b64encode(
                json.dumps(payload, separators=(",", ":")).encode("utf-8")
            )
            .decode("ascii")
            .rstrip("=")
        )
        signature = self._signature(encoded)
        token = f"{encoded}.{signature}"
        return PresignedPut(
            url=(
                f"{self.config.PUBLIC_API_BASE_URL.rstrip('/')}"
                f"/api/v2/uploads/local/{token}"
            ),
            required_headers={"Content-Type": content_type},
            expires_at=expires_at,
        )

    def put_presigned(self, token: str, body: bytes, content_type: str) -> None:
        payload = self._decode_token(token)
        if int(payload["expires"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValidationError(
                "The upload URL has expired. Request a new upload intent."
            )
        if content_type.split(";")[0].strip().lower() != payload["contentType"]:
            raise ValidationError(
                "Upload content type did not match the signed intent."
            )
        if len(body) > self.config.MAX_UPLOAD_BYTES:
            raise ValidationError("Uploaded object exceeds the configured size limit.")
        path = self._path(str(payload["key"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def write_bytes(self, key: str, body: bytes, content_type: str) -> None:
        del content_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def create_presigned_get(self, key: str, download_name: str) -> PresignedGet:
        self.head(key)
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.config.EXPORT_DOWNLOAD_TTL_SECONDS
        )
        payload = {
            "key": key,
            "downloadName": Path(download_name).name,
            "expires": int(expires_at.timestamp()),
            "operation": "get",
        }
        encoded = (
            urlsafe_b64encode(
                json.dumps(payload, separators=(",", ":")).encode("utf-8")
            )
            .decode("ascii")
            .rstrip("=")
        )
        token = f"{encoded}.{self._signature(encoded)}"
        return PresignedGet(
            url=(
                f"{self.config.PUBLIC_API_BASE_URL.rstrip('/')}"
                f"/api/v2/exports/local/{token}"
            ),
            expires_at=expires_at,
        )

    def read_presigned_get(self, token: str) -> tuple[bytes, str, str]:
        payload = self._decode_token(token)
        if payload.get("operation") != "get":
            raise ValidationError("The download URL is invalid.")
        if int(payload["expires"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValidationError("The download URL has expired.")
        key = str(payload["key"])
        return (
            self.read_bytes(key, self.config.MAX_EXPORT_BYTES),
            self._content_type_for_key(key),
            Path(str(payload.get("downloadName") or "handoff-export.zip")).name,
        )

    def head(self, key: str) -> PrivateObjectMetadata:
        path = self._path(key)
        if not path.is_file():
            raise ObjectStorageUnavailableError("The uploaded object was not found.")
        return PrivateObjectMetadata(
            key=key,
            size_bytes=path.stat().st_size,
            content_type=self._content_type_for_key(key),
            etag=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def read_bytes(self, key: str, max_bytes: int) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise ObjectStorageUnavailableError("The uploaded object was not found.")
        if path.stat().st_size > max_bytes:
            raise ValidationError("Uploaded object exceeds the configured size limit.")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def _decode_token(self, token: str) -> dict[str, Any]:
        try:
            encoded, supplied_signature = token.split(".", 1)
            if not hmac.compare_digest(self._signature(encoded), supplied_signature):
                raise ValueError("bad signature")
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = json.loads(urlsafe_b64decode(padded).decode("utf-8"))
            required = {"key", "expires"}
            if not required.issubset(payload) or not (
                "contentType" in payload or payload.get("operation") == "get"
            ):
                raise ValueError("missing fields")
            self._path(str(payload["key"]))
            return payload
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValidationError("The upload URL is invalid.") from exc

    def _signature(self, value: str) -> str:
        secret = self.config.reveal(self.config.LOCAL_UPLOAD_SIGNING_SECRET) or ""
        return hmac.new(
            secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValidationError("Invalid private object key.")
        return candidate

    @staticmethod
    def _content_type_for_key(key: str) -> str:
        return {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".zip": "application/zip",
            ".csv": "text/csv",
            ".json": "application/json",
        }.get(Path(key).suffix.lower(), "application/octet-stream")


class S3PrivateObjectStorage(PrivateObjectStorage):
    def __init__(self, config: Settings = settings, client: Any | None = None):
        self.config = config
        self._provided_client = client

    @property
    def client(self):
        if self._provided_client is not None:
            return self._provided_client
        try:
            import boto3

            self._provided_client = boto3.client(
                "s3", region_name=self.config.S3_REGION or None
            )
            return self._provided_client
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "Private object storage is unavailable."
            ) from exc

    def _bucket(self) -> str:
        if not self.config.S3_BUCKET:
            raise ObjectStorageUnavailableError(
                "Private object storage is not configured."
            )
        return self.config.S3_BUCKET

    def create_presigned_put(self, key: str, content_type: str) -> PresignedPut:
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.config.S3_PRESIGNED_TTL_SECONDS
        )
        params: dict[str, Any] = {
            "Bucket": self._bucket(),
            "Key": key,
            "ContentType": content_type,
            "ServerSideEncryption": self.config.S3_SERVER_SIDE_ENCRYPTION,
        }
        headers = {
            "Content-Type": content_type,
            "x-amz-server-side-encryption": self.config.S3_SERVER_SIDE_ENCRYPTION,
        }
        if self.config.S3_SERVER_SIDE_ENCRYPTION == "aws:kms":
            if not self.config.S3_KMS_KEY_ID:
                raise ObjectStorageUnavailableError(
                    "Private object storage encryption is not configured."
                )
            params["SSEKMSKeyId"] = self.config.S3_KMS_KEY_ID
            headers["x-amz-server-side-encryption-aws-kms-key-id"] = (
                self.config.S3_KMS_KEY_ID
            )
        try:
            url = self.client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=self.config.S3_PRESIGNED_TTL_SECONDS,
                HttpMethod="PUT",
            )
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "Could not create a private upload URL."
            ) from exc
        return PresignedPut(url=url, required_headers=headers, expires_at=expires_at)

    def write_bytes(self, key: str, body: bytes, content_type: str) -> None:
        params: dict[str, Any] = {
            "Bucket": self._bucket(),
            "Key": key,
            "Body": body,
            "ContentType": content_type,
            "ServerSideEncryption": self.config.S3_SERVER_SIDE_ENCRYPTION,
        }
        if self.config.S3_SERVER_SIDE_ENCRYPTION == "aws:kms":
            if not self.config.S3_KMS_KEY_ID:
                raise ObjectStorageUnavailableError(
                    "Private object storage encryption is not configured."
                )
            params["SSEKMSKeyId"] = self.config.S3_KMS_KEY_ID
        try:
            self.client.put_object(**params)
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "The export could not be stored privately."
            ) from exc

    def create_presigned_get(self, key: str, download_name: str) -> PresignedGet:
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.config.EXPORT_DOWNLOAD_TTL_SECONDS
        )
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket(),
                    "Key": key,
                    "ResponseContentDisposition": (
                        f'attachment; filename="{Path(download_name).name}"'
                    ),
                },
                ExpiresIn=self.config.EXPORT_DOWNLOAD_TTL_SECONDS,
                HttpMethod="GET",
            )
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "Could not create a private download URL."
            ) from exc
        return PresignedGet(url=url, expires_at=expires_at)

    def head(self, key: str) -> PrivateObjectMetadata:
        try:
            response = self.client.head_object(Bucket=self._bucket(), Key=key)
            return PrivateObjectMetadata(
                key=key,
                size_bytes=int(response["ContentLength"]),
                content_type=str(response.get("ContentType") or ""),
                etag=str(response.get("ETag") or "").strip('"') or None,
            )
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "The uploaded object could not be verified."
            ) from exc

    def read_bytes(self, key: str, max_bytes: int) -> bytes:
        metadata = self.head(key)
        if metadata.size_bytes > max_bytes:
            raise ValidationError("Uploaded object exceeds the configured size limit.")
        try:
            response = self.client.get_object(Bucket=self._bucket(), Key=key)
            body = response["Body"].read(max_bytes + 1)
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "The uploaded object could not be read."
            ) from exc
        if len(body) > max_bytes:
            raise ValidationError("Uploaded object exceeds the configured size limit.")
        return body

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self._bucket(), Key=key)
            waiter_factory = getattr(self.client, "get_waiter", None)
            if callable(waiter_factory):
                waiter_factory("object_not_exists").wait(
                    Bucket=self._bucket(),
                    Key=key,
                    WaiterConfig={"Delay": 1, "MaxAttempts": 5},
                )
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "The private object could not be deleted and verified."
            ) from exc


def get_private_object_storage(
    config: Settings = settings,
) -> PrivateObjectStorage:
    if config.effective_object_storage_provider == "s3":
        return S3PrivateObjectStorage(config)
    return LocalPrivateObjectStorage(config)
