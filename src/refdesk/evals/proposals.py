"""Cross-family check of Claude's golden-v1 proposals (ADR-018 step 4, issue #15).

Claude Code proposes, for every case, which pool candidates fit the brief, with a grade,
the record fields the proposal rests on, and a one-line reason. A judge from another
family (`phi4`, ADR-021) checks each one, one at a time at temperature 0, with the same
retry rule as the rationale judge: one retry for a malformed answer, then "invalid".
A judge from Claude's own family is refused before any request.

The judge cannot see the image, so it checks the reason's facts against the record and
whether the work, as described, plausibly fits the brief at that grade. Its relevance
judgement is unmeasured (the judge probe screened false facts, not relevance): its
verdicts flag proposals for Joe, they never decide a label. What breaks without this
module: ADR-018 step 4 would be skipped, and Joe would review proposals no second model
had looked at.
"""

from __future__ import annotations

from refdesk.evals.judge_probe import parse_verdict
from refdesk.judge import MAX_ATTEMPTS
from refdesk.llm.client import LLMClient, NoValidJudge
from refdesk.rationale import Prompt, load_prompt, record_block
from refdesk.schema import ArtworkRecord

PROPOSER_FAMILY = "anthropic"  # Claude Code
GRADES = {2: "fits the whole brief", 1: "fits part of the brief"}


def load_proposal_prompt(version: str | None = None) -> Prompt:
    return load_prompt("proposal", version)


def proposal_messages(
    brief: str, record: ArtworkRecord, proposal: dict, prompt: Prompt
) -> list[dict]:
    grade = proposal["grade"]
    user = (
        f"Brief: {brief}\n\nRecord:\n{record_block(record)}\n\n"
        f"Proposal:\nGrade {grade} ({GRADES[grade]}). Reason: {proposal['reason']}"
    )
    return [{"role": "system", "content": prompt.text}, {"role": "user", "content": user}]


def judge_proposals(
    client: LLMClient,
    case: dict,
    brief: str,
    records: dict[str, ArtworkRecord],
    *,
    judge_tier: str,
    prompt: Prompt | None = None,
) -> list[dict]:
    """Each of the case's proposals with judge_model, judge_family and judge_verdict
    ("supported", "unsupported" or "invalid") added. Briefs never leave the machine."""
    family = client.config.provider_of(judge_tier).family
    if family == PROPOSER_FAMILY:
        raise NoValidJudge(f"judge {judge_tier} is from the proposer's family {family!r}")
    prompt = prompt or load_proposal_prompt()
    judged = []
    for proposal in case["proposals"]:
        messages = proposal_messages(brief, records[proposal["record_id"]], proposal, prompt)
        verdict, model = None, None
        for _ in range(MAX_ATTEMPTS):
            completion = client.complete(
                judge_tier, messages, job="golden-proposals", keep_local=True,
                max_tokens=16, temperature=0,
            )  # fmt: skip
            model = completion.model_reported
            verdict = parse_verdict(completion.text)
            if verdict is not None:
                break
        judged.append(
            proposal
            | {"judge_model": model, "judge_family": family, "judge_verdict": verdict or "invalid"}
        )
    return judged
