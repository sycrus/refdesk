"""Routing-label pipeline (issue #161; PRD 10.3, 12; ADR-021, ADR-022).

Builds the labels Kev's Q1 ("which tier?") is trained on. For each synthetic brief:

1. retrieve the top-k records once (the same records for every tier, so tiers compete on
   the same items);
2. every configured routing tier generates a rationale per record (`generator`);
3. code checks (`verifier.check_claims`) and the `phi4` claim judge (`judge`) verify them;
4. the label is the **cheapest tier that met the quality bar**: the first tier in routing
   order (cheapest first, ADR-020) whose verified share reached
   `quality_bar.min_verified_share` (config/labelling.yaml; a placeholder until M4-01,
   #153, and written into every manifest while it is one).

Rules this module enforces, each tested in tests/test_routing_labels.py:

- **A model never judges its own family's output** (ADR-021). The judge is picked per tier
  from a family other than the generator's, at startup. If any tier has no valid judge the
  pipeline refuses to start (`NoValidJudge`), before any request. Both families are written
  to every label.
- **A blocked paid call is a hard error.** At startup a paid tier needs a key, a
  `labelling_budget_usd` and `--approve` (unless this is a dry run, which makes no
  request). During the run one `LLMClient` holds the whole job to that budget and refuses
  before the call that would exceed it. Every refusal and provider failure propagates: no
  label is written for a tier that was not run, and nothing falls back to the mock.
- **Phases.** Each tier generates for every brief, then its judge runs over every
  rationale, so each GPU model loads once per phase (`ensure_model`, the ModelManager).
- **Where briefs went.** Every label lists the providers its brief was sent to. The briefs
  are synthetic (`provenance: synthetic`), never operator briefs, so `keep_local` is off.

What breaks without it: Kev would have no labels to train on, or labels made by a judge
grading its own family, which biases them towards that family's tier (ADR-021).
Not built here: resume after a stop (a stopped run writes nothing; re-run it), and the
judge's agreement with Joe's ratings (#16), which must be reported before labels are used.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, ConfigDict

from refdesk.generator import MAX_ATTEMPTS as GEN_ATTEMPTS
from refdesk.generator import generate_rationale
from refdesk.judge import MAX_ATTEMPTS as JUDGE_ATTEMPTS
from refdesk.judge import judge_messages, judge_rationale
from refdesk.llm.client import (
    CallObservation,
    LLMClient,
    MissingBudget,
    MissingKey,
    NotApproved,
    Transport,
    pick_judge,
)
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.rationale import Prompt, load_prompt, rationale_messages
from refdesk.schema import ArtworkRecord
from refdesk.verifier import item_status
from refdesk.wording import AttributionStatus

JOB = "labelling"  # budget key: labelling_budget_usd in config/budgets.yaml
GEN_MAX_TOKENS = 600  # generator.generate_rationale's default
JUDGE_MAX_TOKENS = 16  # judge.judge_rationale's
# Statements the judge checks per item (claims plus the fit sentence). Unknown before
# generation, so the dry run assumes this many; the client still enforces the budget.
EST_STATEMENTS_PER_ITEM = 5


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityBar(_Model):
    min_verified_share: float
    placeholder: bool = True


class LabellingSettings(_Model):
    n_briefs: int
    seed: int
    items_per_brief: int
    retriever: str
    quality_bar: QualityBar

    @classmethod
    def load(cls, path: str | Path = "config/labelling.yaml") -> LabellingSettings:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data["labelling"])


# --- synthetic briefs -------------------------------------------------------------------

# Brief types are kept as a field so a whole type can be held out later (PRD 10.3, out of
# domain). Vocabulary is generic painting subject matter, not drawn from golden-set briefs.
SUBJECTS = (
    "flowers", "horses", "the sea", "ships", "a harbour", "mountains", "a river", "a forest",
    "a city street", "a portrait of a woman", "a portrait of a man", "children", "dogs",
    "birds", "fruit", "a still life", "a winter landscape", "a garden", "cattle", "a church",
    "musicians", "a storm", "the moon", "boats on a lake", "a market", "soldiers", "angels",
    "a bridge", "trees", "a village",
)  # fmt: skip
MOODS = (
    "calm", "dramatic", "melancholy", "joyful", "mysterious", "warm", "cold", "stormy",
    "quiet", "festive", "dark", "luminous",
)  # fmt: skip
USES = (
    "a tea tin", "a book cover", "a concert poster", "a wine label", "a hotel lobby",
    "a calendar", "a theatre programme", "a greeting card", "a museum shop scarf",
    "a mood board", "a film title sequence", "a restaurant menu",
)  # fmt: skip
PERIODS = ("the 1600s", "the 1700s", "the 1800s", "the early 1900s", "the Dutch Golden Age")
MEDIA = ("oil on canvas", "watercolour", "oil on wood", "tempera")
TEMPLATES = {
    "use": "{mood} {subject} for {use}",
    "period": "{subject} from {period}, {mood} in tone",
    "medium": "{subject} in {medium}, something {mood}",
    "combined": "{mood} {subject} in {medium} for {use}",
}


@dataclass(frozen=True)
class SyntheticBrief:
    id: str
    brief: str
    brief_type: str
    seed: int
    provenance: str = "synthetic"


def synthetic_briefs(n: int, *, seed: int) -> list[SyntheticBrief]:
    """`n` distinct template briefs, deterministic for a seed. Written by code, never by
    an operator: these may go to cloud tiers."""
    rng = random.Random(seed)
    seen: set[str] = set()
    out: list[SyntheticBrief] = []
    types = list(TEMPLATES)
    while len(out) < n:
        brief_type = types[len(out) % len(types)]
        text = TEMPLATES[brief_type].format(
            subject=rng.choice(SUBJECTS), mood=rng.choice(MOODS), use=rng.choice(USES),
            period=rng.choice(PERIODS), medium=rng.choice(MEDIA),
        )  # fmt: skip
        text = text[0].upper() + text[1:]
        if text in seen:
            continue
        seen.add(text)
        out.append(SyntheticBrief(f"syn-{seed}-{len(out):05d}", text, brief_type, seed))
    return out


# --- retrieval --------------------------------------------------------------------------


class BriefRetriever(Protocol):
    def records_for(self, brief: str, k: int) -> list[ArtworkRecord]: ...


class StoreRetriever:
    """A registry retriever over the store's records, answering with records."""

    def __init__(self, name: str, records: list[ArtworkRecord]):
        from refdesk.retrieval import Query
        from refdesk.retrieval.registry import build_retriever

        self._query = Query
        self.retriever = build_retriever(name, records)
        self.by_id = {r.id: r for r in records}

    def records_for(self, brief: str, k: int) -> list[ArtworkRecord]:
        hits = self.retriever.search(self._query(brief=brief, k=k))
        return [self.by_id[h.record_id] for h in hits[:k] if h.record_id in self.by_id]


