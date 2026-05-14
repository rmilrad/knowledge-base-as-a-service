import boto3
from botocore.config import Config

from app.config import settings

_client = None


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


async def upload_to_s3(key: str, data: bytes):
    client = _get_s3_client()
    client.put_object(Bucket=settings.s3_bucket_name, Key=key, Body=data)


async def download_from_s3(key: str) -> bytes:
    client = _get_s3_client()
    response = client.get_object(Bucket=settings.s3_bucket_name, Key=key)
    return response["Body"].read()


async def delete_from_s3(key: str):
    client = _get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket_name, Key=key)
