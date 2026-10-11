"""Retrieval interface (FR-3, FR-4). Every retriever, from the metadata baseline to
embedding similarity, implements `Retriever`, so evals and the loop can swap them freely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Query:
    brief: str = ""
    conditions: dict[str, str] = field(default_factory=dict)  # period, material, motif, department
    anchor_id: str | None = None  # "<source>:<object_id>"; "more like this"
    avoid: list[str] = field(default_factory=list)  # record IDs or terms to exclude
    k: int = 12


@dataclass(frozen=True)
class Hit:
    record_id: str
    score: float
    matched: tuple[str, ...]  # evidence: which attributes or features produced the score
    union_size: int = 0


@runtime_checkable
class Retriever(Protocol):
    def search(self, query: Query) -> list[Hit]: ...