# --- dry-run estimate -------------------------------------------------------------------


@dataclass(frozen=True)
class TierEstimate:
    tier: str
    judge_tier: str
    generation_calls: int
    judge_calls: int
    tokens_in: int
    tokens_out_max: int
    cost_usd: float  # one attempt per call, every output at max_tokens
    worst_case_cost_usd: float  # every call retried once


@dataclass(frozen=True)
class Estimate:
    briefs: int
    briefs_with_records: int
    tiers: list[TierEstimate]
    budget_usd: float | None

    @property
    def cost_usd(self) -> float:
        return sum(t.cost_usd for t in self.tiers)

    @property
    def worst_case_cost_usd(self) -> float:
        return sum(t.worst_case_cost_usd for t in self.tiers)

    @property
    def fits_budget(self) -> bool:
        if self.worst_case_cost_usd == 0:
            return True
        return self.budget_usd is not None and self.worst_case_cost_usd <= self.budget_usd


def format_estimate(e: Estimate) -> str:
    lines = [
        f"Dry run: {e.briefs} synthetic briefs, {e.briefs_with_records} with retrieved records.",
        "| Tier | Judge | Generation calls | Judge calls (est.) | Tokens in | Tokens out (max) "
        "| Cost USD | Worst case USD (one retry each) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for t in e.tiers:
        lines.append(
            f"| {t.tier} | {t.judge_tier} | {t.generation_calls} | {t.judge_calls} | "
            f"{t.tokens_in} | {t.tokens_out_max} | {t.cost_usd:.4f} | {t.worst_case_cost_usd:.4f} |"
        )
    budget = "none set" if e.budget_usd is None else f"{e.budget_usd:.2f}"
    verdict = "within" if e.fits_budget else "OVER"
    lines += [
        f"Total: {e.cost_usd:.4f} USD; worst case {e.worst_case_cost_usd:.4f} USD; "
        f"labelling_budget_usd {budget}: worst case {verdict} budget.",
        f"Judge calls assume {EST_STATEMENTS_PER_ITEM} statements per item. Token counts use "
        "the client's estimate (about 4 characters per token); output is at max_tokens.",
        "No request was made. A paid run needs a key in .env and --approve.",
    ]
    return "\n".join(lines)


# --- the pipeline -----------------------------------------------------------------------


@dataclass
class LabellingResult:
    settings: LabellingSettings
    tiers: list[str]
    judge_for: dict[str, str]
    briefs: list[SyntheticBrief]
    labels: list[dict[str, Any]]
    prompts: dict[str, str]  # name -> sha256
    models_reported: dict[str, list[str]]
    spent_usd: float
    approved: bool
    corpus: dict[str, Any] = field(default_factory=dict)

    def config_hash(self) -> str:
        fields = {
            "settings": self.settings.model_dump(),
            "tiers": self.tiers,
            "judge_for": self.judge_for,
            "prompts": self.prompts,
            "briefs_sha256": hashlib.sha256(
                "\n".join(b.brief for b in self.briefs).encode()
            ).hexdigest(),
            "corpus": self.corpus,
        }
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:12]


