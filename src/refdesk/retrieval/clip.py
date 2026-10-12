"""Embedding retriever: the off-the-shelf similarity baseline (FR-4, issue #33).

The brief becomes a CLIP text vector; an anchor uses its own image vector (the anchor wins
if both are given). Hits are ranked by cosine similarity over the FAISS image index (#32).

Deliberately a plain baseline, in the spirit of ArtLens:
- Evidence is only the similarity score. Nothing is claimed about why an image matched.
- Conditions are ignored; combining them with similarity is #34.
- Only works with an image vector can be returned, which in practice means open works:
  images are cached only for open works (#31). That is a real limit of image similarity.

The rights filter (`allowed`) and the avoid list apply as for every retriever. Avoid terms
reuse the metadata baseline's matching, so "avoid Monet" means the same in both.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from refdesk.embeddings import Embedder, EmbeddingIndex
from refdesk.retrieval import Hit, Query, allowed
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord


class EmbeddingRetriever:
    def __init__(self, records: Iterable[ArtworkRecord], index: EmbeddingIndex, embedder: Embedder):
        self.records = {r.id: r for r in records}
        self.index = index
        self.embedder = embedder
        self._terms = JaccardRetriever(self.records.values())  # avoid-term matching only

    def _query_vector(self, query: Query) -> np.ndarray | None:
        if query.anchor_id is not None:
            if query.anchor_id not in self.index:
                raise KeyError(query.anchor_id)
            return self.index.vector(query.anchor_id)
        if query.brief.strip():
            return self.embedder.embed_texts([query.brief])[0]
        return None

    def _excluded(self, query: Query) -> set[str]:
        excluded = self._terms.excluded(query)
        if query.anchor_id is not None:
            excluded.add(query.anchor_id)
        return excluded

    def search(self, query: Query) -> list[Hit]:
        vector = self._query_vector(query)
        if vector is None:
            return []
        excluded = self._excluded(query)
        hits = []
        # Exact search over the whole index is instant at this size, and keeps filtering
        # simple: rank everything, then drop excluded or not-allowed records.
        for record_id, score in self.index.search(vector, k=len(self.index.ids)):
            record = self.records.get(record_id)
            if record is None or record_id in excluded or not allowed(record, query):
                continue
            hits.append(Hit(record_id, score, (f"clip_cosine:{score:.3f}",)))
        # Ties (equal to 6 decimals, below float32 noise) break by record ID, so rankings
        # are deterministic, as in the metadata baseline.
        hits.sort(key=lambda h: (-round(h.score, 6), h.record_id))
        return hits[: query.k]
