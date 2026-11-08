"""The demo bundle (issue #167, ADR-025, option A): recorded runs and the corpus metadata
committed as reviewable JSONL. No images: the UI loads them from the museum's host
(Joe, 2026-11-08)."""

import json

import pytest
from test_boards import RECORDS as BASE

from refdesk.api.models import BoardRequest
from refdesk.boards import BoardService, RunStore
from refdesk.demo import BundleError, build_store, export_bundle
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.store import Store

URL = "https://images.metmuseum.org/CRDImages/ep/original/1.jpg"
RECORDS = [BASE[0].model_copy(update={"image_url": URL}), *BASE[1:]]


def service(db, runs_dir):
    return BoardService(
        RunStore(db), lambda: RECORDS, JaccardRetriever, "jaccard", runs_dir=runs_dir
    )


@pytest.fixture
def source(tmp_path):
    """A local store like the dev machine's: records with raw responses, a cached image
    for the Open work, one run."""
    db, runs_dir = tmp_path / "src.sqlite", tmp_path / "runs"
    with Store(db) as store:
        for record in RECORDS:
            store.save(record, {"private": "raw museum response"})
        store.save_image("met:1", URL, "met/1.jpg", "0" * 64, 1)
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

    def test_has_no_images_or_image_list(self, source):
        out = export(source)
        assert sorted(p.name for p in out.iterdir()) == [
            "events", "manifest.json", "records.jsonl", "runs.jsonl",
        ]  # fmt: skip

    def test_manifest_names_the_corpus_and_runs(self, source):
        manifest = json.loads((export(source) / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["corpus_version"].startswith("met:3:")
        assert manifest["runs"] == [source["run_id"]]

    def test_unknown_run_is_an_error(self, source):
        with pytest.raises(BundleError, match="nope"):
            export(source, ["nope"])


class TestBuild:
    def build(self, source):
        bundle = export(source)
        target = source["tmp"] / "demo"
        counts = build_store(bundle, db=target / "refdesk.sqlite", runs_dir=target / "runs")
        return target, counts

    def test_rebuilds_records_runs_and_trace(self, source):
        target, counts = self.build(source)
        assert counts == {"records": len(RECORDS), "runs": 1}
        svc = service(target / "refdesk.sqlite", target / "runs")
        view = svc.get(source["run_id"])
        assert view.items == source["view"].items
        assert view.events  # the audit trace is there
        with Store(target / "refdesk.sqlite") as store:
            assert store.count_records() == len(RECORDS)
            assert store.get_raw(RECORDS[0].raw_record_ref) is None  # no raw responses
            assert store.get_image("met:1") is None  # no image cache in the demo

    def test_board_items_keep_the_museum_image_url(self, source):
        # The UI shows images from image_url, on the museum's own host.
        target, _ = self.build(source)
        view = service(target / "refdesk.sqlite", target / "runs").get(source["run_id"])
        record = next(i.record for i in view.items if i.record.id == "met:1")
        assert record.image_url == URL
