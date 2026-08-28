from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import warnings
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings


ALLOWED_INPUT_MIME_TYPES = {"image/jpeg": "JPEG", "image/jpg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
DECODED_FORMAT_MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MAX_VERIFICATION_IMAGE_PIXELS = 25_000_000
MAX_VERIFICATION_IMAGE_DIMENSION = 10_000


class VerificationStorageConfigurationError(RuntimeError):
    pass


class VerificationStorageError(RuntimeError):
    pass


class VerificationImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedVerificationImage:
    data: bytes
    content_type: str = "image/jpeg"
    extension: str = ".jpg"


@dataclass(frozen=True)
class PrivateDocumentStream:
    body: object
    content_type: str
    content_length: int | None


def _normalized_prefix() -> str:
    prefix = settings.s3_verification_prefix.strip("/")
    if not prefix:
        raise VerificationStorageConfigurationError("Private verification storage is not configured.")
    return prefix + "/"


def validate_verification_storage_configuration() -> None:
    if not settings.s3_verification_bucket or not settings.s3_verification_region:
        raise VerificationStorageConfigurationError("Private verification storage is not configured.")
    _normalized_prefix()
    if settings.s3_event_bucket and settings.s3_verification_bucket == settings.s3_event_bucket:
        raise VerificationStorageConfigurationError("Private verification storage is not isolated.")
    if bool(settings.aws_access_key_id) != bool(settings.aws_secret_access_key):
        raise VerificationStorageConfigurationError("Private verification storage credentials are incomplete.")


def require_verification_document_upload_enabled() -> None:
    if not settings.verification_document_upload_enabled:
        raise VerificationStorageConfigurationError("Verification document upload is not enabled.")
    validate_verification_storage_configuration()


def normalize_verification_image(*, data: bytes, declared_content_type: str | None) -> NormalizedVerificationImage:
    declared = (declared_content_type or "").lower().strip()
    if declared not in ALLOWED_INPUT_MIME_TYPES:
        raise VerificationImageValidationError("Only JPEG, PNG, and WEBP images are accepted.")
    if not data:
        raise VerificationImageValidationError("The image is empty.")
    if len(data) > settings.s3_verification_max_bytes:
        raise VerificationImageValidationError("The image exceeds the configured size limit.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                decoded_format = (source.format or "").upper()
                decoded_mime = DECODED_FORMAT_MIME_TYPES.get(decoded_format)
                if decoded_mime is None or ALLOWED_INPUT_MIME_TYPES[declared] != decoded_format:
                    raise VerificationImageValidationError("The image content does not match its declared type.")
                width, height = source.size
                if (
                    width <= 0
                    or height <= 0
                    or width > MAX_VERIFICATION_IMAGE_DIMENSION
                    or height > MAX_VERIFICATION_IMAGE_DIMENSION
                    or width * height > MAX_VERIFICATION_IMAGE_PIXELS
                ):
                    raise VerificationImageValidationError("The image dimensions are too large.")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
                    rgba = oriented.convert("RGBA")
                    normalized = Image.new("RGB", rgba.size, "white")
                    normalized.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    normalized = oriented.convert("RGB")
    except VerificationImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise VerificationImageValidationError("The image dimensions are too large.") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationImageValidationError("The image is malformed or truncated.") from None

    output = BytesIO()
    normalized.save(output, format="JPEG", quality=92, optimize=True, exif=b"")
    normalized_bytes = output.getvalue()
    if len(normalized_bytes) > settings.s3_verification_max_bytes:
        raise VerificationImageValidationError("The normalized image exceeds the configured size limit.")
    return NormalizedVerificationImage(data=normalized_bytes)


class VerificationDocumentStorage:
    """Private S3 access with no public-URL behavior."""

    def __init__(self, *, client=None) -> None:  # noqa: ANN001
        validate_verification_storage_configuration()
        if client is not None:
            self._client = client
            return
        client_kwargs: dict[str, str] = {"region_name": settings.s3_verification_region or ""}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            client_kwargs.update(
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
        self._client = boto3.client("s3", **client_kwargs)

    @staticmethod
    def new_object_key() -> str:
        return f"{_normalized_prefix()}{uuid4().hex}.jpg"

    @staticmethod
    def _validate_internal_key(object_key: str) -> None:
        prefix = _normalized_prefix()
        if not object_key.startswith(prefix) or object_key == prefix or ".." in object_key:
            raise VerificationStorageError("Verification document reference is invalid.")

    def put_document(self, *, object_key: str, image: NormalizedVerificationImage) -> None:
        self._validate_internal_key(object_key)
        request = {
            "Bucket": settings.s3_verification_bucket,
            "Key": object_key,
            "Body": image.data,
            "ContentType": image.content_type,
            "CacheControl": "no-store, private, max-age=0",
            "ServerSideEncryption": "aws:kms" if settings.s3_verification_kms_key_id else "AES256",
        }
        if settings.s3_verification_kms_key_id:
            request["SSEKMSKeyId"] = settings.s3_verification_kms_key_id
        try:
            self._client.put_object(**request)
        except (BotoCoreError, ClientError):
            raise VerificationStorageError("Private verification storage is temporarily unavailable.") from None

    def get_document(self, *, object_key: str) -> PrivateDocumentStream:
        self._validate_internal_key(object_key)
        try:
            response = self._client.get_object(
                Bucket=settings.s3_verification_bucket,
                Key=object_key,
            )
        except (BotoCoreError, ClientError):
            raise VerificationStorageError("The verification document is unavailable.") from None
        return PrivateDocumentStream(
            body=response["Body"],
            content_type=response.get("ContentType") or "image/jpeg",
            content_length=response.get("ContentLength"),
        )

    def delete_document(self, *, object_key: str) -> None:
        self._validate_internal_key(object_key)
        try:
            self._client.delete_object(
                Bucket=settings.s3_verification_bucket,
                Key=object_key,
            )
        except (BotoCoreError, ClientError):
            raise VerificationStorageError("Verification document cleanup is temporarily unavailable.") from None
