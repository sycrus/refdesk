"""Local blind-labelling page for golden-v1 (issue #138, supports #15; ADR-018).

The page only records Joe's labels: it writes the sheet's relevant/grade/note columns and
nothing else, shows no rank or retriever, and serves images from the local cache of open
works only.
"""

import csv
import hashlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from refdesk.evals.label_app import (
    LabelError,
    apply_label,
    create_app,
    read_sheet,
    start_pass2,
    write_sheet,
)
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus
from refdesk.store import Store

FIELDS = [
    "draft_id", "brief", "usage_mode", "candidate", "title", "artist", "date", "medium",
    "subjects", "record_url", "image_url", "relevant", "grade", "note",
]  # fmt: skip


def row(candidate, draft="d02", **labels):
    base = {f: "" for f in FIELDS} | {
        "draft_id": draft, "brief": "Boats at sea", "usage_mode": "reference_only",
        "candidate": candidate, "title": f"Title {candidate}", "artist": "Corot",
        "date": "ca. 1865", "medium": "Oil on canvas", "subjects": "Landscapes, Boats",
        "record_url": "https://www.metmuseum.org/art/collection/search/1",
        "image_url": "https://images.metmuseum.org/x.jpg",
    }  # fmt: skip
    return base | labels


@pytest.fixture
def sheet(tmp_path):
    path = tmp_path / "blind-sheet.csv"
    rows = [row("met:1"), row("met:2", relevant="y", grade="2", note="close call"), row("met:3")]
    write_sheet(path, FIELDS, rows)
    return path


def record(object_id, status=RightsStatus.OPEN):
    rights = RightsRecord(
        source="met", object_id=object_id, flag_field="isPublicDomain",
        flag_value=status is RightsStatus.OPEN, licence_string=None,
        checked_at=datetime(2026, 10, 27, tzinfo=UTC), status=status,
    )  # fmt: skip
    return ArtworkRecord(
        id=f"met:{object_id}", source="met", object_id=object_id,
        raw_record_ref=f"met/objects/{object_id}.json", rights=rights,
    )  # fmt: skip


@pytest.fixture
def client(tmp_path, sheet):
    images = tmp_path / "images"
    (images / "met").mkdir(parents=True)
    with Store(tmp_path / "db.sqlite") as store:
        for object_id, status in [
            ("1", RightsStatus.OPEN),
            ("2", RightsStatus.PERMISSION_REQUIRED),
        ]:
            store.save(record(object_id, status), {})
            data = f"jpeg:{object_id}".encode()
            (images / "met" / f"{object_id}.jpg").write_bytes(data)
            store.save_image(
                f"met:{object_id}", "u", f"met/{object_id}.jpg",
                hashlib.sha256(data).hexdigest(), len(data),
            )  # fmt: skip
    return TestClient(create_app(sheet, tmp_path / "db.sqlite", images))


class TestApplyLabel:
    def test_not_relevant_clears_the_grade(self):
        assert apply_label(row("met:1", relevant="y", grade="2"), "n", "", "")["grade"] == ""

    def test_a_grade_needs_relevant_yes(self):
        with pytest.raises(LabelError, match="grade"):
            apply_label(row("met:1"), "n", "2", "")

    @pytest.mark.parametrize("relevant, grade", [("maybe", ""), ("y", "3")])
    def test_rejects_values_the_sheet_does_not_use(self, relevant, grade):
        with pytest.raises(LabelError):
            apply_label(row("met:1"), relevant, grade, "")

    def test_relevant_without_a_grade_yet_is_kept(self):
        # Pressing y then 1 or 2 saves twice; the first save has no grade yet.
        assert apply_label(row("met:1"), "y", "", "")["relevant"] == "y"

    def test_a_note_stays_on_one_line(self):
        assert apply_label(row("met:1"), "n", "", "too\r\nmodern ")["note"] == "too modern"

    def test_only_the_label_columns_change(self):
        before = row("met:1")
        after = apply_label(before, "y", "1", "sky only")
        changed = {k for k in FIELDS if before[k] != after[k]}
        assert changed == {"relevant", "grade", "note"}


