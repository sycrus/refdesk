"""Image cache for open works only (issue #31, PRD 9, CLAUDE.md hard rules)."""

import hashlib
from datetime import UTC, datetime

import pytest

from refdesk.images import cache_images
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus
from refdesk.sources import met
from refdesk.store import Store

CHECKED = datetime(2026, 10, 11, tzinfo=UTC)
IMG = "https://images.metmuseum.org/CRDImages/ep/web-large/{}.jpg"


def rec(object_id, status=RightsStatus.OPEN, image=True):
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
        image_url=IMG.format(object_id) if image else None,
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


class BytesTransport:
    def __init__(self, fail=()):
        self.fetched = []
        self.fail = set(fail)

    def get_json(self, url):
        raise AssertionError("no JSON calls expected")

    def get_bytes(self, url):
        self.fetched.append(url)
        if any(f in url for f in self.fail):
            return 503, b""
        return 200, f"jpeg:{url}".encode()


def client(transport):
    return met.MetClient(transport, min_interval=0, max_retries=0, sleep=lambda s: None)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "db.sqlite") as s:
        for r in [
            rec("1"),
            rec("2"),
            rec("3", RightsStatus.PERMISSION_REQUIRED, image=False),
            rec("4", RightsStatus.UNVERIFIED, image=False),
            rec("5", image=False),  # open, but the source gave no image
        ]:
            s.save(r, {"objectID": int(r.object_id)})
        yield s


class TestOnlyOpenWorks:
    def test_downloads_only_open_records_with_an_image(self, store, tmp_path):
        transport = BytesTransport()
        result = cache_images(store, client(transport), tmp_path / "images")
        assert transport.fetched == [IMG.format("1"), IMG.format("2")]
        assert result.downloaded == 2
        assert result.skipped == {"not_open": 2, "no_image_url": 1}

    def test_a_non_open_record_with_an_image_url_is_still_not_downloaded(self, store, tmp_path):
        # Defence in depth: even if a non-open record carried an image URL, never fetch it.
        bad = rec("6", RightsStatus.PERMISSION_REQUIRED).model_copy(
            update={"image_url": IMG.format("6")}
        )
        store.save(bad, {"objectID": 6})
        transport = BytesTransport()
        cache_images(store, client(transport), tmp_path / "images")
        assert IMG.format("6") not in transport.fetched


class TestResumable:
    def test_rerun_fetches_nothing_new(self, store, tmp_path):
        cache_images(store, client(BytesTransport()), tmp_path / "images")
        again = BytesTransport()
        result = cache_images(store, client(again), tmp_path / "images")
        assert again.fetched == []
        assert result.downloaded == 0 and result.already_cached == 2

    def test_a_missing_file_is_fetched_again(self, store, tmp_path):
        cache_images(store, client(BytesTransport()), tmp_path / "images")
        (tmp_path / "images" / "met" / "1.jpg").unlink()
        again = BytesTransport()
        cache_images(store, client(again), tmp_path / "images")
        assert again.fetched == [IMG.format("1")]

    def test_failure_stops_and_keeps_progress(self, store, tmp_path):
        with pytest.raises(met.MetUnavailable):
            cache_images(store, client(BytesTransport(fail={"/2.jpg"})), tmp_path / "images")
        assert store.image_path("met:1") is not None
        assert store.image_path("met:2") is None


class TestStoredImage:
    def test_file_and_hash_are_recorded(self, store, tmp_path):
        cache_images(store, client(BytesTransport()), tmp_path / "images")
        path = tmp_path / "images" / "met" / "1.jpg"
        assert path.read_bytes() == f"jpeg:{IMG.format('1')}".encode()
        row = store.get_image("met:1")
        assert row["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert row["url"] == IMG.format("1")

    def test_limit(self, store, tmp_path):
        transport = BytesTransport()
        result = cache_images(store, client(transport), tmp_path / "images", limit=1)
        assert len(transport.fetched) == 1
        # Totals still cover every record, not just those seen before the limit.
        assert result.skipped == {"not_open": 2, "no_image_url": 1, "over_limit": 1}


class TestImageHost:
    def test_refuses_a_url_off_the_met_image_host(self):
        c = client(BytesTransport())
        with pytest.raises(ValueError, match="not a Met image host"):
            c.get_bytes("https://example.org/x.jpg")
        with pytest.raises(ValueError):
            c.get_bytes("http://images.metmuseum.org/x.jpg")  # not https
