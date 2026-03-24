from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict[str, Any]


class VectorStore(Protocol):
    def ensure_collection(self, name: str, vector_size: int) -> None:
        ...

    def reset_collection(self, name: str, vector_size: int) -> None:
        ...

    def upsert(self, name: str, records: list[VectorRecord]) -> None:
        ...

    def query(self, name: str, vector: list[float], limit: int) -> list[dict[str, Any]]:
        ...
