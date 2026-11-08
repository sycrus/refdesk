"""The demo bundle (issue #167, ADR-025, option A): recorded runs and the corpus metadata
committed as reviewable JSONL; images fetched at image build time from the source's own
host, for Open works only, each checked against the hash recorded when the run was made."""

import hashlib
import json

import pytest
from test_boards import RECORDS

from refdesk.api.models import BoardRequest
from refdesk.boards import BoardService, RunStore
from refdesk.demo import BundleError, build_store, export_bundle
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.store import Store

IMAGE = b"\xff\xd8 open work"
URL = "https://images.metmuseum.org/CRDImages/ep/original/1.jpg"
CLOSED_URL = "https://images.metmuseum.org/CRDImages/ep/original/2.jpg"


def service(db, runs_dir):
    return BoardService(
        RunStore(db), lambda: RECORDS, JaccardRetriever, "jaccard", runs_dir=runs_dir
    )


@pytest.fixture
def source(tmp_path):
    """A local store like the dev machine's: records with raw responses, a cached image
    for the Open work (and, wrongly, one for a permission-required work), one run."""
    db, runs_dir, images = tmp_path / "src.sqlite", tmp_path / "runs", tmp_path / "images"
    with Store(db) as store:
        for record in RECORDS:
            store.save(record, {"private": "raw museum response"})
        (images / "met").mkdir(parents=True)
        (images / "met" / "1.jpg").write_bytes(IMAGE)
        store.save_image("met:1", URL, "met/1.jpg", hashlib.sha256(IMAGE).hexdigest(), len(IMAGE))
        store.save_image("met:2", CLOSED_URL, "met/2.jpg", "0" * 64, 1)
    svc = service(db, runs_dir)
    request = BoardRequest(brief="boats", keep_local=True)
    run_id = svc.create(request).run_id
    view = svc.execute(run_id, request)
    return {"db": db, "runs_dir": runs_dir, "run_id": run_id, "view": view, "tmp": tmp_path}


def export(source, run_ids=None):
    out = source["tmp"] / "bundle"
    export_bundle(source["db"], source["runs_dir"], run_ids or [source["run_id"]], out)
    return out


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TestExport:
    def test_writes_the_records_without_raw_responses(self, source):
        out = export(source)
        records = lines(out / "records.jsonl")
        assert [r["id"] for r in records] == [r.id for r in RECORDS]
        assert "raw museum response" not in (out / "records.jsonl").read_text(encoding="utf-8")

    def test_writes_the_chosen_runs_and_their_trace(self, source):
        out = export(source)
        runs = lines(out / "runs.jsonl")
        assert [r["run_id"] for r in runs] == [source["run_id"]]
        assert (out / "events" / f"{source['run_id']}.jsonl").is_file()

    def test_lists_images_for_open_board_items_only(self, source):
        on_board = {item.record.id for item in source["view"].items}
        assert "met:1" in on_board
        images = lines(export(source) / "images.jsonl")
        assert [i["record_id"] for i in images] == ["met:1"]  # never met:2, not Open
        assert images[0]["url"] == URL
        assert images[0]["sha256"] == hashlib.sha256(IMAGE).hexdigest()

    def test_manifest_names_the_corpus_and_runs(self, source):
        manifest = json.loads((export(source) / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["corpus_version"].startswith("met:3:")
        assert manifest["runs"] == [source["run_id"]]
        assert manifest["images"] == 1

    def test_unknown_run_is_an_error(self, source):
        with pytest.raises(BundleError, match="nope"):
            export(source, ["nope"])


class TestBuild:
    def build(self, source, fetch=None, tmp=None):
        bundle = export(source)
        target = source["tmp"] / "demo"
        fetched = []

        def default_fetch(url):
            fetched.append(url)
            return IMAGE

        build_store(
            bundle,
            db=target / "refdesk.sqlite",
            runs_dir=target / "runs",
            images_dir=target / "images",
            fetch=fetch or default_fetch,
        )
        return target, fetched

    def test_rebuilds_records_runs_and_trace(self, source):
        target, _ = self.build(source)
        svc = service(target / "refdesk.sqlite", target / "runs")
        view = svc.get(source["run_id"])
        assert view.items == source["view"].items
        assert view.events  # the audit trace is there
        with Store(target / "refdesk.sqlite") as store:
            assert store.count_records() == len(RECORDS)
            assert store.get_raw(RECORDS[0].raw_record_ref) is None  # no raw responses

    def test_fetches_each_image_and_records_its_hash(self, source):
        target, fetched = self.build(source)
        assert fetched == [URL]
        assert (target / "images" / "met" / "1.jpg").read_bytes() == IMAGE
        with Store(target / "refdesk.sqlite") as store:
            assert store.get_image("met:1")["sha256"] == hashlib.sha256(IMAGE).hexdigest()

    def test_a_changed_image_fails_the_build(self, source):
        with pytest.raises(BundleError, match="met:1"):
            self.build(source, fetch=lambda url: b"something else")

    def test_lists_every_failed_image_not_just_the_first(self, source):
        from refdesk.sources.met import MetNotFound

        def gone(url):
            raise MetNotFound(url)

        with pytest.raises(BundleError, match=r"(?s)1 of 1 images failed:\n.*met:1.*MetNotFound"):
            self.build(source, fetch=gone)

    def test_refuses_an_image_for_a_work_that_is_not_open(self, source):
        bundle = export(source)
        with (bundle / "images.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"record_id": "met:2", "url": CLOSED_URL, "path": "met/2.jpg",
                                "sha256": "0" * 64, "bytes": 1}) + "\n")  # fmt: skip
        target = source["tmp"] / "demo"
        with pytest.raises(BundleError, match="met:2"):
            build_store(
                bundle, db=target / "db.sqlite", runs_dir=target / "runs",
                images_dir=target / "images", fetch=lambda url: IMAGE,
            )  # fmt: skip

    def test_refuses_a_path_outside_the_image_directory(self, source):
        bundle = export(source)
        rows = lines(bundle / "images.jsonl")
        rows[0]["path"] = "../escape.jpg"
        (bundle / "images.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        target = source["tmp"] / "demo"
        with pytest.raises(BundleError, match="path"):
            build_store(
                bundle, db=target / "db.sqlite", runs_dir=target / "runs",
                images_dir=target / "images", fetch=lambda url: IMAGE,
            )  # fmt: skip
