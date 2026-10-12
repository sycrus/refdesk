"""Retrieval interface (FR-3, FR-4). Every retriever, from the metadata baseline to
embedding similarity, implements `Retriever`, so evals and the loop can swap them freely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from refdesk.schema import ArtworkRecord, RightsStatus

UsageMode = Literal["reference_only", "reproduction"]


@dataclass(frozen=True)
class Query:
    brief: str = ""
    conditions: dict[str, str] = field(default_factory=dict)  # period, material, motif, department
    anchor_id: str | None = None  # "<source>:<object_id>"; "more like this"
    avoid: list[str] = field(default_factory=list)  # record IDs or terms to exclude
    k: int = 12
    usage_mode: UsageMode = "reference_only"

    def __post_init__(self) -> None:
        if self.usage_mode not in ("reference_only", "reproduction"):
            raise ValueError(f"unknown usage_mode {self.usage_mode!r}")


@dataclass(frozen=True)
class Hit:
    record_id: str
    score: float
    matched: tuple[str, ...]  # evidence: which attributes or features produced the score
    union_size: int = 0
    # Named contributions that sum to `score`, e.g. (("similarity", 0.3), ("attributes", 0.13)).
    # Empty for single-signal retrievers, whose score is the one signal.
    components: tuple[tuple[str, float], ...] = ()


def allowed(record: ArtworkRecord, query: Query) -> bool:
    """Rights filter every retriever applies. In reproduction mode only works the source
    states are open may be returned (PRD 5, 9). Reference-only mode shows every status;
    the UI badges say which can be reused."""
    if query.usage_mode == "reproduction":
        return record.rights.status is RightsStatus.OPEN
    return True


@runtime_checkable
class Retriever(Protocol):
    def search(self, query: Query) -> list[Hit]: ...
