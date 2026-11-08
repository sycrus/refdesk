"""scripts/build_labelling_pools.py never rebuilds a sheet Joe has labelled (issue #15)."""

import csv

import pytest
from build_labelling_pools import has_labels

FIELDS = ["draft_id", "candidate", "relevant", "grade", "note"]


def sheet(tmp_path, **labels):
    path = tmp_path / "blind-sheet.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow({"draft_id": "d02", "candidate": "met:1", "relevant": "", "grade": "",
                         "note": ""})  # fmt: skip
        writer.writerow({"draft_id": "d02", "candidate": "met:2"} | dict.fromkeys(FIELDS[2:], "")
                        | labels)  # fmt: skip
    return path


def test_no_sheet_and_an_empty_sheet_may_be_built(tmp_path):
    assert not has_labels(tmp_path / "missing.csv")
    assert not has_labels(sheet(tmp_path))


@pytest.mark.parametrize("labels", [{"relevant": "n"}, {"grade": "1"}, {"note": "close"}])
def test_any_label_blocks_a_rebuild(tmp_path, labels):
    assert has_labels(sheet(tmp_path, **labels))


# --- Round-2 batches (ADR-018 amendment 2026-11-08) ------------------------------------

from build_labelling_pools import batch_blind_ids, batch_paths  # noqa: E402


def draft(draft_id, decision="retrieve"):
    return {"draft_id": draft_id, "expected_decision": decision, "detail": "sparse"}


def test_batch_files_are_named_after_the_batch():
    paths = batch_paths("b2")
    assert paths.drafts.name == "briefs-draft-b2.jsonl"
    assert paths.cases.name == "blind-cases-b2.json"
    assert paths.sheet.name == "blind-sheet-b2.csv"
    assert paths.sources.name == "pool-sources-b2.jsonl"
    assert paths.sources.parent.name == "labelling-v1"  # gitignored runs/, not the repo


def test_round_one_keeps_its_file_names():
    paths = batch_paths(None)
    assert (paths.drafts.name, paths.sheet.name) == ("briefs-draft.jsonl", "blind-sheet.csv")


def test_every_retrieve_draft_in_a_batch_is_blind():
    drafts = [draft("d46"), draft("d47"), draft("d48", "decline")]
    assert batch_blind_ids(drafts, existing=["d01"]) == ["d46", "d47"]


def test_a_batch_may_not_reuse_a_round_one_id():
    with pytest.raises(ValueError, match="d01"):
        batch_blind_ids([draft("d01"), draft("d46")], existing=["d01", "d02"])