class LabellingPipeline:
    def __init__(
        self,
        config: ProvidersConfig,
        budgets: Budgets,
        settings: LabellingSettings,
        *,
        tiers: list[str] | None = None,
        judges: list[str] | None = None,
        env: Mapping[str, str] | None = None,
        approved: bool = False,
        transport: Transport | None = None,
        ensure_model: Callable[[str], None] | None = None,
        dry_run: bool = False,
        prompts: Mapping[str, str] | None = None,
    ):
        self.config = config
        self.budgets = budgets
        self.settings = settings
        self.tiers = list(config.routing if tiers is None else tiers)
        self.judges = list(config.judges if judges is None else judges)
        self.approved = approved
        self.calls: list[CallObservation] = []
        self._ensure_model = ensure_model or (lambda model: None)
        self.client = LLMClient(
            config, budgets, env=env, approved=approved, transport=transport,
            observe=self.calls.append,
        )  # fmt: skip
        from refdesk.rationale import prompt_named

        prompts = prompts or {}
        self.prompts: dict[str, Prompt] = {
            kind: prompt_named(prompts[kind]) if kind in prompts else load_prompt(kind)
            for kind in ("rationale", "judge", "fit")
        }
        # Startup checks, before any request. A tier with no judge outside its family
        # stops everything (NoValidJudge), so no tier is labelled by code checks alone.
        self.judge_for = {
            tier: pick_judge(config, generator_tier=tier, candidates=self.judges)
            for tier in self.tiers
        }
        if not dry_run:
            for tier in [*self.tiers, *self.judge_for.values()]:
                self._check_paid(tier)

    def _check_paid(self, tier: str) -> None:
        provider = self.config.provider_of(tier)
        if not provider.paid:
            return
        if not self.client.env.get(provider.key_env or ""):
            raise MissingKey(f"tier {tier}: {provider.key_env} is not set (.env)")
        if self.budgets.for_job(JOB) is None:
            raise MissingBudget(f"tier {tier} is paid; no {JOB}_budget_usd in budgets.yaml")
        if not self.approved:
            raise NotApproved(f"tier {tier} is paid; run the dry run, then --approve")

    # -- dry run --

    def estimate(self, briefs: list[SyntheticBrief], retriever: BriefRetriever) -> Estimate:
        """Calls, tokens and cost of a run, from the real prompts. Makes no request."""
        k = self.settings.items_per_brief
        pairs = [(b, r) for b in briefs for r in retriever.records_for(b.brief, k)]
        tiers = []
        for tier, judge in self.judge_for.items():
            tokens_in = tokens_out = 0
            cost = 0.0
            for brief, record in pairs:
                gen = self.client.estimate(
                    tier, rationale_messages(brief.brief, record, self.prompts["rationale"]),
                    max_tokens=GEN_MAX_TOKENS,
                )  # fmt: skip
                # One representative statement per judge call; the record dominates its size.
                jm = judge_messages(record, "x" * 80, self.prompts["judge"], brief.brief)
                one_judge = self.client.estimate(judge, jm, max_tokens=JUDGE_MAX_TOKENS)
                tokens_in += gen.tokens_in + EST_STATEMENTS_PER_ITEM * one_judge.tokens_in
                tokens_out += gen.tokens_out_max + EST_STATEMENTS_PER_ITEM * JUDGE_MAX_TOKENS
                cost += gen.cost_usd + EST_STATEMENTS_PER_ITEM * one_judge.cost_usd
            worst = cost * max(GEN_ATTEMPTS, JUDGE_ATTEMPTS)
            tiers.append(
                TierEstimate(
                    tier,
                    judge,
                    len(pairs),
                    EST_STATEMENTS_PER_ITEM * len(pairs),
                    tokens_in,
                    tokens_out,
                    cost,
                    worst,
                )  # fmt: skip
            )
        with_records = len({b.id for b, _ in pairs})
        return Estimate(len(briefs), with_records, tiers, self.budgets.for_job(JOB))

    # -- the run --

    def run(self, briefs: list[SyntheticBrief], retriever: BriefRetriever) -> LabellingResult:
        k = self.settings.items_per_brief
        records = {b.id: retriever.records_for(b.brief, k) for b in briefs}
        attempts: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        models: dict[str, set[str]] = defaultdict(set)
        for tier in self.tiers:
            self._run_tier(tier, briefs, records, attempts[tier], models)
        labels = [self._label(b, records[b.id], attempts) for b in briefs]
        return LabellingResult(
            settings=self.settings, tiers=self.tiers, judge_for=self.judge_for,
            briefs=briefs, labels=labels,
            prompts={p.name: p.sha256 for p in self.prompts.values()},
            models_reported={t: sorted(m) for t, m in models.items()},
            spent_usd=self.client.spent[JOB], approved=self.approved,
        )  # fmt: skip

    def _run_tier(self, tier, briefs, records, out, models) -> None:
        judge = self.judge_for[tier]
        generated: dict[tuple[str, str], Any] = {}
        # Phase 1: generate (one model load). Any refusal or provider error propagates.
        self._ensure_model(self.config.tiers[tier].model)
        for brief in briefs:
            for record in records[brief.id]:
                g = generate_rationale(
                    self.client, tier=tier, brief=brief.brief, record=record,
                    keep_local=False, job=JOB, prompt=self.prompts["rationale"],
                )  # fmt: skip
                generated[brief.id, record.id] = g
                if g.model_reported:
                    models[tier].add(g.model_reported)
        # Phase 2: code checks, then the judge (one model load) on what passed them.
        from refdesk.verifier import check_claims

        self._ensure_model(self.config.tiers[judge].model)
        for brief in briefs:
            items = []
            for record in records[brief.id]:
                g = generated[brief.id, record.id]
                code = check_claims(g.rationale, record) if g.ok else None
                judged = None
                if code is not None and code.passed:
                    judged = judge_rationale(
                        self.client, judge_tier=judge, generator_tier=tier, record=record,
                        rationale=g.rationale, keep_local=False, job=JOB,
                        prompt=self.prompts["judge"], fit_prompt=self.prompts["fit"],
                        brief=brief.brief,
                    )  # fmt: skip
                    if judged.model_reported:
                        models[judge].add(judged.model_reported)
                verdict = judged.verdict if judged else None
                reasons = (
                    ([g.failure] if g.failure else [])
                    + (list(code.failures) if code else [])
                    + (list(verdict.failures) if verdict else [])
                )
                items.append({
                    "record_id": record.id,
                    "usable": g.ok,
                    "code_pass": bool(code and code.passed),
                    "judge_pass": bool(verdict and verdict.passed),
                    "fit_pass": bool(verdict and verdict.fit_failure is None),
                    "verified": item_status(code, verdict) is AttributionStatus.VERIFIED,
                    "reasons": reasons,
                    "cost_usd": g.cost_usd + (judged.cost_usd if judged else 0.0),
                })  # fmt: skip
            share = sum(i["verified"] for i in items) / len(items) if items else 0.0
            out[brief.id] = {
                "generator_tier": tier,
                "generator_family": self.config.provider_of(tier).family,
                "generator_provider": self.config.tiers[tier].provider,
                "judge_tier": judge,
                "judge_family": self.config.provider_of(judge).family,
                "judge_provider": self.config.tiers[judge].provider,
                "verified_share": share,
                "met_bar": bool(items) and share >= self.settings.quality_bar.min_verified_share,
                "cost_usd": sum(i["cost_usd"] for i in items),
                "items": items,
            }

    def _label(self, brief, records, attempts) -> dict[str, Any]:
        row: dict[str, Any] = {
            "brief_id": brief.id,
            "brief": brief.brief,
            "brief_type": brief.brief_type,
            "provenance": brief.provenance,
            "record_ids": [r.id for r in records],
            "quality_bar": self.settings.quality_bar.min_verified_share,
            "quality_bar_placeholder": self.settings.quality_bar.placeholder,
        }
        if not records:
            return row | {
                "label": None, "label_reason": "no retrieved records", "sent_to": [],
                "generator_family": None, "judge_family": None, "tiers": {},
            }  # fmt: skip
        tiers = {t: attempts[t][brief.id] for t in self.tiers}
        label = next((t for t in self.tiers if tiers[t]["met_bar"]), None)
        sent_to: list[str] = []
        for a in tiers.values():
            for p in (a["generator_provider"], a["judge_provider"]):
                if p not in sent_to:
                    sent_to.append(p)
        return row | {
            "label": label,
            "label_reason": "cheapest tier that met the quality bar"
            if label
            else "no tier met the quality bar",
            "generator_family": tiers[label]["generator_family"] if label else None,
            "judge_family": tiers[label]["judge_family"] if label else None,
            "sent_to": sent_to,
            "tiers": tiers,
        }


