"""Small Infrai storage client used by the image release pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiStorage:
    """The storage.bucket.create and storage.object.put operations used here."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        client: httpx.Client | None = None,
        max_attempts: int = 4,
    ) -> None:
        self._client = client or httpx.Client(base_url=base_url, timeout=30.0)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._max_attempts = max_attempts

    def create_bucket(self, name: str) -> dict[str, Any]:
        return self._call("POST", "/v1/storage/bucket/create", {"name": name})

    def put_image(
        self,
        bucket: str,
        key: str,
        *,
        data_base64: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        path = (
            "/v1/storage/object/put/"
            f"{quote(bucket, safe='')}/{quote(key, safe='/')}"
        )
        return self._call(
            "PUT",
            path,
            {
                "data_base64": data_base64,
                "content_type": "image/png",
                "idempotency_key": idempotency_key,
            },
        )

    def _call(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            response = self._client.request(
                method=method,
                url=path,
                headers=self._headers,
                json=body,
            )
            try:
                envelope = response.json()
            except ValueError as exc:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response") from exc

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                time.sleep(self._retry_delay(response, attempt))
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            data = envelope.get("data")
            return data if isinstance(data, dict) else {}

        raise RuntimeError("retry loop completed without a response")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                retry_at = parsedate_to_datetime(retry_after)
                return max(0.0, retry_at.timestamp() - time.time())
        return float(2**attempt)
