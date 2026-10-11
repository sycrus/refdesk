"""Command line: uv run python -m refdesk <command>  (PowerShell or WSL2).

ingest met [--db PATH] [--limit N] [--refresh] [--recheck-skipped]
    Ingest the Met paintings slice. Resumable; re-run after any stop.
rebuild met [--db PATH]
    Re-derive records from stored raw responses (no network). Use after a mapping change.
stats [--db PATH]
    Record counts by rights status, and ingest progress.
"""

from __future__ import annotations

import argparse
import sys

from refdesk.ingest import ingest, rebuild
from refdesk.sources.met import SOURCE, MetSource, MetUnavailable
from refdesk.store import Store

DEFAULT_DB = "data/refdesk.sqlite"


def _print_stats(store: Store) -> None:
    print(f"records: {store.count_records()}")
    for status, n in sorted(store.count_by_rights_status().items()):
        print(f"  {status}: {n}")
    for outcome, n in sorted(store.progress_counts(SOURCE).items()):
        print(f"  progress {outcome}: {n}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="refdesk")
    commands = parser.add_subparsers(dest="command", required=True)
    p_ingest = commands.add_parser("ingest", help="ingest a source into the store")
    p_ingest.add_argument("source", choices=["met"])
    p_ingest.add_argument("--db", default=DEFAULT_DB)
    p_ingest.add_argument("--limit", type=int, help="stop after N new objects")
    p_ingest.add_argument("--refresh", action="store_true", help="re-fetch objects already done")
    p_ingest.add_argument(
        "--recheck-skipped",
        action="store_true",
        help="re-fetch objects skipped for a classification the slice now includes",
    )
    p_rebuild = commands.add_parser("rebuild", help="re-derive records from stored raw data")
    p_rebuild.add_argument("source", choices=["met"])
    p_rebuild.add_argument("--db", default=DEFAULT_DB)
    p_stats = commands.add_parser("stats", help="show store counts")
    p_stats.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args(argv)

    with Store(args.db) as store:
        if args.command == "stats":
            _print_stats(store)
            return 0
        if args.command == "rebuild":
            result = rebuild(store, args.source)
            print(f"rebuilt {result.rebuilt}, missing raw {len(result.missing_raw)}")
            _print_stats(store)
            return 0 if not result.missing_raw else 1
        try:
            result = ingest(
                store,
                MetSource(),
                limit=args.limit,
                refresh=args.refresh,
                recheck_skipped=args.recheck_skipped,
            )
        except (MetUnavailable, KeyboardInterrupt) as stop:
            print(f"Stopped: {type(stop).__name__} {stop}. Progress is saved; re-run to resume.")
            _print_stats(store)
            return 1
        print(
            f"listed {result.listed}, already done {result.already_done}, "
            f"ingested {result.ingested}, skipped {result.skipped}"
        )
        _print_stats(store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
