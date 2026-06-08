from __future__ import annotations

import logging

import httpx

from .base import StorageError

logger = logging.getLogger(__name__)


class SupabaseObjectStorage:
    """
    Thin client over the Supabase Storage REST API. Authenticates with the
    service-role key so the backend can read/write any bucket regardless of
    row-level security.

    `ensure_ready()` creates the bucket on first boot if it doesn't exist.
    """

    def __init__(
        self, base_url: str, service_key: str, bucket: str, timeout_s: float = 30.0
    ) -> None:
        self._base = base_url.rstrip("/")
        self._bucket = bucket
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        }
        self._timeout = timeout_s

    async def ensure_ready(self) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.get(
                f"{self._base}/bucket/{self._bucket}", headers=self._headers
            )
            if resp.status_code == 200:
                return
            if resp.status_code not in (404, 400):
                raise StorageError(
                    f"bucket probe failed: {resp.status_code} {resp.text}"
                )
            create = await c.post(
                f"{self._base}/bucket",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"name": self._bucket, "public": False},
            )
            if create.status_code not in (200, 201, 409):
                raise StorageError(
                    f"bucket create failed: {create.status_code} {create.text}"
                )
            logger.info("created Supabase Storage bucket '%s'", self._bucket)

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.post(
                f"{self._base}/object/{self._bucket}/{path}",
                headers={
                    **self._headers,
                    "Content-Type": content_type,
                    "x-upsert": "true",
                },
                content=data,
            )
            if resp.status_code not in (200, 201):
                raise StorageError(f"upload failed: {resp.status_code} {resp.text}")

    async def get(self, path: str) -> bytes:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.get(
                f"{self._base}/object/authenticated/{self._bucket}/{path}",
                headers=self._headers,
            )
            if resp.status_code != 200:
                raise StorageError(f"download failed: {resp.status_code} {resp.text}")
            return resp.content

    async def delete(self, path: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.delete(
                f"{self._base}/object/{self._bucket}/{path}",
                headers=self._headers,
            )
            if resp.status_code not in (200, 204, 404):
                raise StorageError(f"delete failed: {resp.status_code} {resp.text}")
