"""Assemble golden-v1 from the labelling files and check the trust rules (ADR-018, issue #15).

Inputs, all per case:
- the draft brief (`briefs-draft.jsonl`);
- Joe's blind pass 1 and pass 2 on the blind pools (`blind-sheet.csv`,
  `blind-sheet-pass2.csv`);
- Claude's proposals with phi4's verdicts (`runs/labelling-v1/proposals-judged.jsonl`);
- Joe's labels on the non-blind pools (`review-sheet.csv`).

Joe's labels are the expected references in every case. On review cases, his decision on
each proposal is derived from his own label of that work: not relevant -> rejected; the
same grade -> accepted; another grade -> regraded. A work he marked relevant that Claude
did not propose is added to `expected` and counted as missed by Claude. Decline cases
carry no references.

Nothing here is frozen: `scripts/golden_v1_report.py` writes the report, and writes
`evals/golden/golden-v1.jsonl` only when Joe asks and the trust rules pass. What breaks
without this module: the trust rules would be applied to hand-built case files, and a
label could be lost or changed on the way from the sheets.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from refdesk.evals.golden import ExpectedRef, GoldenCase, Proposal, Review
from refdesk.evals.labelling import (
    TrustResult,
    _claude_by_case,
    _self_by_case,
    trust_check,
)

VERSION = "v1"
LABELLER = "joe"
SOURCE = "draft:claude-code"
PROPOSAL_KEYS = ("record_id", "grade", "fields", "judge_model", "judge_family", "judge_verdict")


def labels_by_case(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    """Sheet rows grouped by case, then by candidate, in sheet order."""
    out: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        out.setdefault(row["draft_id"], {})[row["candidate"]] = row
    return out


def _done(row: dict[str, str]) -> bool:
    return row["relevant"] == "n" or (row["relevant"] == "y" and row["grade"] in ("1", "2"))


def _expected(rows: dict[str, dict[str, str]]) -> list[ExpectedRef]:
    return [
        ExpectedRef(record_id=rid, grade=int(r["grade"]))
        for rid, r in rows.items()
        if r["relevant"] == "y"
    ]


def decision(proposal: dict, row: dict[str, str]) -> str:
    """Joe's decision on one proposal, read from his own label of that work."""
    if row["relevant"] == "n":
        return "rejected"
    return "accepted" if int(row["grade"]) == proposal["grade"] else "regraded"


@dataclass
class Assembly:
    cases: list[GoldenCase] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # why a case could not be built
    added: Counter = field(default_factory=Counter)  # case -> works Joe added in review
    pass2_complete: bool = False


def assemble(
    *,
    drafts: list[dict],
    blind_ids: set[str],
    corpus_version: str,
    pass1: list[dict[str, str]],
    pass2: list[dict[str, str]] | None,
    proposals: dict[str, dict],
    review: list[dict[str, str]],
    reviewed_at: datetime,
) -> Assembly:
    out = Assembly()
    first, second, reviewed = (
        labels_by_case(pass1),
        labels_by_case(pass2 or []),
        labels_by_case(review),
    )
    out.pass2_complete = pass2 is not None and all(_done(r) for r in pass2)
    for draft in drafts:
        did = draft["draft_id"]
        common = dict(
            id=f"g1-{int(did[1:]):03d}", brief=draft["brief"], usage_mode=draft["usage_mode"],
            expected_decision=draft["expected_decision"], source=SOURCE, labeller=LABELLER,
            difficulty=draft["difficulty"], tags=draft.get("tags", []), version=VERSION,
            provenance="human", corpus_version=corpus_version, detail=draft["detail"],
        )  # fmt: skip
        if draft["expected_decision"] == "decline":
            out.cases.append(GoldenCase(**common, expected=[], review=Review(blind=False)))
            continue
        props = proposals.get(did, {}).get("proposals", [])
        if did in blind_ids:
            rows = first.get(did, {})
            if not rows or not all(_done(r) for r in rows.values()):
                out.problems.append(f"{did}: blind pass 1 is not complete")
                continue
            relabel = None
            if out.pass2_complete:
                relabel = [rid for rid, r in second.get(did, {}).items() if r["relevant"] == "y"]
            built = Review(
                blind=True, pool=list(rows), relabel=relabel,
                proposals=[Proposal(**{k: p[k] for k in PROPOSAL_KEYS}) for p in props],
            )  # fmt: skip
        else:
            rows = reviewed.get(did, {})
            if not rows or not all(_done(r) for r in rows.values()):
                out.problems.append(f"{did}: review is not complete")
                continue
            built = Review(
                blind=False, pool=list(rows), reviewed_by=LABELLER, reviewed_at=reviewed_at,
                proposals=[
                    Proposal(**{k: p[k] for k in PROPOSAL_KEYS},
                             decision=decision(p, rows[p["record_id"]]))
                    for p in props
                ],
            )  # fmt: skip
            proposed = {p["record_id"] for p in props}
            out.added[did] = sum(
                1 for rid, r in rows.items() if r["relevant"] == "y" and rid not in proposed
            )
        expected = _expected(rows)
        if not expected:
            out.problems.append(
                f"{did}: Joe marked no work relevant; a retrieve case needs at least one "
                "(Joe decides: decline it, rewrite the brief, or widen the pool)"
            )
            continue
        out.cases.append(GoldenCase(**common, expected=expected, review=built))
    return out


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _judge_vs_joe(cases: list[GoldenCase]) -> Counter:
    """phi4's verdict against Joe's decision, over reviewed proposals."""
    return Counter(
        (p.judge_verdict, p.decision)
        for c in cases
        if c.review and not c.review.blind
        for p in c.review.proposals
    )


