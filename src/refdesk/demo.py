"""The demo bundle (issue #167, ADR-025, option A, Joe 2026-11-08).

The public demo serves recorded runs from a store baked into the image. The bundle is
what gets committed, as reviewable text:

    demo/manifest.json      corpus version, run IDs, counts
    demo/records.jsonl      every record's metadata (no raw museum responses)
    demo/runs.jsonl         the recorded runs (request and view, as stored)
    demo/events/<run>.jsonl each run's log: the audit trace
    demo/images.jsonl       URL, path and sha256 of each Open work on a recorded board

Images are not committed (CLAUDE.md: images once entered git by mistake). The image
build fetches them from the source's own host (MetClient refuses any other host), only
for Open works, and checks each against the hash recorded when the run was made, so a
changed or substituted image fails the build instead of shipping.

What breaks without it: the demo would need the dev machine's 14 MB store (a third of it
raw museum responses) and 235 MB image cache, or images in git.

    uv run python -m refdesk.demo export --runs <id> <id> ... --out demo
    uv run python -m refdesk.demo build --bundle demo --db /app/data/refdesk.sqlite \\
        --runs-dir /app/runs --images /app/data/images
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

from refdesk.boards import RunStore
from refdesk.runlog import FILENAME as EVENTS_FILE
from refdesk.schema import ArtworkRecord, RightsStatus
from refdesk.store import Store


class BundleError(Exception):
    """The bundle is incomplete, or an image does not match it."""


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def export_bundle(db: Path, runs_dir: Path, run_ids: list[str], out: Path) -> dict:
    """Write the bundle for `run_ids` from a local store. Returns the manifest."""
    from refdesk.evals.golden import corpus_version

    db, runs_dir, out = Path(db), Path(runs_dir), Path(out)
    with Store(db) as store:
        records = list(store.iter_records())
        by_id = {r.id: r for r in records}
        con = sqlite3.connect(db)
        try:
            runs = []
            for run_id in run_ids:
                row = con.execute(
                    "SELECT run_id, created_at, updated_at, request, view FROM runs "
                    "WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if row is None:
                    raise BundleError(f"No run {run_id!r} in {db}.")
                keys = ("run_id", "created_at", "updated_at", "request", "view")
                runs.append(dict(zip(keys, row, strict=True)))
        finally:
            con.close()

        images, seen = [], set()
        for run in runs:
            for item in json.loads(run["view"])["items"]:
                record_id = item["record"]["id"]
                record = by_id.get(record_id)
                if record_id in seen or record is None:
                    continue
                seen.add(record_id)
                if record.rights.status is not RightsStatus.OPEN:
                    continue  # never an image for a work that is not Open
                image = store.get_image(record_id)
                if image is not None:
                    images.append(
                        {k: image[k] for k in ("record_id", "url", "path", "sha256", "bytes")}
                    )

    (out / "events").mkdir(parents=True, exist_ok=True)
    _write_jsonl(out / "records.jsonl", [json.loads(r.model_dump_json()) for r in records])
    _write_jsonl(out / "runs.jsonl", runs)
    _write_jsonl(out / "images.jsonl", sorted(images, key=lambda i: i["record_id"]))
    for run_id in run_ids:
        events = runs_dir / run_id / EVENTS_FILE
        if not events.is_file():
            raise BundleError(f"Run {run_id!r} has no trace at {events}.")
        shutil.copyfile(events, out / "events" / f"{run_id}.jsonl")
    manifest = {
        "corpus_version": corpus_version(records),
        "runs": list(run_ids),
        "records": len(records),
        "images": len(images),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_store(
    bundle: Path, *, db: Path, runs_dir: Path, images_dir: Path, fetch: Callable[[str], bytes]
) -> dict:
    """Rebuild the demo store from a bundle. `fetch` gets image bytes from the source's
    host (MetClient.get_bytes in the image build). Raises BundleError on any mismatch."""
    bundle, db, runs_dir, images_dir = Path(bundle), Path(db), Path(runs_dir), Path(images_dir)
    records = {}
    with Store(db) as store:
        for row in _read_jsonl(bundle / "records.jsonl"):
            record = ArtworkRecord.model_validate(row)
            store.save_record(record)  # metadata only: no raw response in the demo
            records[record.id] = record

        RunStore(db)  # creates the runs tables
        con = sqlite3.connect(db)
        try:
            with con:
                for run in _read_jsonl(bundle / "runs.jsonl"):
                    con.execute(
                        "INSERT INTO runs (run_id, created_at, updated_at, request, view) "
                        "VALUES (:run_id, :created_at, :updated_at, :request, :view)",
                        run,
                    )
                    trace = bundle / "events" / f"{run['run_id']}.jsonl"
                    (runs_dir / run["run_id"]).mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(trace, runs_dir / run["run_id"] / EVENTS_FILE)
        finally:
            con.close()

        root = images_dir.resolve()
        images = _read_jsonl(bundle / "images.jsonl")
        for image in images:
            record_id = image["record_id"]
            record = records.get(record_id)
            if record is None or record.rights.status is not RightsStatus.OPEN:
                raise BundleError(f"{record_id}: not an Open work in this bundle; no image.")
            target = (root / image["path"]).resolve()
            if not target.is_relative_to(root):
                raise BundleError(f"{record_id}: image path {image['path']!r} leaves {root}.")
            data = fetch(image["url"])
            digest = hashlib.sha256(data).hexdigest()
            if digest != image["sha256"]:
                raise BundleError(
                    f"{record_id}: the image at {image['url']} has changed since the run was "
                    f"recorded (sha256 {digest[:12]}, expected {image['sha256'][:12]})."
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            store.save_image(record_id, image["url"], image["path"], digest, len(data))
    return {"records": len(records), "runs": len(_read_jsonl(bundle / "runs.jsonl")),
            "images": len(images)}  # fmt: skip


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m refdesk.demo", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="Write the bundle from the local store")
    ex.add_argument("--runs", nargs="+", required=True)
    ex.add_argument("--db", default="data/refdesk.sqlite")
    ex.add_argument("--runs-dir", default="runs")
    ex.add_argument("--out", default="demo")
    bu = sub.add_parser("build", help="Rebuild the demo store from the bundle (image build)")
    bu.add_argument("--bundle", default="demo")
    bu.add_argument("--db", required=True)
    bu.add_argument("--runs-dir", required=True)
    bu.add_argument("--images", required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        print(
            json.dumps(export_bundle(Path(args.db), Path(args.runs_dir), args.runs, Path(args.out)))
        )
    else:
        from refdesk.sources.met import MetClient

        client = MetClient()
        counts = build_store(
            Path(args.bundle), db=Path(args.db), runs_dir=Path(args.runs_dir),
            images_dir=Path(args.images), fetch=client.get_bytes,
        )  # fmt: skip
        print(json.dumps(counts))


if __name__ == "__main__":
    main()
