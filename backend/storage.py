"""Object storage helpers using MinIO (S3-compatible) via aioboto3."""

from __future__ import annotations

import logging
import uuid

import aioboto3

from config import settings

logger = logging.getLogger(__name__)

_SESSION = aioboto3.Session()


def _client():
    """Return an aioboto3 S3 client pointed at the configured MinIO endpoint."""
    return _SESSION.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name="us-east-1",  # MinIO ignores this; boto3 requires a value
    )


def _public_url(internal_url: str) -> str:
    """Replace the internal MinIO endpoint with the public one in a presigned URL."""
    return internal_url.replace(settings.minio_endpoint, settings.minio_public_endpoint, 1)


async def upload_docx(data: bytes, filename: str) -> str:
    """Upload DOCX bytes to MinIO and return a 1-hour presigned GET URL."""
    key = f"reports/{uuid.uuid4()}/{filename}"
    async with _client() as s3:
        await s3.put_object(
            Bucket=settings.minio_bucket,
            Key=key,
            Body=data,
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.minio_bucket, "Key": key},
            ExpiresIn=3600,
        )
    logger.info("Uploaded DOCX to %s/%s/%s", settings.minio_endpoint, settings.minio_bucket, key)
    return _public_url(url)


async def upload_pdf(data: bytes, filename: str) -> str:
    """Upload PDF bytes to MinIO and return a 1-hour presigned GET URL."""
    key = f"reports/{uuid.uuid4()}/{filename}"
    async with _client() as s3:
        await s3.put_object(
            Bucket=settings.minio_bucket,
            Key=key,
            Body=data,
            ContentType="application/pdf",
        )
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.minio_bucket, "Key": key},
            ExpiresIn=3600,
        )
    logger.info("Uploaded PDF to %s/%s/%s", settings.minio_endpoint, settings.minio_bucket, key)
    return _public_url(url)
