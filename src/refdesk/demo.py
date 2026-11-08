"""The demo bundle (issue #167, ADR-025, option A, Joe 2026-11-08).

The public demo serves recorded runs from a store baked into the image. The bundle is
what gets committed, as reviewable text:

    demo/manifest.json      corpus version, run IDs, counts
    demo/records.jsonl      every record's metadata (no raw museum responses)
    demo/runs.jsonl         the recorded runs (request and view, as stored)
    demo/events/<run>.jsonl each run's log: the audit trace

No images (Joe, 2026-11-08). The UI loads each Open work's image from the museum's own
host in the visitor's browser (`image_url`), so the demo needs no image cache. Only the
API's /records/{id}/image reads the cache; in the demo it answers 404 image_not_cached,
pointing to image_url. An earlier version fetched and hash-checked images at build time:
12 of 65 had changed or gone at the Met within a month, and the UI never used them.

What breaks without it: the demo would need the dev machine's 14 MB store (a third of it
raw museum responses), or the store in git as an unreviewable binary.

    uv run python -m refdesk.demo export --runs <id> <id> ... --out demo
    uv run python -m refdesk.demo build --bundle demo --db /app/data/refdesk.sqlite \\
        --runs-dir /app/runs
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from refdesk.boards import RunStore
from refdesk.runlog import FILENAME as EVENTS_FILE
from refdesk.schema import ArtworkRecord
from refdesk.store import Store


class BundleError(Exception):
    """The bundle is incomplete."""


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

    (out / "events").mkdir(parents=True, exist_ok=True)
    _write_jsonl(out / "records.jsonl", [json.loads(r.model_dump_json()) for r in records])
    _write_jsonl(out / "runs.jsonl", runs)
    for run_id in run_ids:
        events = runs_dir / run_id / EVENTS_FILE
        if not events.is_file():
            raise BundleError(f"Run {run_id!r} has no trace at {events}.")
        shutil.copyfile(events, out / "events" / f"{run_id}.jsonl")
    manifest = {
        "corpus_version": corpus_version(records),
        "runs": list(run_ids),
        "records": len(records),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_store(bundle: Path, *, db: Path, runs_dir: Path) -> dict:
    """Rebuild the demo store from a bundle: records, runs and traces. No network."""
    bundle, db, runs_dir = Path(bundle), Path(db), Path(runs_dir)
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

    return {"records": len(records), "runs": len(_read_jsonl(bundle / "runs.jsonl"))}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m refdesk.demo", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="Write the bundle from the local store")
    ex.add_argument("--runs", nargs="+", required=True)
    ex.add_argument("--db", default="data/refdesk.sqlite")
    ex.add_argument("--runs-dir", default="runs")
    ex.add_argument("--out", default="demo")
    bu = sub.add_parser("build", help="Rebuild the demo store from the bundle (docker build)")
    bu.add_argument("--bundle", default="demo")
    bu.add_argument("--db", required=True)
    bu.add_argument("--runs-dir", required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        print(
            json.dumps(export_bundle(Path(args.db), Path(args.runs_dir), args.runs, Path(args.out)))
        )
    else:
        counts = build_store(Path(args.bundle), db=Path(args.db), runs_dir=Path(args.runs_dir))
        print(json.dumps(counts))


if __name__ == "__main__":
    main()
