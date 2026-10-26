"""Rationale verifier, stage 2: a model judge (issue #97; ADR-021, ADR-022).

`phi4` (family microsoft) checks every claim's text and the fit sentence, one statement
at a time, against the record. One at a time because the hard judge probe (#122) showed
it matters: per statement phi4 caught 40 of 40 subtle errors; on a whole rationale, 82%.
Claims use the probe's exact wording (`prompts/judge-v1.md`), so the measurement applies
to what runs here. The fit sentence uses its own prompt (`prompts/fit-v1.md`): judge-v1
flagged 17 of 20 pure-opinion sentences as unsupported, fit-v1 2 of 20, while catching 19
of 20 smuggled facts (`evals/reports/fit-probe-2026-10-27.md`).

The judge must come from a different provider family than the generator, checked before
any request. Pass rule (Joe, 2026-10-27): SUPPORTED passes, UNSUPPORTED fails, a
malformed answer gets one retry and then counts as a fail.

Stage 1 (code checks, `verifier.check_claims`) runs first; `verifier.item_status` combines
both. What breaks without this stage: a claim whose value is right but whose sentence adds
a fact ("painted for a duke") would pass.
"""

from __future__ import annotations

from dataclasses import dataclass

from refdesk.evals.judge_probe import parse_verdict
from refdesk.llm.client import LLMClient, NoValidJudge
from refdesk.rationale import Prompt, Rationale, load_prompt, record_block
from refdesk.schema import ArtworkRecord
from refdesk.verifier import JudgeVerdict

MAX_ATTEMPTS = 2  # one retry for a malformed answer (Joe, 2026-10-27)


def load_judge_prompt(version: str | None = None) -> Prompt:
    return load_prompt("judge", version)


def load_fit_prompt(version: str | None = None) -> Prompt:
    return load_prompt("fit", version)


def judge_messages(record: ArtworkRecord, statement: str, prompt: Prompt) -> list[dict]:
    user = f"Record:\n{record_block(record)}\n\nRationale:\n{statement}"
    return [{"role": "system", "content": prompt.text}, {"role": "user", "content": user}]


@dataclass(frozen=True)
class JudgeResult:
    verdict: JudgeVerdict
    tier: str
    family: str
    model_reported: str | None
    calls: int
    cost_usd: float
    prompt: str
    prompt_sha256: str
    fit_prompt: str
    fit_prompt_sha256: str


def judge_rationale(
    client: LLMClient,
    *,
    judge_tier: str,
    generator_tier: str,
    record: ArtworkRecord,
    rationale: Rationale,
    keep_local: bool,
    job: str,
    prompt: Prompt | None = None,
    fit_prompt: Prompt | None = None,
) -> JudgeResult:
    config = client.config
    judge_family = config.provider_of(judge_tier).family
    generator_family = config.provider_of(generator_tier).family
    if judge_family == generator_family:
        raise NoValidJudge(f"judge {judge_tier} is from the generator's family {judge_family!r}")
    prompt = prompt or load_judge_prompt()
    fit_prompt = fit_prompt or load_fit_prompt()
    statements = [
        (f"claim {n} ({c.field})", c.text, prompt) for n, c in enumerate(rationale.claims, start=1)
    ] + [("fit sentence", rationale.fit, fit_prompt)]
    failures, calls, cost, model = [], 0, 0.0, None
    for label, statement, statement_prompt in statements:
        verdict = None
        for _ in range(MAX_ATTEMPTS):
            completion = client.complete(
                judge_tier,
                judge_messages(record, statement, statement_prompt),
                job=job,
                keep_local=keep_local,
                max_tokens=16,
                temperature=0,
            )
            calls += 1
            cost += completion.cost_usd
            model = completion.model_reported
            verdict = parse_verdict(completion.text)
            if verdict is not None:
                break
        if verdict is None:
            failures.append(f"{label}: judge answer unusable after {MAX_ATTEMPTS} attempts")
        elif verdict == "unsupported":
            failures.append(f"{label}: the judge found it unsupported")
    return JudgeResult(
        verdict=JudgeVerdict(passed=not failures, failures=tuple(failures)),
        tier=judge_tier,
        family=judge_family,
        model_reported=model,
        calls=calls,
        cost_usd=cost,
        prompt=prompt.name,
        prompt_sha256=prompt.sha256,
        fit_prompt=fit_prompt.name,
        fit_prompt_sha256=fit_prompt.sha256,
    )