# --- outputs ----------------------------------------------------------------------------


def write_outputs(result: LabellingResult, *, root: Path, date: str) -> dict[str, Path]:
    """runs/routing-labels/<date>-<config hash>/: briefs.jsonl, labels.jsonl and
    manifest.json. Never overwrites a previous run."""
    h = result.config_hash()
    run_dir = root / "runs" / "routing-labels" / f"{date}-{h}"
    if (run_dir / "manifest.json").exists():
        raise FileExistsError(f"{run_dir.as_posix()} exists; label runs are never overwritten")
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "briefs.jsonl").open("w", encoding="utf-8") as f:
        for b in result.briefs:
            f.write(json.dumps(asdict(b)) + "\n")
    with (run_dir / "labels.jsonl").open("w", encoding="utf-8") as f:
        for row in result.labels:
            f.write(json.dumps(row) + "\n")
    counts = Counter(row["label"] or "none" for row in result.labels)
    reasons = Counter(row["label_reason"] for row in result.labels)
    manifest = {
        "kind": "routing-labels",
        "config_hash": h,
        "date": date,
        "provenance": "synthetic",
        "settings": result.settings.model_dump(),
        "quality_bar": result.settings.quality_bar.model_dump(),
        "quality_bar_note": "PLACEHOLDER until M4-01 (#153) sets it"
        if result.settings.quality_bar.placeholder
        else "set by Joe",
        "tiers": result.tiers,
        "judge_for": result.judge_for,
        "prompts": result.prompts,
        "models_reported": result.models_reported,
        "corpus": result.corpus,
        "approved": result.approved,
        "spent_usd": round(result.spent_usd, 6),
        "counts": {
            "briefs": len(result.briefs),
            "labelled": dict(counts),
            "label_reasons": dict(reasons),
        },
        "trust": "Not trusted until the judge's agreement with Joe's ratings on 100 sampled "
        "rows is reported (PRD 10.3, #16).",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "dir": run_dir,
        "briefs": run_dir / "briefs.jsonl",
        "labels": run_dir / "labels.jsonl",
        "manifest": run_dir / "manifest.json",
    }


def corpus_digest(records: list[ArtworkRecord]) -> dict[str, Any]:
    ids = sorted(r.id for r in records)
    return {"records": len(ids), "ids_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest()}
