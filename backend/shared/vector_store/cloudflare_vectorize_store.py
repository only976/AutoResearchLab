from __future__ import annotations

from typing import Any

import httpx

from .base import VectorRecord


class CloudflareVectorizeStore:
    def __init__(self) -> None:
        import os

        self._account_id = (os.getenv("CF_ACCOUNT_ID") or "").strip()
        self._api_token = (os.getenv("CF_API_TOKEN") or "").strip()
        if not self._account_id or not self._api_token:
            raise RuntimeError("Missing CF_ACCOUNT_ID or CF_API_TOKEN for Cloudflare Vectorize")
        self._base = f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}/vectorize/v2/indexes"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_token}", "Content-Type": "application/json"}

    def ensure_collection(self, name: str, vector_size: int) -> None:
        # Cloudflare indexes are expected to be pre-created in dashboard.
        # This call is a lightweight existence check.
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self._base}/{name}", headers=self._headers())
        if resp.status_code >= 400:
            raise RuntimeError(f"Vectorize index not ready: {name}, status={resp.status_code}, body={resp.text[:300]}")

    def reset_collection(self, name: str, vector_size: int) -> None:
        # No destructive reset here; caller should use unique IDs (upsert overwrite).
        self.ensure_collection(name, vector_size)

    def upsert(self, name: str, records: list[VectorRecord]) -> None:
        payload = {
            "vectors": [
                {"id": r.id, "values": r.vector, "metadata": r.payload}
                for r in records
            ]
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{self._base}/{name}/upsert", headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Vectorize upsert failed: {resp.status_code} {resp.text[:400]}")

    def query(self, name: str, vector: list[float], limit: int) -> list[dict[str, Any]]:
        payload = {"vector": vector, "topK": int(limit), "returnMetadata": True}
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{self._base}/{name}/query", headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Vectorize query failed: {resp.status_code} {resp.text[:400]}")
        data = resp.json() if resp.text else {}
        matches = (((data or {}).get("result") or {}).get("matches") or [])
        return [{"payload": (m.get("metadata") or {})} for m in matches]
