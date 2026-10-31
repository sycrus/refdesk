"""Trajectory evals: pass^k and the step failure taxonomy (issue #173; PRD 10.4, 11.7).

What it does: it evaluates the *loop*, not only the answer. A trajectory suite holds briefs,
each with k recorded runs: the tool outputs (retrievals and model answers) of k runs of the
loop, written to `events.jsonl` by the run log (runlog.py, #156). Each recording is
replayed through the current loop code with the recordings standing in for the retriever
and the model, so a run is deterministic and needs no service. Each replayed run is
classified as a success or by the step that failed:

| Category | The replayed run ... |
|---|---|
| `wrong_retrieval` | worked on a candidate the brief does not allow (rights not Open) |
| `bad_decision` | used another tier than the suite's, or sent a keep-local brief to the cloud |
| `verification_miss` | showed an item as verified whose rationale was planted wrong |
| `bad_stop` | stopped for another reason than expected, or before or after the recording |
| `rationale_error` | stopped correctly but short of K: rationales were unusable or rejected |
| `diverged` | sent a request that differs from the recording (not a PRD category) |

The first matching row wins, in this order, so a planted wrong rationale that got through
counts as a verification miss rather than a stop that came early.

Per brief: single-run success is the share of its k runs that succeed; pass^k is 1 when
all k succeed. The report gives both, averaged over briefs, with bootstrap intervals.

The gate: each recorded run carries the outcome the correct loop gives (`expected`). A
replay whose outcome differs is a regression and fails `check_gate`, which CI runs
(tests/evals/test_trajectory.py), so a deliberately bad change fails CI.

What it is not: a quality score. The suite is synthetic (provenance: synthetic), recorded
against the mock tiers; the k runs differ because faults were planted in the recordings, not
because a real model varied. It shows the harness works, nothing about model reliability.

What breaks without it: the answer evals score one pass per brief, so a loop that recovers
from a bad rationale on one run and stops wrongly on another looks fine; and a change to
the verifier or a stop rule could pass every unit test that does not happen to cover it.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from refdesk.api.models import RunEvent
from refdesk.evals.scorers import bootstrap_ci
from refdesk.llm.config import ProvidersConfig
from refdesk.loop import LoopConfig, LoopController, LoopResult
from refdesk.reasoning import Reasoner
from refdesk.runlog import ReplayDiverged, _Recordings, read_events
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus
from refdesk.wording import AttributionStatus, StopReason

SCORER_VERSION = "trajectory-v1"
SUCCESS = "success"
CATEGORIES = (
    "wrong_retrieval",
    "bad_decision",
    "verification_miss",
    "bad_stop",
    "rationale_error",
    "diverged",
)
# A regression fixture as much as an eval set, so it lives with the test fixtures.
DEFAULT_SUITE = Path("tests/fixtures/trajectory/trajectory-v0-synthetic")
CHECKED = datetime(2026, 10, 31, tzinfo=UTC)

# The tiers the suite was recorded against: the mock generator, and the mock judge in its
# own family so the cross-family rule holds. Nothing here reaches a network: replays answer
# every request from the recordings.
SUITE_PROVIDERS = ProvidersConfig.model_validate(
    {
        "providers": {
            "mock": {"family": "mock", "cloud": False, "paid": False,
                     "base_url": "http://mock.invalid/v1"},
            "mock-judge": {"family": "mock-judge", "cloud": False, "paid": False,
                           "base_url": "http://judge.invalid/v1"},
        },
        "tiers": {
            "mock": {"provider": "mock", "model": "mock-1"},
            "mock-judge": {"provider": "mock-judge", "model": "mock-1"},
        },
        "routing": ["mock"],
        "judges": ["mock-judge"],
    }
)  # fmt: skip


# --- The suite ---


@dataclass(frozen=True)
class RunSpec:
    """One recorded run of a brief. `plants` say which faults the recording holds:
    `{"generator": {record_id: behaviour}, "retrieve": [ids in order]}`; `expected` is the
    outcome the correct loop gives on it."""

    index: int
    plants: dict[str, Any]
    expected: str
    expected_stop: StopReason | None

    @property
    def planted_bad(self) -> set[str]:
        """Records whose rationale is wrong in this recording (ground truth)."""
        generator = self.plants.get("generator", {})
        return {rid for rid, b in generator.items() if b in ("wrongtext", "badfield")}


@dataclass(frozen=True)
class TrajectoryCase:
    id: str
    brief: str
    keep_local: bool
    target: int
    cap_usd: float
    pool: list[ArtworkRecord]
    runs: list[RunSpec]

    @property
    def eligible(self) -> set[str]:
        return {r.id for r in self.pool if r.rights.status is RightsStatus.OPEN}


@dataclass(frozen=True)
class Suite:
    root: Path
    version: str
    provenance: str
    k: int
    generator_tier: str
    prompts: dict[str, str]
    loop: dict[str, Any]
    cases: list[TrajectoryCase]

    def recording(self, case: TrajectoryCase, run: RunSpec) -> Path:
        return self.root / case.id / f"run-{run.index}.jsonl"

    def sha256(self) -> str:
        """Over the manifest and every recording, so a re-recorded suite hashes anew."""
        digest = hashlib.sha256()
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(self.root).as_posix().encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()


def build_record(spec: dict[str, Any]) -> ArtworkRecord:
    """A synthetic pool record from the manifest. Artists and titles say "Synthetic" so
    nobody mistakes them for museum data."""
    status = RightsStatus[spec.get("rights", "open").upper()]  # by name: "permission_required"
    object_id = str(spec["object_id"])
    rights = RightsRecord(
        source="met", object_id=object_id, flag_field="isPublicDomain",
        flag_value=status is RightsStatus.OPEN, licence_string=None, checked_at=CHECKED,
        status=status,
    )  # fmt: skip
    return ArtworkRecord(
        id=f"met:{object_id}", source="met", object_id=object_id, classification="Paintings",
        title=spec["title"], artist=spec.get("artist"), date=spec.get("date"),
        medium=spec.get("medium"), subject_tags=tuple(spec.get("tags", ())),
        raw_record_ref=f"synthetic/{object_id}.json",
        record_url=f"https://www.metmuseum.org/art/collection/search/{object_id}",
        rights=rights,
    )  # fmt: skip


def load_suite(root: str | Path = DEFAULT_SUITE) -> Suite:
    root = Path(root)
    data = json.loads((root / "suite.json").read_text(encoding="utf-8"))
    cases = []
    for c in data["cases"]:
        runs = [
            RunSpec(
                index=i, plants=r.get("plants", {}), expected=r["expected"],
                expected_stop=StopReason(r["expected_stop"]) if r.get("expected_stop") else None,
            )  # fmt: skip
            for i, r in enumerate(c["runs"], start=1)
        ]
        if len(runs) != data["k"]:
            raise ValueError(f"case {c['id']} has {len(runs)} runs; the suite says k={data['k']}")
        for run in runs:
            if run.expected not in (SUCCESS, *CATEGORIES):
                raise ValueError(f"case {c['id']} run {run.index}: unknown {run.expected!r}")
        cases.append(
            TrajectoryCase(
                id=c["id"], brief=c["brief"], keep_local=c.get("keep_local", False),
                target=c["target"], cap_usd=c.get("cap_usd", 1.0),
                pool=[build_record(r) for r in c["pool"]], runs=runs,
            )  # fmt: skip
        )
    return Suite(
        root=root, version=data["version"], provenance=data["provenance"], k=data["k"],
        generator_tier=data["generator_tier"], prompts=data["prompts"], loop=data["loop"],
        cases=cases,
    )  # fmt: skip


def make_reasoner(suite: Suite, transport) -> Reasoner:
    return Reasoner(
        SUITE_PROVIDERS, generator_tier=suite.generator_tier, transport=transport,
        prompts=suite.prompts, env={},
    )  # fmt: skip


# --- Replay and classify ---


class WentPastRecording(ReplayDiverged):
    """The replayed loop made a call after the recorded run had ended: it did not stop
    where the recording stopped."""


class _Tape(_Recordings):
    """The run log's recordings (runlog.py) with two additions: a call past the end is
    told apart from a changed call, and calls left over are counted."""

    @staticmethod
    def _next(queue: list[RunEvent], what: str) -> RunEvent:
        if not queue:
            raise WentPastRecording(f"the replay made a {what} after the recorded run ended")
        return queue.pop(0)

    @property
    def left_over(self) -> int:
        return len(self.retrievals) + len(self.model_calls)


@dataclass
class RunOutcome:
    case_id: str
    run: int
    outcome: str  # SUCCESS or a category
    expected: str
    detail: str
    stop: str | None = None
    accepted: int = 0
    rounds: int = 0

    @property
    def regressed(self) -> bool:
        return self.outcome != self.expected


def classify(
    case: TrajectoryCase,
    run: RunSpec,
    result: LoopResult | None,
    *,
    error: Exception | None = None,
    left_over: int = 0,
    expected_tier: str = "mock",
    cloud_providers: frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """(outcome, one-sentence reason). The first failing check wins (module docstring)."""
    if isinstance(error, WentPastRecording):
        return "bad_stop", f"the loop went on after the recorded run stopped: {error}"
    if isinstance(error, ReplayDiverged):
        return "diverged", str(error)
    assert result is not None
    outside = [r.id for r in result.records if r.id not in case.eligible]
    if outside:
        return "wrong_retrieval", f"worked on records the brief does not allow: {outside}"
    wrong_tiers = sorted({t for t in result.tiers if t != expected_tier})
    leaked = [p for p in result.sent_to if p in cloud_providers] if case.keep_local else []
    if wrong_tiers or leaked:
        return "bad_decision", f"tiers {wrong_tiers}, keep-local brief sent to {leaked}"
    missed = sorted(
        rid for rid in run.planted_bad
        if rid in result.items and result.status(rid) is AttributionStatus.VERIFIED
    )  # fmt: skip
    if missed:
        return "verification_miss", f"planted wrong rationales shown as verified: {missed}"
    if result.stop is not run.expected_stop:
        got = result.stop.value if result.stop else "none"
        want = run.expected_stop.value if run.expected_stop else "none"
        return "bad_stop", f"stopped for {got}; the recording expects {want}"
    if left_over:
        return "bad_stop", f"stopped with {left_over} recorded calls not made"
    if result.accepted >= case.target:
        return SUCCESS, f"{result.accepted} of {case.target} items accepted"
    return "rationale_error", (
        f"{result.accepted} of {case.target} accepted: rationales were unusable or rejected"
    )


def replay_run(
    suite: Suite, case: TrajectoryCase, run: RunSpec, *, loop_overrides: dict | None = None
) -> RunOutcome:
    """Replay one recording through the current loop and classify it."""
    events = read_events(suite.recording(case, run))
    if not events:
        raise FileNotFoundError(f"no recording at {suite.recording(case, run)}")
    tape = _Tape(events, case.brief)
    config = LoopConfig(**{**suite.loop, **(loop_overrides or {})})
    controller = LoopController(config, make_reasoner(suite, tape), clock=lambda: 0.0)
    result, error = None, None
    try:
        result = controller.run(
            brief=case.brief, retrieve=tape.retrieve, target=case.target,
            keep_local=case.keep_local, cap_usd=case.cap_usd,
        )  # fmt: skip
    except ReplayDiverged as diverged:
        error = diverged
    cloud = frozenset(n for n, p in SUITE_PROVIDERS.providers.items() if p.cloud)
    outcome, detail = classify(
        case, run, result, error=error, left_over=tape.left_over if result else 0,
        expected_tier=suite.generator_tier, cloud_providers=cloud,
    )  # fmt: skip
    return RunOutcome(
        case_id=case.id, run=run.index, outcome=outcome, expected=run.expected, detail=detail,
        stop=(result.stop.value if result and result.stop else None),
        accepted=result.accepted if result else 0, rounds=result.rounds if result else 0,
    )  # fmt: skip


@dataclass
class TrajectoryResult:
    suite: Suite
    runs: list[RunOutcome]
    loop_overrides: dict = field(default_factory=dict)
    seed: int = 0
    n_boot: int = 2000
    git_sha: str = ""  # the code replayed; in the hash so a report is never overwritten

    def by_case(self) -> dict[str, list[RunOutcome]]:
        grouped: dict[str, list[RunOutcome]] = {}
        for r in self.runs:
            grouped.setdefault(r.case_id, []).append(r)
        return grouped

    def single_run(self) -> list[float]:
        """Per brief: the share of its k runs that succeed."""
        return [
            sum(r.outcome == SUCCESS for r in runs) / len(runs) for runs in self.by_case().values()
        ]

    def pass_k(self) -> list[float]:
        """Per brief: 1 when all k runs succeed."""
        return [float(all(r.outcome == SUCCESS for r in runs)) for runs in self.by_case().values()]

    def taxonomy(self) -> Counter:
        return Counter(r.outcome for r in self.runs if r.outcome != SUCCESS)

    @property
    def regressions(self) -> list[RunOutcome]:
        return [r for r in self.runs if r.regressed]

    def config_hash(self) -> str:
        payload = {
            "suite": self.suite.version, "suite_sha256": self.suite.sha256(), "k": self.suite.k,
            "loop_overrides": self.loop_overrides, "scorer": SCORER_VERSION, "seed": self.seed,
            "n_boot": self.n_boot, "git_sha": self.git_sha,
        }  # fmt: skip
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def run_trajectory_eval(
    suite: Suite, *, loop_overrides: dict | None = None, seed: int = 0, n_boot: int = 2000,
    git_sha: str = "",
) -> TrajectoryResult:
    runs = [
        replay_run(suite, case, run, loop_overrides=loop_overrides)
        for case in suite.cases
        for run in case.runs
    ]
    return TrajectoryResult(suite, runs, dict(loop_overrides or {}), seed, n_boot, git_sha)


class TrajectoryRegression(AssertionError):
    """A replayed run's outcome differs from the outcome the suite expects."""