class TestSheet:
    def test_round_trip_keeps_columns_and_line_endings(self, sheet):
        fields, rows = read_sheet(sheet)
        assert fields == FIELDS and rows[1]["note"] == "close call"
        assert b"\r\n" not in sheet.read_bytes()

    def test_pass2_copies_the_rows_with_labels_cleared(self, sheet, tmp_path):
        out = tmp_path / "blind-sheet-pass2.csv"
        start_pass2(sheet, out)
        fields, rows = read_sheet(out)
        assert [r["candidate"] for r in rows] == ["met:1", "met:2", "met:3"]
        assert all(r["relevant"] == r["grade"] == r["note"] == "" for r in rows)

    def test_pass2_never_overwrites(self, sheet, tmp_path):
        out = tmp_path / "blind-sheet-pass2.csv"
        start_pass2(sheet, out)
        with pytest.raises(FileExistsError):
            start_pass2(sheet, out)


class TestApp:
    def test_rows_show_no_rank_retriever_or_image_url(self, client):
        rows = client.get("/api/rows").json()["rows"]
        assert [r["index"] for r in rows] == [0, 1, 2]
        assert not {"rank", "retriever", "source", "sources", "image_url"} & set(rows[0])
        assert rows[1]["relevant"] == "y" and rows[1]["note"] == "close call"

    def test_a_label_is_written_to_the_sheet_at_once(self, client, sheet):
        r = client.put("/api/rows/0", json={"candidate": "met:1", "relevant": "y", "grade": "2"})
        assert r.status_code == 200
        _, rows = read_sheet(sheet)
        assert (rows[0]["relevant"], rows[0]["grade"]) == ("y", "2")
        assert rows[1]["note"] == "close call"  # other rows untouched

    def test_a_label_for_a_row_that_moved_is_refused(self, client, sheet):
        # Guards against the sheet being rebuilt or reordered while the page is open.
        r = client.put("/api/rows/0", json={"candidate": "met:3", "relevant": "n"})
        assert r.status_code == 409
        assert read_sheet(sheet)[1][0]["relevant"] == ""

    def test_an_invalid_label_is_refused_and_not_written(self, client, sheet):
        r = client.put("/api/rows/0", json={"candidate": "met:1", "relevant": "n", "grade": "2"})
        assert r.status_code == 422
        assert read_sheet(sheet)[1][0]["relevant"] == ""

    def test_the_cached_image_of_an_open_work_is_served(self, client):
        r = client.get("/image/0")
        assert r.status_code == 200 and r.content == b"jpeg:1"

    def test_no_image_for_a_work_that_is_not_open(self, client):
        assert client.get("/image/1").status_code == 404

    def test_no_image_when_nothing_is_cached(self, client):
        assert client.get("/image/2").status_code == 404

    def test_the_page_loads(self, client):
        r = client.get("/")
        assert r.status_code == 200 and "Blind labelling" in r.text


def test_written_sheet_is_plain_csv(sheet):
    with sheet.open(encoding="utf-8", newline="") as f:
        assert next(csv.reader(f)) == FIELDS


class TestToken:
    """Off localhost (e.g. over Tailscale) every request needs the startup token."""

    @pytest.fixture
    def app(self, tmp_path, sheet):
        return create_app(sheet, tmp_path / "db.sqlite", tmp_path / "images", token="s3cret")

    def test_no_token_no_page_and_no_labels(self, app, sheet):
        c = TestClient(app)
        assert c.get("/").status_code == 401
        assert c.get("/api/rows").status_code == 401
        assert c.put("/api/rows/0", json={"candidate": "met:1", "relevant": "n"}).status_code == 401
        assert read_sheet(sheet)[1][0]["relevant"] == ""

    def test_a_wrong_token_is_refused(self, app):
        assert TestClient(app).get("/?t=guess").status_code == 401

    def test_the_token_in_the_url_is_kept_in_a_cookie(self, app):
        c = TestClient(app)
        assert c.get("/?t=s3cret").status_code == 200
        assert c.get("/api/rows").status_code == 200  # the page's own calls carry no token
