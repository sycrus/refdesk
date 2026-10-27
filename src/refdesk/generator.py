"""Rationale generator (issue #95; ADR-020, ADR-022; FR-5, FR-11).

One retrieved record and the brief in, a structured rationale out. The prompt holds only
the record's own fields, marked as data (`rationale_messages`). Every call goes through
`LLMClient`, so keep-local, budget and approval checks run before any request, and their
refusals stay hard errors: a blocked call is never turned into a "failed rationale".

An answer that is not a usable rationale is retried once, then returned as failed with
the reason. A failed rationale is never shown as verified; the item becomes
"Needs human check". What breaks without this: either a malformed answer reaches the
board, or one flaky answer drops an item that a second try would have explained.
"""

from __future__ import annotations

from dataclasses import dataclass

from refdesk.llm.client import LLMClient
from refdesk.rationale import (
    Prompt,
    Rationale,
    RationaleError,
    load_prompt,
    parse_rationale,
    rationale_messages,
)
from refdesk.schema import ArtworkRecord

MAX_ATTEMPTS = 2  # one retry for an unusable answer (Joe, 2026-10-27, issue #97)


@dataclass(frozen=True)
class GeneratedRationale:
    record_id: str
    rationale: Rationale | None
    failure: str | None  # why there is no rationale, shown with "Needs human check"
    attempts: int
    tier: str
    provider: str
    family: str
    model_requested: str
    model_reported: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_s: float
    prompt: str
    prompt_sha256: str

    @property
    def ok(self) -> bool:
        return self.rationale is not None


def generate_rationale(
    client: LLMClient,
    *,
    tier: str,
    brief: str,
    record: ArtworkRecord,
    keep_local: bool,
    job: str,
    prompt: Prompt | None = None,
    max_tokens: int = 600,
) -> GeneratedRationale:
    prompt = prompt or load_prompt("rationale")
    messages = rationale_messages(brief, record, prompt)
    totals = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "latency_s": 0.0}
    rationale, failure, completion = None, None, None
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        completion = client.complete(
            tier, messages, job=job, keep_local=keep_local, max_tokens=max_tokens
        )
        for key in totals:
            totals[key] += getattr(completion, key)
        try:
            rationale = parse_rationale(completion.text, record)
            failure = None
            break
        except RationaleError as error:
            failure = f"rationale unusable after {attempts} attempt(s): {error}"
    return GeneratedRationale(
        record_id=record.id,
        rationale=rationale,
        failure=failure,
        attempts=attempts,
        tier=completion.tier,
        provider=completion.provider,
        family=completion.family,
        model_requested=completion.model_requested,
        model_reported=completion.model_reported,
        tokens_in=totals["tokens_in"],
        tokens_out=totals["tokens_out"],
        cost_usd=totals["cost_usd"],
        latency_s=totals["latency_s"],
        prompt=prompt.name,
        prompt_sha256=prompt.sha256,
    )
