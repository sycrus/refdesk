"""Combined retriever: attributes plus embedding similarity in one weighted score (FR-3,
issue #34).

    score = w_similarity * cosine + w_attributes * jaccard

Every hit carries both terms in `Hit.components`, so a reviewer sees why it ranked where it
did (PRD 1A), e.g. similarity 0.6 x 0.52 = 0.312 plus attributes 0.4 x 0.29 = 0.118.
`matched` lists the shared attributes, the cosine, and any filters the record passed.

- cosine: as in the CLIP baseline (`clip.py`): brief text vector, or the anchor's image
  vector when there is an anchor.
- jaccard: as in the metadata baseline (`metadata.py`), over the boost attributes only.
- Conditions are `boost` (add to the attribute set; the default) or `filter` (a record must
  have the attribute, and it then adds nothing to the score), set per field in
  config/retrieval.yaml. Boost is the default because filtering silently drops records
  whose source leaves that field empty, which is common in Met data.
- Records with no image vector (in practice non-open works, #31) compete on attributes
  alone, with similarity 0 and "no image vector" in their evidence. An anchor without a
  vector contributes its attributes only.
- A record is a candidate if it has any evidence: an image vector to compare, a shared
  boost attribute, or a passed filter. A filter alone ranks at score 0, shown as such.

Known limit: CLIP text-to-image cosines sit around 0.15-0.35 while Jaccard spans 0-1, so the
weights also absorb a scale difference. The 0.6/0.4 default is an untuned placeholder; tune
it on golden-v1, never on the synthetic golden-v0.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from refdesk.embeddings import Embedder, EmbeddingIndex
from refdesk.retrieval import Hit, Query, allowed
from refdesk.retrieval.metadata import ACCEPTED_PERIODS, JaccardRetriever, condition_attributes
from refdesk.schema import ArtworkRecord

CONDITION_KEYS = ("period", "material", "motif", "department")  # PRD 8
COMPONENTS = ("similarity", "attributes")


class CombinedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    weights: dict[str, float]
    conditions: dict[str, Literal["boost", "filter"]] = {}

    @model_validator(mode="after")
    def _valid(self) -> CombinedConfig:
        if set(self.weights) != set(COMPONENTS):
            raise ValueError(f"weights must name exactly {COMPONENTS}")
        if any(w < 0 for w in self.weights.values()) or not sum(self.weights.values()):
            raise ValueError("weights must be non-negative and not all zero")
        if unknown := set(self.conditions) - set(CONDITION_KEYS):
            raise ValueError(f"unknown condition fields {sorted(unknown)}")
        return self

    def mode(self, key: str) -> str:
        return self.conditions.get(key, "boost")


def load_config(path: Path = Path("config/retrieval.yaml")) -> CombinedConfig:
    return CombinedConfig(**yaml.safe_load(path.read_text(encoding="utf-8"))["combined"])


class ConditionNotUnderstood(ValueError):
    """A condition that cannot be applied as asked (issue #63). Raised instead of being
    dropped, because a dropped filter makes results look filtered when they are not."""


def check_conditions(conditions: dict[str, str], config: CombinedConfig) -> None:
    """Every condition field must be one of PRD 8's, and every filter must turn into at
    least one attribute. A boost that gives nothing stays lenient: it only adds nothing.
    Needs no retriever, so the API can check a board before any model loads."""
    for key, value in conditions.items():
        if key not in CONDITION_KEYS:
            raise ConditionNotUnderstood(
                f"Unknown condition {key!r}. Conditions are {', '.join(CONDITION_KEYS)}."
            )
        if config.mode(key) == "filter" and not condition_attributes(key, value):
            formats = ACCEPTED_PERIODS if key == "period" else "a word found in the records"
            raise ConditionNotUnderstood(
                f"The {key} filter {value!r} cannot be applied. Use {formats}."
            )


class CombinedRetriever:
    def __init__(
        self,
        records: Iterable[ArtworkRecord],
        index: EmbeddingIndex,
        embedder: Embedder,
        config: CombinedConfig,
    ):
        self.records = {r.id: r for r in records}
        self.index = index
        self.embedder = embedder
        self.config = config
        self.terms = JaccardRetriever(self.records.values())

    def _query_vector(self, query: Query) -> np.ndarray | None:
        if query.anchor_id is not None:
            if query.anchor_id not in self.records:
                raise KeyError(query.anchor_id)
            return self.index.vector(query.anchor_id) if query.anchor_id in self.index else None
        if query.brief.strip():
            return self.embedder.embed_texts([query.brief])[0]
        return None

    def _split_conditions(self, query: Query) -> tuple[set[str], set[str]]:
        """Query attributes to boost, and attributes every record must have."""
        check_conditions(query.conditions, self.config)
        filters: set[str] = set()
        for key, value in query.conditions.items():
            if self.config.mode(key) == "filter":
                filters |= condition_attributes(key, value)
        boost = self.terms.query_attributes(query) - filters
        return boost, filters

    def _cosines(self, vector: np.ndarray | None) -> dict[str, float]:
        if vector is None:
            return {}
        return {rid: float(s) for rid, s in self.index.search(vector, k=len(self.index.ids))}

    def search(self, query: Query) -> list[Hit]:
        boost, filters = self._split_conditions(query)
        cosines = self._cosines(self._query_vector(query))
        if not (boost or filters or cosines):
            return []
        excluded = self.terms.excluded(query) | {query.anchor_id}
        w_sim, w_attr = self.config.weights["similarity"], self.config.weights["attributes"]
        hits = []
        for record_id, record in self.records.items():
            if record_id in excluded or not allowed(record, query):
                continue
            attrs = self.terms.attrs[record_id]
            if not filters <= attrs:
                continue
            shared = boost & attrs
            cosine = cosines.get(record_id)
            if not (shared or filters or cosine is not None):
                continue  # no evidence at all
            jaccard = len(shared) / len(boost | attrs) if shared else 0.0
            similarity = w_sim * (cosine or 0.0)
            attributes = w_attr * jaccard
            evidence = [*sorted(shared), *(f"filter:{a}" for a in sorted(filters))]
            if cosines:
                evidence.append(
                    f"clip_cosine:{cosine:.3f}" if cosine is not None else "no image vector"
                )
            hits.append(
                Hit(
                    record_id,
                    similarity + attributes,
                    tuple(evidence),
                    len(boost | attrs),
                    (("similarity", similarity), ("attributes", attributes)),
                )
            )
        # Ties (equal to 6 decimals, below float32 noise) break by record ID.
        hits.sort(key=lambda h: (-round(h.score, 6), h.record_id))
        return hits[: query.k]