def report(
    assembly: Assembly, *, title: str, caveats: list[str], seed: int = 0
) -> tuple[str, TrustResult | None]:
    cases = assembly.cases
    blind = [c for c in cases if c.review and c.review.blind]
    reviewed = [c for c in cases if c.review and not c.review.blind and c.review.reviewed_by]
    lines = [
        f"# {title}",
        "",
        "> golden-v1 trust check (ADR-018, issue #15). Labels by Joe; proposals by Claude "
        "Code, checked by phi4. Not frozen by this report.",
        "",
    ]
    lines += [
        "## Cases",
        "",
        f"- Built: {len(cases)} ({len(blind)} blind, {len(reviewed)} reviewed, "
        f"{sum(c.expected_decision == 'decline' for c in cases)} decline)",
        f"- Not built: {len(assembly.problems)}",
        *[f"  - {p}" for p in assembly.problems],
        "",
    ]
    result = None
    if blind and assembly.pass2_complete:
        result = trust_check(cases, seed=seed)
        anchoring = result.anchoring_verdict if reviewed else "pending (no reviewed cases yet)"
        lines += [
            "## Trust rules",
            "",
            "| Measure | Value |",
            "|---|---|",
            f"| Claude's agreement with Joe's blind labels | {_pct(result.claude_agreement)} |",
            f"| Joe's self-agreement (pass 1 vs pass 2) | {_pct(result.self_agreement)} |",
            f"| Gap (self minus Claude), points, 95% CI | {result.gap_points:.1f} "
            f"[{result.gap_interval[0]:.1f}, {result.gap_interval[1]:.1f}] |",
            f"| **Gap verdict** (at most 5 points) | **{result.gap_verdict}** |",
            f"| Blind disagreement (Claude's proposals Joe did not pick at that grade) | "
            f"{_pct(result.blind_disagreement)} |",
            "| Correction rate in review (rejected or regraded) | "
            f"{_pct(result.correction_rate)} |",
            f"| **Anchoring verdict** (corrections at most 5 points below blind disagreement) | "
            f"**{anchoring}** |",
            "",
            "## By detail level (blind cases)",
            "",
            "| Detail | Cases | Claude agreement | Self-agreement |",
            "|---|---|---|---|",
        ]
        for level in ("sparse", "moderate", "rich"):
            group = [c for c in blind if c.detail == level]
            if group:
                claude = sum(map(_claude_by_case, group)) / len(group)
                own = sum(map(_self_by_case, group)) / len(group)
                lines.append(f"| {level} | {len(group)} | {_pct(claude)} | {_pct(own)} |")
        lines.append("")
    else:
        lines += ["## Trust rules", "", "Pending: Joe's second blind pass is not complete.", ""]
    if reviewed:
        table = _judge_vs_joe(cases)
        lines += [
            "## Review",
            "",
            f"- Works Joe added that Claude did not propose: {sum(assembly.added.values())}",
            "- phi4's verdict against Joe's decision (reviewed proposals):",
            "",
            "| phi4 | accepted | regraded | rejected |",
            "|---|---|---|---|",
        ]
        for verdict in ("supported", "unsupported", "invalid"):
            row = [table[(verdict, d)] for d in ("accepted", "regraded", "rejected")]
            if any(row):
                lines.append(f"| {verdict} | " + " | ".join(map(str, row)) + " |")
        lines.append("")
    if caveats:
        lines += ["## Caveats", "", *[f"- {c}" for c in caveats], ""]
    return "\n".join(lines), result
