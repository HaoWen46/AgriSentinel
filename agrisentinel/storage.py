"""MinIO / S3 object-store helpers (the raw lake).

Uses boto3 against the S3-compatible MinIO endpoint with path-style addressing
(required by MinIO). All keys are plain strings; callers namespace them, e.g.
``s2/<aoi>/<date>/B08.tif`` or ``laws/<pcode>.json``.
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_fixed

from agrisentinel.config import get_settings
from agrisentinel.logging import get_logger

log = get_logger(__name__)


def get_s3():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@retry(stop=stop_after_attempt(15), wait=wait_fixed(2), reraise=True)
def ensure_bucket(bucket: str | None = None) -> str:
    """Create the bucket if missing (idempotent); retry while MinIO boots."""
    s = get_settings()
    bucket = bucket or s.s3_bucket
    client = get_s3()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
        log.info("Created bucket s3://%s", bucket)
    return bucket


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    s = get_settings()
    get_s3().put_object(Bucket=s.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return f"s3://{s.s3_bucket}/{key}"


def get_bytes(key: str) -> bytes:
    s = get_settings()
    obj = get_s3().get_object(Bucket=s.s3_bucket, Key=key)
    return obj["Body"].read()


def object_exists(key: str) -> bool:
    s = get_settings()
    try:
        get_s3().head_object(Bucket=s.s3_bucket, Key=key)
        return True
    except ClientError:
        return False


def list_keys(prefix: str = "") -> Iterator[str]:
    s = get_settings()
    paginator = get_s3().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s.s3_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def open_bytesio(key: str) -> io.BytesIO:
    return io.BytesIO(get_bytes(key))
