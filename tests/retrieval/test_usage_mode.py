"""Reproduction mode returns only open works, for every retriever (issue #35, PRD 5, 9)."""

from datetime import UTC, datetime

import numpy as np
import pytest

from refdesk.embeddings import EmbeddingIndex
from refdesk.retrieval import Query
from refdesk.retrieval.registry import RETRIEVERS, Resources, build_retriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 11, tzinfo=UTC)


def rec(object_id, status):
    flag = status is not RightsStatus.UNVERIFIED
    rights = RightsRecord(
        source="met",
        object_id=object_id,
        flag_field="isPublicDomain" if flag else None,
        flag_value=(status is RightsStatus.OPEN) if flag else None,
        licence_string=None,
        checked_at=CHECKED,
        status=status,
    )
    return ArtworkRecord(
        id=f"met:{object_id}",
        source="met",
        object_id=object_id,
        classification="Paintings",
        subject_tags=("Boats",),
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


RECORDS = [
    rec("1", RightsStatus.OPEN),
    rec("2", RightsStatus.PERMISSION_REQUIRED),
    rec("3", RightsStatus.UNVERIFIED),
]


class SameDirectionEmbedder:
    """Every text points the same way, so every record matches."""

    def embed_texts(self, texts):
        return np.ones((len(texts), 2), dtype=np.float32)


# Fake resources: an image vector for every record, so the rights filter is what decides.
FAKES = Resources(
    load_index=lambda: EmbeddingIndex([r.id for r in RECORDS], np.ones((3, 2), np.float32)),
    load_embedder=SameDirectionEmbedder,
)


@pytest.mark.parametrize("name", sorted(RETRIEVERS))
def test_reproduction_returns_only_open_works(name):
    retriever = build_retriever(name, RECORDS, FAKES)
    hits = retriever.search(Query(brief="boats", usage_mode="reproduction"))
    assert [h.record_id for h in hits] == ["met:1"]


@pytest.mark.parametrize("name", sorted(RETRIEVERS))
def test_reference_only_returns_every_rights_status(name):
    retriever = build_retriever(name, RECORDS, FAKES)
    hits = retriever.search(Query(brief="boats", usage_mode="reference_only"))
    assert {h.record_id for h in hits} == {"met:1", "met:2", "met:3"}


def test_default_usage_mode_is_reference_only():
    assert Query().usage_mode == "reference_only"


def test_unknown_usage_mode_is_rejected():
    with pytest.raises(ValueError):
        Query(usage_mode="print it anyway")
