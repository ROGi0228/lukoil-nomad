from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from src.core.config import Settings
from src.services.storage.base import FileStorage


class S3Storage(FileStorage):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = aioboto3.Session()

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        async with self._session.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            aws_access_key_id=self._settings.s3_access_key,
            aws_secret_access_key=self._settings.s3_secret_key,
            region_name=self._settings.s3_region,
        ) as client:
            yield client

    async def ensure_bucket_exists(self) -> None:
        async with self._client() as client:
            try:
                await client.head_bucket(Bucket=self._settings.s3_bucket)
            except ClientError:
                await client.create_bucket(Bucket=self._settings.s3_bucket)

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        async with self._client() as client:
            await client.put_object(
                Bucket=self._settings.s3_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        return key

    async def download(self, key: str) -> bytes:
        async with self._client() as client:
            response = await client.get_object(Bucket=self._settings.s3_bucket, Key=key)
            body: bytes = await response["Body"].read()
            return body
