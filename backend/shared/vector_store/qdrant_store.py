from __future__ import annotations

from typing import Any

from loguru import logger

from .base import VectorRecord


class QdrantVectorStore:
    def __init__(self, *, local_path: str | None = None):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._Distance = Distance
        self._VectorParams = VectorParams
        self._client = None

        import os

        cloud_url = os.getenv("QDRANT_URL")
        cloud_key = os.getenv("QDRANT_API_KEY")
        if cloud_url and cloud_key:
            self._client = QdrantClient(url=cloud_url, api_key=cloud_key, timeout=60)
            logger.info("Vector store provider: Qdrant Cloud")
        else:
            self._client = QdrantClient(path=local_path, timeout=60)
            logger.info("Vector store provider: Qdrant local path={}", local_path)

    def ensure_collection(self, name: str, vector_size: int) -> None:
        if not self._client.collection_exists(name):
            self._client.create_collection(
                collection_name=name,
                vectors_config=self._VectorParams(size=vector_size, distance=self._Distance.COSINE),
            )

    def reset_collection(self, name: str, vector_size: int) -> None:
        try:
            if self._client.collection_exists(name):
                self._client.delete_collection(name)
        except Exception:
            pass
        self.ensure_collection(name, vector_size)

    def upsert(self, name: str, records: list[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=r.id, vector=r.vector, payload=r.payload)
            for r in records
        ]
        self._client.upsert(collection_name=name, points=points)

    def query(self, name: str, vector: list[float], limit: int) -> list[dict[str, Any]]:
        result = self._client.query_points(collection_name=name, query_vector=vector, limit=limit)
        out: list[dict[str, Any]] = []
        for p in result.points:
            out.append({"payload": p.payload or {}})
        return out
