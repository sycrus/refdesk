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
