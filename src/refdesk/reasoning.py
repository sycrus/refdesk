"""Generate and verify rationales for a board's items (issue #98; ADR-022; PRD 8B, 10.2).

Runs in phases, so each GPU model loads once per phase (CLAUDE.md, `ModelManager`):

1. **Generate** a rationale for every item (`generator.generate_rationale`).
2. **Code checks** on every rationale (`verifier.check_claims`): no model.
3. **Judge** every rationale that passed the code checks (`judge.judge_rationale`).

Each run gets its own `LLMClient` whose budget is the board's cap (job "board"), so G1 is
real: the client refuses *before* the call that would exceed the cap, the run stops with
"Stopped: budget cap reached", and items not reached say so. Other refusals stop loudly
too: a keep-local brief with a cloud generator is declined (scenario 4); a paid tier
without `--approve`, a missing key or an unreachable provider stops as "source
unavailable". Nothing falls back to another tier.

What breaks without this module: boards would stay retrieval-only, or the steps would be
wired item by item, swapping GPU models for every item and checking the cap nowhere.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from refdesk.generator import GeneratedRationale, generate_rationale
from refdesk.judge import JudgeResult, judge_rationale
from refdesk.llm.client import (
    BudgetExceeded,
    KeepLocalViolation,
    LLMClient,
    LLMPolicyError,
    NoValidJudge,
    ProviderError,
    Transport,
    pick_judge,
)
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.rationale import Prompt, load_prompt, prompt_named
from refdesk.schema import ArtworkRecord
from refdesk.verifier import CodeVerification, check_claims
from refdesk.wording import StopReason

AUTO = "auto"
JOB = "board"
PROMPT_KINDS = ("rationale", "judge", "fit")


@dataclass
class ItemReasoning:
    record_id: str
    generated: GeneratedRationale | None = None
    code: CodeVerification | None = None
    judged: JudgeResult | None = None
    notes: list[str] = field(default_factory=list)  # why something did not happen

    @property
    def cost_usd(self) -> float:
        gen = self.generated.cost_usd if self.generated else 0.0
        return gen + (self.judged.cost_usd if self.judged else 0.0)


@dataclass
class ReasoningOutcome:
    items: dict[str, ItemReasoning]
    spent_usd: float = 0.0
    sent_to: list[str] = field(default_factory=list)
    models_used: dict[str, str] = field(default_factory=dict)
    stop: StopReason | None = None
    stop_detail: str | None = None
    judge_tier: str | None = None


class ModelUnavailable(RuntimeError):
    """A local model could not be loaded (backend down, not enough VRAM)."""


class Interrupted(Exception):
    """Raised by `before_call` to stop before the next model call (the loop controller's
    kill switch and timeout, issue #155)."""

    def __init__(self, reason: StopReason, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _stop_for(error: Exception) -> tuple[StopReason, str]:
    if isinstance(error, Interrupted):
        return error.reason, error.detail
    if isinstance(error, BudgetExceeded):
        return StopReason.BUDGET_CAP, f"The next model call could exceed the cap: {error}"
    if isinstance(error, KeepLocalViolation):
        return StopReason.DECLINED, f"{error}. The brief was not sent anywhere."
    return (
        StopReason.SOURCE_UNAVAILABLE,
        f"{type(error).__name__}: {error}. No other tier was used.",
    )


class Reasoner:
    def __init__(
        self,
        config: ProvidersConfig,
        *,
        generator_tier: str,
        judge_tier: str | None = AUTO,
        judges: list[str] | None = None,
        transport: Transport | None = None,
        env: Mapping[str, str] | None = None,
        approved: bool = False,
        ensure_model: Callable[[str], None] | None = None,
        prompts: Mapping[str, str] | None = None,
    ):
        self.config = config
        self.generator_tier = generator_tier
        self._judge_tier = judge_tier
        self.judges = config.judges if judges is None else judges
        self.transport = transport
        self.env = os.environ if env is None else env
        self.approved = approved
        # Called with a tier's model before each phase; the API passes the ModelManager.
        self._ensure_model = ensure_model or (lambda model: None)
        # Prompt per kind by name ({"fit": "fit-v1"}), pinned in config/retrieval.yaml; a
        # kind left out uses its highest version. Their hashes go into run manifests.
        prompts = prompts or {}
        self.prompts: dict[str, Prompt] = {
            kind: prompt_named(prompts[kind]) if kind in prompts else load_prompt(kind)
            for kind in PROMPT_KINDS
        }

    def ensure_model(self, model: str) -> None:
        try:
            self._ensure_model(model)
        except Exception as error:  # noqa: BLE001 - any load failure stops the run, loudly
            raise ModelUnavailable(f"could not load {model}: {error}") from error

    def judge_tier(self) -> str | None:
        if self._judge_tier != AUTO:
            return self._judge_tier
        try:
            return pick_judge(
                self.config, generator_tier=self.generator_tier, candidates=self.judges
            )
        except NoValidJudge:
            return None

    def _client(self, cap_usd: float) -> LLMClient:
        return LLMClient(
            self.config,
            Budgets({f"{JOB}_budget_usd": cap_usd}),
            env=self.env,
            approved=self.approved,
            transport=self.transport,
        )

    def run(
        self,
        *,
        brief: str,
        records: list[ArtworkRecord],
        keep_local: bool,
        cap_usd: float,
        on_phase: Callable[[str], None] = lambda phase: None,
        before_call: Callable[[], None] = lambda: None,
    ) -> ReasoningOutcome:
        """`before_call` runs before every model call and may raise `Interrupted` to stop
        the run there (the loop controller's kill switch and timeout)."""
        client = self._client(cap_usd)
        outcome = ReasoningOutcome(items={r.id: ItemReasoning(r.id) for r in records})

        def sent(tier: str) -> None:
            provider = self.config.tiers[tier].provider
            if provider not in outcome.sent_to:
                outcome.sent_to.append(provider)

        on_phase("generate")
        model = self.config.tiers[self.generator_tier].model
        try:
            if model:
                self.ensure_model(model)
            for record in records:
                item = outcome.items[record.id]
                before_call()
                item.generated = generate_rationale(
                    client, tier=self.generator_tier, brief=brief, record=record,
                    keep_local=keep_local, job=JOB, prompt=self.prompts["rationale"],
                )  # fmt: skip
                sent(self.generator_tier)
                outcome.models_used["generator"] = item.generated.model_reported or model
                if item.generated.ok:
                    item.code = check_claims(item.generated.rationale, record)
        except (LLMPolicyError, ProviderError, ModelUnavailable, Interrupted) as error:
            outcome.stop, outcome.stop_detail = _stop_for(error)

        judge_tier = self.judge_tier()
        outcome.judge_tier = judge_tier
        if outcome.stop is None and judge_tier is None:
            for item in outcome.items.values():
                item.notes.append(
                    "No judge outside the generator's family is configured; "
                    "claims were checked by code only."
                )
        elif outcome.stop is None:
            on_phase("verify")
            try:
                self.ensure_model(self.config.tiers[judge_tier].model)
                for record in records:
                    item = outcome.items[record.id]
                    if item.code is None or not item.code.passed:
                        continue
                    before_call()
                    item.judged = judge_rationale(
                        client, judge_tier=judge_tier, generator_tier=self.generator_tier,
                        record=record, rationale=item.generated.rationale,
                        keep_local=keep_local, job=JOB, prompt=self.prompts["judge"],
                        fit_prompt=self.prompts["fit"], brief=brief,
                    )  # fmt: skip
                    sent(judge_tier)
                    outcome.models_used["judge"] = (
                        item.judged.model_reported or self.config.tiers[judge_tier].model
                    )
            except (LLMPolicyError, ProviderError, ModelUnavailable, Interrupted) as error:
                outcome.stop, outcome.stop_detail = _stop_for(error)

        if outcome.stop is not None:
            for item in outcome.items.values():
                if item.generated is None:
                    item.notes.append(f"Not explained: {outcome.stop.banner.lower()}.")
                elif item.judged is None and item.code is not None and item.code.passed:
                    item.notes.append(f"Not judged: {outcome.stop.banner.lower()}.")
        outcome.spent_usd = sum(i.cost_usd for i in outcome.items.values())
        return outcome
