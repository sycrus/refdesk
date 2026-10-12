"""The browser tests' store: built offline from the recorded Met fixtures (issue #46)."""

import make_e2e_store

from refdesk.store import Store
from refdesk.wording import RightsStatus


def test_builds_a_store_from_the_fixtures(tmp_path):
    path = tmp_path / "e2e.sqlite"
    make_e2e_store.build(path)
    store = Store(path)
    try:
        records = {r.id: r for r in store.iter_records()}
    finally:
        store.close()
    assert set(records) == {"met:436535", "met:490190", "met:492759"}
    assert records["met:436535"].rights.status == RightsStatus.OPEN
    # The rights check time is when the fixture was recorded, not invented.
    assert records["met:436535"].rights.checked_at.isoformat() == "2026-10-11T11:16:44+00:00"


def test_rebuilding_starts_from_scratch(tmp_path):
    path = tmp_path / "e2e.sqlite"
    make_e2e_store.build(path)
    make_e2e_store.build(path)
    store = Store(path)
    try:
        assert store.count_records() == 3
    finally:
        store.close()
