"""Command line: uv run python -m refdesk <command>  (PowerShell or WSL2).

ingest met [--db PATH] [--limit N] [--refresh] [--recheck-skipped]
    Ingest the Met paintings slice. Resumable; re-run after any stop.
rebuild met [--db PATH]
    Re-derive records from stored raw responses (no network). Use after a mapping change.
stats [--db PATH]
    Record counts by rights status, and ingest progress.
images met [--db PATH] [--dir data/images] [--limit N]
    Cache images of open works only (resumable).
eval [--retriever jaccard] [--golden PATH] [--k 12] [--seed 0] [--db PATH]
    Run a retriever over a golden set; write manifest, report and history row.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from refdesk.evals.golden import GoldenCase, corpus_version
from refdesk.evals.harness import EvalConfig, file_sha256, git_state, run_eval, write_outputs
from refdesk.images import cache_images
from refdesk.ingest import ingest, rebuild
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.sources.met import SOURCE, MetClient, MetSource, MetUnavailable
from refdesk.store import Store

DEFAULT_DB = "data/refdesk.sqlite"
DEFAULT_GOLDEN = "evals/golden/golden-v0-synthetic.jsonl"
RETRIEVERS = {"jaccard": JaccardRetriever}


def _print_stats(store: Store) -> None:
    print(f"records: {store.count_records()}")
    for status, n in sorted(store.count_by_rights_status().items()):
        print(f"  {status}: {n}")
    for outcome, n in sorted(store.progress_counts(SOURCE).items()):
        print(f"  progress {outcome}: {n}")


def _eval(store: Store, args: argparse.Namespace) -> int:
    golden = Path(args.golden)
    lines = [line for line in golden.read_text(encoding="utf-8").splitlines() if line]
    cases = [GoldenCase(**json.loads(line)) for line in lines]
    records = list(store.iter_records())
    corpus = corpus_version(records)
    golden_corpus = {c.corpus_version for c in cases}
    if golden_corpus != {corpus}:
        print(f"Not comparable: golden set is for {golden_corpus}, the store is {corpus}.")
        return 2
    sha, dirty = git_state(Path.cwd())
    config = EvalConfig(
        retriever=args.retriever,
        retriever_params={},
        k=args.k,
        seed=args.seed,
        n_boot=args.n_boot,
        golden_path=golden.as_posix(),
        golden_sha256=file_sha256(golden),
        golden_version=cases[0].version,
        corpus_version=corpus,
        git_sha=sha,
        git_dirty=dirty,
    )
    result = run_eval(RETRIEVERS[args.retriever](records), cases, records, config)
    paths = write_outputs(result, root=Path.cwd(), date=date.today().isoformat())
    for metric, s in result.summary.items():
        print(f"{metric}: {s['mean']:.3f} [{s['low']:.3f}, {s['high']:.3f}] n={s['n']}")
    print(f"config hash {config.config_hash()}; report {paths['report'].as_posix()}")
    return 0


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
    p_images = commands.add_parser("images", help="cache images of open works")
    p_images.add_argument("source", choices=["met"])
    p_images.add_argument("--db", default=DEFAULT_DB)
    p_images.add_argument("--dir", default="data/images")
    p_images.add_argument("--limit", type=int, help="stop after N new downloads")
    p_eval = commands.add_parser("eval", help="evaluate a retriever on a golden set")
    p_eval.add_argument("--retriever", choices=sorted(RETRIEVERS), default="jaccard")
    p_eval.add_argument("--golden", default=DEFAULT_GOLDEN)
    p_eval.add_argument("--k", type=int, default=12)
    p_eval.add_argument("--seed", type=int, default=0)
    p_eval.add_argument("--n-boot", type=int, default=2000)
    p_eval.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args(argv)

    with Store(args.db) as store:
        if args.command == "stats":
            _print_stats(store)
            return 0
        if args.command == "images":
            try:
                result = cache_images(store, MetClient(), Path(args.dir), limit=args.limit)
            except (MetUnavailable, KeyboardInterrupt) as stop:
                print(f"Stopped: {type(stop).__name__} {stop}. Progress is saved; re-run.")
                return 1
            print(
                f"downloaded {result.downloaded}, already cached {result.already_cached}, "
                f"skipped {dict(result.skipped)}"
            )
            return 0
        if args.command == "eval":
            return _eval(store, args)
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
