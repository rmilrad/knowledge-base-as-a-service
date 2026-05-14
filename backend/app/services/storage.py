import logging
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.config import settings

logger = logging.getLogger("kbaas.storage")

_client = None
_use_local = False
_local_dir = Path(__file__).resolve().parent.parent.parent / "local_storage"


def _get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
    return _client


def _check_s3() -> bool:
    """Check if S3/MinIO is reachable. Cache the result."""
    global _use_local
    try:
        client = _get_s3_client()
        client.head_bucket(Bucket=settings.s3_bucket_name)
        logger.info("S3/MinIO is available")
        return True
    except (ClientError, EndpointConnectionError, Exception) as e:
        logger.warning(f"S3/MinIO not available ({e}), using local filesystem storage")
        _use_local = True
        return False


# Try S3 on first import, fall back to local
_check_s3()


def _local_path(key: str) -> Path:
    p = _local_dir / key
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


async def upload_to_s3(key: str, data: bytes):
    if _use_local:
        p = _local_path(key)
        p.write_bytes(data)
        logger.info(f"Stored locally: {p} ({len(data)} bytes)")
        return

    try:
        client = _get_s3_client()
        client.put_object(Bucket=settings.s3_bucket_name, Key=key, Body=data)
        logger.info(f"Uploaded to S3: {key} ({len(data)} bytes)")
    except Exception as e:
        logger.error(f"S3 upload failed for {key}: {e}")
        # Fall back to local storage
        p = _local_path(key)
        p.write_bytes(data)
        logger.info(f"Fell back to local storage: {p}")


async def download_from_s3(key: str) -> bytes:
    if _use_local:
        p = _local_path(key)
        if not p.exists():
            raise FileNotFoundError(f"Local file not found: {p}")
        data = p.read_bytes()
        logger.info(f"Read from local storage: {p} ({len(data)} bytes)")
        return data

    try:
        client = _get_s3_client()
        response = client.get_object(Bucket=settings.s3_bucket_name, Key=key)
        data = response["Body"].read()
        logger.info(f"Downloaded from S3: {key} ({len(data)} bytes)")
        return data
    except Exception as e:
        logger.error(f"S3 download failed for {key}: {e}")
        # Try local fallback
        p = _local_path(key)
        if p.exists():
            return p.read_bytes()
        raise


async def delete_from_s3(key: str):
    if _use_local:
        p = _local_path(key)
        if p.exists():
            p.unlink()
            logger.info(f"Deleted local file: {p}")
        return

    try:
        client = _get_s3_client()
        client.delete_object(Bucket=settings.s3_bucket_name, Key=key)
        logger.info(f"Deleted from S3: {key}")
    except Exception as e:
        logger.error(f"S3 delete failed for {key}: {e}")
