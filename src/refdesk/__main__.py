"""Command line: uv run python -m refdesk <command>  (PowerShell or WSL2).

ingest met [--db PATH] [--limit N] [--refresh] [--recheck-skipped]
    Ingest the Met paintings slice. Resumable; re-run after any stop.
rebuild met [--db PATH]
    Re-derive records from stored raw responses (no network). Use after a mapping change.
stats [--db PATH]
    Record counts by rights status, and ingest progress.
images met [--db PATH] [--dir data/images] [--limit N]
    Cache images of open works only (resumable).
embed met [--model ViT-B-32] [--pretrained laion2b_s34b_b79k] [--device cuda]
    Embed cached images of open works into a FAISS index (needs: uv sync --extra embed).
eval [--retriever jaccard|clip|combined] [--golden PATH] [--k 12] [--seed 0] [--db PATH]
    Run a retriever over a golden set; write manifest, report and history row.
eval-rationales [--generator mock|local-small] [--judge auto|TIER] [--retriever jaccard] [--k 3]
    [--rationale-prompt rationale-vN] [--fit-prompt fit-vN]
    Generate and verify rationales for each golden case's top-k items; write manifest,
    report and history rows (issue #102). Local and mock tiers only (the brief stays local).
compare HASH_A HASH_B [HASH ...] [--write]
    Paired comparison of eval runs (B - A per case, with a 95% CI), for every pair.
    --write saves one report to evals/reports/ (named by the run hashes).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

from refdesk.evals.compare import (
    NotComparable,
    compare_runs,
    format_comparison,
    write_comparison_report,
)
from refdesk.evals.golden import GoldenCase, corpus_version
from refdesk.evals.harness import EvalConfig, file_sha256, git_state, run_eval, write_outputs
from refdesk.images import cache_images
from refdesk.ingest import ingest, rebuild
from refdesk.retrieval.registry import RETRIEVERS, build_retriever, retriever_params
from refdesk.sources.met import SOURCE, MetClient, MetSource, MetUnavailable
from refdesk.store import Store

DEFAULT_DB = "data/refdesk.sqlite"
DEFAULT_GOLDEN = "evals/golden/golden-v0-synthetic.jsonl"


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
        retriever_params=retriever_params(args.retriever),
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
    result = run_eval(build_retriever(args.retriever, records), cases, records, config)
    paths = write_outputs(result, root=Path.cwd(), date=date.today().isoformat())
    for metric, s in result.summary.items():
        print(f"{metric}: {s['mean']:.3f} [{s['low']:.3f}, {s['high']:.3f}] n={s['n']}")
    print(f"config hash {config.config_hash()}; report {paths['report'].as_posix()}")
    return 0


def _eval_rationales(store: Store, args: argparse.Namespace) -> int:
    import yaml

    from refdesk.boards import default_reasoner
    from refdesk.evals.rationale_eval import (
        EvalStopped,
        run_rationale_eval,
        write_rationale_outputs,
    )
    from refdesk.llm.config import Budgets

    golden = Path(args.golden)
    lines = [line for line in golden.read_text(encoding="utf-8").splitlines() if line]
    cases = [GoldenCase(**json.loads(line)) for line in lines]
    records = list(store.iter_records())
    corpus = corpus_version(records)
    if {c.corpus_version for c in cases} != {corpus}:
        print(f"Not comparable: golden set is for another corpus; the store is {corpus}.")
        return 2
    settings = yaml.safe_load(Path("config/retrieval.yaml").read_text(encoding="utf-8"))
    prompt_names = dict(settings["api"]["reasoning"].get("prompts") or {})
    if args.rationale_prompt:
        prompt_names["rationale"] = args.rationale_prompt
    if args.fit_prompt:
        prompt_names["fit"] = args.fit_prompt
    reasoner = default_reasoner(
        {"generator_tier": args.generator, "judge_tier": args.judge, "prompts": prompt_names}
    )
    judge_tier = reasoner.judge_tier()
    tiers = reasoner.config.tiers
    prompts = list(reasoner.prompts.values())
    sha, dirty = git_state(Path.cwd())
    config = EvalConfig(
        retriever=args.retriever,
        retriever_params={
            **retriever_params(args.retriever),
            "generator_tier": args.generator,
            "judge_tier": judge_tier,
            "judge_model": tiers[judge_tier].model if judge_tier else None,
        },
        k=args.k,
        seed=args.seed,
        n_boot=args.n_boot,
        golden_path=golden.as_posix(),
        golden_sha256=file_sha256(golden),
        golden_version=cases[0].version,
        corpus_version=corpus,
        git_sha=sha,
        git_dirty=dirty,
        model=tiers[args.generator].model,
        prompt_hashes={p.name: p.sha256 for p in prompts},
    )
    budget = Budgets.load("config/budgets.yaml").for_job("rationale_eval") or 0.0
    try:
        result = run_rationale_eval(
            build_retriever(args.retriever, records), reasoner, cases, records, config,
            cap_usd=budget,
        )  # fmt: skip
    except EvalStopped as stop:
        print(f"Stopped, no report written: {stop}")
        return 1
    paths = write_rationale_outputs(result, root=Path.cwd(), date=date.today().isoformat())
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
    p_compare = commands.add_parser("compare", help="paired comparison of eval runs")
    p_compare.add_argument("runs", nargs="+", metavar="HASH", help="two or more run hashes")
    p_compare.add_argument("--write", action="store_true", help="save one comparison report")
    p_compare.add_argument("--db", default=DEFAULT_DB)
    p_embed = commands.add_parser("embed", help="build the image embedding index")
    p_embed.add_argument("source", choices=["met"])
    p_embed.add_argument("--db", default=DEFAULT_DB)
    p_embed.add_argument("--images", default="data/images")
    p_embed.add_argument("--out", default="data/index/met-clip")
    p_embed.add_argument("--model", default="ViT-B-32")
    p_embed.add_argument("--pretrained", default="laion2b_s34b_b79k")
    p_embed.add_argument("--device", default="cuda")
    p_eval = commands.add_parser("eval", help="evaluate a retriever on a golden set")
    p_eval.add_argument("--retriever", choices=sorted(RETRIEVERS), default="jaccard")
    p_eval.add_argument("--golden", default=DEFAULT_GOLDEN)
    p_eval.add_argument("--k", type=int, default=12)
    p_eval.add_argument("--seed", type=int, default=0)
    p_eval.add_argument("--n-boot", type=int, default=2000)
    p_eval.add_argument("--db", default=DEFAULT_DB)
    p_reval = commands.add_parser("eval-rationales", help="verifier pass rates of rationales")
    p_reval.add_argument("--generator", default="mock", help="generator tier (providers.yaml)")
    p_reval.add_argument("--judge", default="auto", help="judge tier, or auto")
    p_reval.add_argument("--retriever", choices=sorted(RETRIEVERS), default="jaccard")
    p_reval.add_argument("--golden", default=DEFAULT_GOLDEN)
    p_reval.add_argument("--k", type=int, default=3)
    p_reval.add_argument("--rationale-prompt", help="e.g. rationale-v2 (default: config)")
    p_reval.add_argument("--fit-prompt", help="e.g. fit-v2 (default: config)")
    p_reval.add_argument("--seed", type=int, default=0)
    p_reval.add_argument("--n-boot", type=int, default=2000)
    p_reval.add_argument("--db", default=DEFAULT_DB)
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
                f"skipped {dict(result.skipped)}, failed {len(result.failed)}"
            )
            for record_id, reason in result.failed.items():
                print(f"  failed {record_id}: {reason}")
            return 1 if result.failed else 0
        if args.command == "compare":
            if len(args.runs) < 2:
                print("compare needs at least two run hashes")
                return 2
            try:
                if args.write:
                    path = write_comparison_report(Path.cwd(), args.runs, date.today().isoformat())
                    print(f"wrote {path.relative_to(Path.cwd()).as_posix()}")
                    return 0
                for i, run_a in enumerate(args.runs):
                    for run_b in args.runs[i + 1 :]:
                        print(format_comparison(compare_runs(Path.cwd(), run_a, run_b)))
                        print()
            except NotComparable as error:
                print(f"Not comparable: {error}")
                return 2
            except FileExistsError as error:
                print(error)
                return 2
            return 0
        if args.command == "embed":
            from refdesk.embeddings import OpenClipEmbedder, build_index

            embedder = OpenClipEmbedder(args.model, args.pretrained, args.device)
            started = time.perf_counter()
            result = build_index(store, Path(args.images), embedder, Path(args.out))
            seconds = time.perf_counter() - started
            action = "built" if result.built else "up to date (skipped)"
            print(f"{action}: {result.count} vectors, {embedder.model_id}, {seconds:.1f} s")
            return 0
        if args.command == "eval":
            return _eval(store, args)
        if args.command == "eval-rationales":
            return _eval_rationales(store, args)
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
