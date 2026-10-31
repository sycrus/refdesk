"""Corpus snapshots: pin a golden set to an ID list so the store can grow (#151, ADR-023)."""

from datetime import UTC, datetime

import pytest

from refdesk.evals.corpus import (
    CorpusMismatch,
    ensure_snapshot,
    load_snapshot,
    pin,
    record_digest,
    snapshot_path,
    write_snapshot,
)
from refdesk.evals.golden import corpus_version
from refdesk.retrieval import Query
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 11, tzinfo=UTC)


def rec(object_id, tags=("Flowers",), status=RightsStatus.OPEN, checked=CHECKED, **fields):
    rights = RightsRecord(
        source="met",
        object_id=object_id,
        flag_field="isPublicDomain",
        flag_value=status is RightsStatus.OPEN,
        licence_string=None,
        checked_at=checked,
        status=status,
    )
    return ArtworkRecord(
        id=f"met:{object_id}",
        source="met",
        object_id=object_id,
        title=fields.pop("title", f"Work {object_id}"),
        subject_tags=tuple(tags),
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
        **fields,
    )


PINNED = [rec("1"), rec("2"), rec("3", status=RightsStatus.PERMISSION_REQUIRED)]
VERSION = corpus_version(PINNED)


@pytest.fixture
def snapshots(tmp_path):
    write_snapshot(PINNED, tmp_path)
    return tmp_path


def test_file_name_is_the_corpus_version_without_colons(tmp_path):
    # Colons are not allowed in Windows file names.
    path = snapshot_path("met:2588:d188937d8a53", tmp_path)
    assert path.name == "met-2588-d188937d8a53.tsv"


def test_snapshot_round_trips_and_its_ids_hash_to_the_corpus_version(snapshots):
    rows = load_snapshot(snapshot_path(VERSION, snapshots))
    assert sorted(rows) == ["met:1", "met:2", "met:3"]
    assert rows["met:3"].rights_status == RightsStatus.PERMISSION_REQUIRED.value
    assert rows["met:1"].digest == record_digest(PINNED[0])


def test_a_snapshot_whose_ids_do_not_match_its_name_is_refused(snapshots):
    path = snapshot_path(VERSION, snapshots)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")  # drop one record
    with pytest.raises(CorpusMismatch, match="hash"):
        load_snapshot(path)


def test_writing_is_idempotent_but_never_overwrites_a_different_snapshot(snapshots):
    path = snapshot_path(VERSION, snapshots)
    before = path.read_bytes()
    assert write_snapshot(PINNED, snapshots) == path
    assert path.read_bytes() == before
    changed = [rec("1", title="Retitled"), *PINNED[1:]]  # same IDs, so the same name
    with pytest.raises(FileExistsError):
        write_snapshot(changed, snapshots)


def test_pin_filters_to_the_snapshot_and_counts_new_records(snapshots):
    pinned = pin([*PINNED, rec("4"), rec("5")], VERSION, snapshots)
    assert [r.id for r in pinned.records] == ["met:1", "met:2", "met:3"]
    assert pinned.extra == 2
    assert pinned.content_changed == []
    assert pinned.drift == ""
    assert corpus_version(pinned.records) == VERSION


def test_no_snapshot_file_is_refused(tmp_path):
    with pytest.raises(CorpusMismatch, match="no snapshot"):
        pin(PINNED, VERSION, tmp_path)


def test_a_pinned_record_missing_from_the_store_is_refused_by_name(snapshots):
    with pytest.raises(CorpusMismatch, match="met:2"):
        pin([PINNED[0], PINNED[2]], VERSION, snapshots)


def test_a_rights_change_on_a_pinned_record_is_refused(snapshots):
    # A flip can turn an expected reference into one that must not be shown.
    flipped = rec("1", status=RightsStatus.PERMISSION_REQUIRED)
    with pytest.raises(CorpusMismatch, match="met:1"):
        pin([flipped, *PINNED[1:]], VERSION, snapshots)


def test_other_field_changes_warn_and_change_the_drift_digest(snapshots):
    retitled = rec("2", title="A new attribution")
    pinned = pin([PINNED[0], retitled, PINNED[2]], VERSION, snapshots)
    assert pinned.content_changed == ["met:2"]
    assert pinned.drift
    assert any("met:2" in note for note in pinned.notes())


def test_a_recheck_of_rights_alone_is_not_drift(snapshots):
    # Re-ingest stamps a new checked_at; the status the source states is what matters.
    rechecked = rec("1", checked=datetime(2026, 10, 31, tzinfo=UTC))
    pinned = pin([rechecked, *PINNED[1:]], VERSION, snapshots)
    assert pinned.content_changed == []


def test_retrievers_built_on_pinned_records_never_rank_new_works(snapshots):
    store = [*PINNED, rec("9", tags=("Flowers", "Flowers"))]
    pinned = pin(store, VERSION, snapshots)
    hits = JaccardRetriever(pinned.records).search(Query(brief="flowers", k=10))
    assert "met:9" not in {h.record_id for h in hits}


class TestEnsureSnapshot:
    """At freeze, a golden set's snapshot must exist (decision 3 on #151)."""

    def test_an_existing_snapshot_is_kept_even_if_the_store_has_grown(self, snapshots):
        path = ensure_snapshot(VERSION, [*PINNED, rec("4")], snapshots)
        assert path == snapshot_path(VERSION, snapshots)

    def test_a_missing_snapshot_is_written_from_a_store_that_matches(self, tmp_path):
        assert ensure_snapshot(VERSION, PINNED, tmp_path).exists()

    def test_a_missing_snapshot_cannot_be_rebuilt_from_a_grown_store(self, tmp_path):
        with pytest.raises(CorpusMismatch, match="cannot be rebuilt"):
            ensure_snapshot(VERSION, [*PINNED, rec("4")], tmp_path)
