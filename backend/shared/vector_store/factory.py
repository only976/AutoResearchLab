from __future__ import annotations

import os
from pathlib import Path

from .cloudflare_vectorize_store import CloudflareVectorizeStore
from .qdrant_store import QdrantVectorStore


def create_vector_store(*, qdrant_local_path: Path | None = None):
    provider = (os.getenv("VECTOR_STORE_PROVIDER") or "qdrant").strip().lower()
    if provider in {"cloudflare", "vectorize", "cloudflare_vectorize"}:
        return CloudflareVectorizeStore()
    path = str(qdrant_local_path) if qdrant_local_path else None
    return QdrantVectorStore(local_path=path)
