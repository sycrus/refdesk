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
    Run a retriever over a golden set; write manifest, report and history row. The store is
    filtered to the golden set's corpus snapshot first (ADR-023).
eval-rationales [--generator mock|local-small] [--judge auto|TIER] [--retriever jaccard] [--k 3]
    [--rationale-prompt rationale-vN] [--fit-prompt fit-vN]
    Generate and verify rationales for each golden case's top-k items; write manifest,
    report and history rows (issue #102). Local and mock tiers only (the brief stays local).
label-routing [--dry-run] [--approve] [--tiers T1,T2] [--judges J1] [--n N] [--db PATH]
    Routing labels (issue #161, PRD 10.3): synthetic briefs through every routing tier,
    verified and judged by a model from another family; the label is the cheapest tier that
    met the quality bar (config/labelling.yaml). --dry-run prints calls, tokens and cost and
    makes no request. Paid tiers need a key in .env and --approve. Writes
    runs/routing-labels/<date>-<hash>/. Mock drill: --tiers mock,mock-strong --judges mock-judge.
compare HASH_A HASH_B [HASH ...] [--write]
    Paired comparison of eval runs (B - A per case, with a 95% CI), for every pair.
    --write saves one report to evals/reports/ (named by the run hashes).
snapshot [--db PATH]
    Write evals/golden/corpus/<corpus version>.tsv for the store as it is now: the record IDs
    a golden set built today is pinned to (ADR-023). Never overwrites a different snapshot.
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
from refdesk.evals.corpus import CorpusMismatch, PinnedCorpus, pin, write_snapshot
from refdesk.evals.golden import GoldenCase
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


def _pinned(store: Store, cases: list[GoldenCase]) -> PinnedCorpus | None:
    """The store filtered to the golden set's corpus snapshot, or None (printed why)."""
    versions = {c.corpus_version for c in cases}
    if len(versions) != 1:
        print(f"Not comparable: the golden set mixes corpus versions {sorted(versions)}.")
        return None
    try:
        pinned = pin(list(store.iter_records()), versions.pop())
    except CorpusMismatch as error:
        print(f"Not comparable: {error}")
        return None
    for note in pinned.notes():
        print(note.replace("**", ""))
    return pinned


def _eval(store: Store, args: argparse.Namespace) -> int:
    golden = Path(args.golden)
    lines = [line for line in golden.read_text(encoding="utf-8").splitlines() if line]
    cases = [GoldenCase(**json.loads(line)) for line in lines]
    pinned = _pinned(store, cases)
    if pinned is None:
        return 2
    records, corpus = pinned.records, pinned.version
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
        corpus_drift=pinned.drift,
    )
    result = run_eval(build_retriever(args.retriever, records), cases, records, config)
    result.corpus_notes = pinned.notes()
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
    pinned = _pinned(store, cases)
    if pinned is None:
        return 2
    records, corpus = pinned.records, pinned.version
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
        corpus_drift=pinned.drift,
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
    result.corpus_notes = pinned.notes()
    paths = write_rationale_outputs(result, root=Path.cwd(), date=date.today().isoformat())
    for metric, s in result.summary.items():
        print(f"{metric}: {s['mean']:.3f} [{s['low']:.3f}, {s['high']:.3f}] n={s['n']}")
    print(f"config hash {config.config_hash()}; report {paths['report'].as_posix()}")
    return 0


def _label_routing(store: Store, args: argparse.Namespace) -> int:
    from refdesk import routing_labels as rl
    from refdesk.llm.client import KeepAliveTransport, LLMPolicyError, ProviderError
    from refdesk.llm.config import Budgets, ProvidersConfig
    from refdesk.llm.model_manager import ModelManager, OllamaBackend, load_specs

    config = ProvidersConfig.load("config/providers.yaml")
    budgets = Budgets.load("config/budgets.yaml")
    settings = rl.LabellingSettings.load(args.settings)
    if args.n is not None:
        settings = settings.model_copy(update={"n_briefs": args.n})
    specs = load_specs("config/models.yaml")
    manager = ModelManager(specs, {"ollama": OllamaBackend()})

    def ensure(model: str) -> None:
        if model in specs:  # GPU models only; the mock needs nothing
            manager.ensure(model)

    try:
        pipeline = rl.LabellingPipeline(
            config, budgets, settings,
            tiers=args.tiers.split(",") if args.tiers else None,
            judges=args.judges.split(",") if args.judges else None,
            approved=args.approve, dry_run=args.dry_run,
            ensure_model=None if args.dry_run else ensure,
            transport=KeepAliveTransport(),  # tens of thousands of calls (WinError 10048)
        )  # fmt: skip
    except LLMPolicyError as error:
        print(f"Refused at startup: {type(error).__name__}: {error}")
        return 2
    records = list(store.iter_records())
    if not records:
        print("The store has no records; ingest first.")
        return 2
    retriever = rl.StoreRetriever(settings.retriever, records)
    briefs = rl.synthetic_briefs(settings.n_briefs, seed=settings.seed)
    print(f"tiers {pipeline.tiers}; judge per tier {pipeline.judge_for}")
    if settings.quality_bar.placeholder:
        print(f"quality bar {settings.quality_bar.min_verified_share} is a PLACEHOLDER (#153)")
    if args.dry_run:
        print(rl.format_estimate(pipeline.estimate(briefs, retriever)))
        return 0
    try:
        result = pipeline.run(briefs, retriever)
    except (LLMPolicyError, ProviderError) as error:
        print(f"Stopped: {type(error).__name__}: {error}. No labels written; nothing fell back.")
        return 1
    result.corpus = rl.corpus_digest(records)
    paths = rl.write_outputs(result, root=Path.cwd(), date=date.today().isoformat())
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    print(f"labels {manifest['counts']['labelled']}; spent {result.spent_usd:.4f} USD")
    print(f"wrote {paths['labels'].as_posix()} and {paths['manifest'].as_posix()}")
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
    p_snapshot = commands.add_parser("snapshot", help="write the store's corpus snapshot")
    p_snapshot.add_argument("--db", default=DEFAULT_DB)
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
    p_label = commands.add_parser("label-routing", help="routing labels for the Q1 decision")
    p_label.add_argument("--dry-run", action="store_true", help="estimate only; no request")
    p_label.add_argument("--approve", action="store_true", help="allow paid calls")
    p_label.add_argument("--tiers", help="comma-separated tiers (default: routing)")
    p_label.add_argument("--judges", help="comma-separated judge tiers (default: judges)")
    p_label.add_argument("--n", type=int, help="number of briefs (default: config)")
    p_label.add_argument("--settings", default="config/labelling.yaml")
    p_label.add_argument("--db", default=DEFAULT_DB)
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
        if args.command == "snapshot":
            try:
                path = write_snapshot(list(store.iter_records()))
            except FileExistsError as error:
                print(error)
                return 2
            print(f"snapshot {path.as_posix()}")
            return 0
        if args.command == "eval":
            return _eval(store, args)
        if args.command == "eval-rationales":
            return _eval_rationales(store, args)
        if args.command == "label-routing":
            return _label_routing(store, args)
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