def check_gate(result: TrajectoryResult) -> None:
    """Fails when any run's outcome differs from its expected outcome: the CI gate."""
    if result.regressions:
        lines = [
            f"{r.case_id} run {r.run}: expected {r.expected}, got {r.outcome} ({r.detail})"
            for r in result.regressions
        ]
        raise TrajectoryRegression("trajectory regression:\n" + "\n".join(lines))


# --- Report ---


def _ci(values: list[float], seed: int, n_boot: int) -> str:
    mean, low, high = bootstrap_ci(values, seed=seed, n_boot=n_boot)
    return f"{mean:.3f} [{low:.3f}, {high:.3f}]"


def report(result: TrajectoryResult, *, date: str, dirty: bool) -> str:
    s, h = result.suite, result.config_hash()
    tax = result.taxonomy()
    n_failed = sum(tax.values())
    lines = [
        f"# Trajectory eval {date} ({s.version}, {h})",
        "",
        f"Issue #173; PRD 11.7. Suite `{s.root.as_posix()}` (provenance: **{s.provenance}**), "
        f"{len(s.cases)} briefs, k = {s.k} recorded runs each, replayed through the current "
        f"loop with the recordings standing in for the retriever and the model.",
        "",
        "**Plumbing only.** The suite is synthetic and recorded against the mock tiers. The "
        "k runs differ because faults were planted in the recordings, not because a real "
        "model varied, so these numbers say the harness and the loop's handling of planted "
        "faults work, nothing about model reliability (ADR-018).",
        "",
        "## Summary",
        "",
        "| Metric | Mean over briefs [95% CI] |",
        "|---|---|",
        f"| Single-run success (share of a brief's k runs that succeed) | "
        f"{_ci(result.single_run(), result.seed, result.n_boot)} |",
        f"| pass^{s.k} (all {s.k} runs of a brief succeed) | "
        f"{_ci(result.pass_k(), result.seed, result.n_boot)} |",
        "",
        f"Gate: **{'PASS' if not result.regressions else 'FAIL'}**: "
        f"{len(result.regressions)} of {len(result.runs)} runs differ from their expected "
        "outcome.",
        "",
        "## Failed runs by step",
        "",
        "| Step | Runs | Share of failed runs |",
        "|---|---|---|",
    ]
    for category in CATEGORIES:
        share = f"{tax[category] / n_failed:.2f}" if n_failed else "n/a"
        lines.append(f"| {category} | {tax[category]} | {share} |")
    lines += [
        "",
        "## Per brief",
        "",
        "| Brief | Single-run success | pass^k | Run outcomes |",
        "|---|---|---|---|",
    ]
    for case_id, runs in result.by_case().items():
        ok = sum(r.outcome == SUCCESS for r in runs)
        outcomes = ", ".join(r.outcome for r in runs)
        lines.append(
            f"| {case_id} | {ok}/{len(runs)} | {int(ok == len(runs))} | {outcomes} |"
        )
    lines += [
        "",
        "## Runs",
        "",
        "| Brief | Run | Outcome | Expected | Stop | Accepted | Rounds | Why |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in result.runs:
        lines.append(
            f"| {r.case_id} | {r.run} | {r.outcome} | {r.expected} | {r.stop or '-'} | "
            f"{r.accepted} | {r.rounds} | {r.detail} |"
        )
    lines += [
        "",
        "## Config",
        "",
        f"- Config hash `{h}`: suite version and SHA-256 of the manifest and recordings "
        f"(`{s.sha256()[:12]}`), k, loop overrides ({result.loop_overrides or 'none'}), "
        f"scorer `{SCORER_VERSION}`, seed {result.seed}, {result.n_boot} bootstrap draws, "
        "git SHA.",
        f"- Code: `{result.git_sha[:12]}`{' (dirty)' if dirty else ''}. Prompts {s.prompts}; "
        f"loop {s.loop}.",
        "- Reproduce: `uv run python -m refdesk eval-trajectories`.",
        "",
    ]
    return "\n".join(lines)


def write_report(result: TrajectoryResult, *, root: Path, date: str, dirty: bool) -> Path:
    path = root / "evals" / "reports" / f"trajectory-eval-{date}-{result.config_hash()}.md"
    if path.exists():
        raise FileExistsError(f"{path.name} exists; reports are never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report(result, date=date, dirty=dirty), encoding="utf-8")
    return path
