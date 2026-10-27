"""Golden-case format and validation (label-golden-cases skill, PRD 11, ADR-018).

A golden case is one brief with the references a good board should contain. v0 cases are
synthetic: written by Claude Code, with expected references derived by an explicit `rule`
applied to the ingested corpus. They exist to build and test the eval harness, never to
support a claim.

`validate_cases` checks what the skill asks for: the format, unique IDs, no near-duplicate
briefs, every reference inside the ingested corpus, the corpus version, and no brief text
leaking into prompt files. It also counts coverage so gaps are visible.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from refdesk.schema import ArtworkRecord, RightsStatus

NEAR_DUPLICATE = 0.8  # token Jaccard between two briefs
_WORD = re.compile(r"[a-z0-9]+")


class ExpectedRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str
    grade: int = Field(ge=1, le=2)  # 2 = matches the whole rule, 1 = partial


class Proposal(BaseModel):
    """One reference Claude Code proposed for a v1 case, the judge's verdict on it, and
    Joe's decision (ADR-018). Blind cases keep proposals undecided: Joe never saw them."""

    model_config = ConfigDict(extra="forbid")
    record_id: str
    grade: int = Field(ge=1, le=2)
    fields: list[str] = Field(min_length=1)  # record fields the proposal rests on
    judge_model: str | None = None
    judge_family: str | None = None
    judge_verdict: Literal["supported", "unsupported", "invalid"] | None = None
    decision: Literal["accepted", "rejected", "regraded"] | None = None

    @model_validator(mode="after")
    def _cross_family(self) -> Proposal:
        if self.judge_family == "anthropic":
            raise ValueError("the judge must not be from Claude's family (ADR-021)")
        return self


class Review(BaseModel):
    """How a v1 case was labelled (ADR-018). What breaks without it: the trust rules
    (gap, anchoring) cannot be computed, so v1 could be frozen with no check on whether
    Joe's review simply accepted Claude's answers."""

    model_config = ConfigDict(extra="forbid")
    blind: bool
    pool: list[str] = []  # blind cases: the unranked candidates Joe labelled
    proposed_by: str = "claude-code"
    proposals: list[Proposal] = []
    relabel: list[str] | None = None  # blind cases: Joe's second pass, a day later
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Review:
        if self.blind:
            if not self.pool:
                raise ValueError("a blind case needs the pool of candidates Joe labelled")
            if any(p.decision for p in self.proposals):
                raise ValueError("blind proposals are never decided: Joe did not see them")
            outside = {p.record_id for p in self.proposals} | set(self.relabel or [])
            if outside - set(self.pool):
                raise ValueError("blind proposals and relabels must come from the pool")
        else:
            if self.relabel is not None:
                raise ValueError("only blind cases have a second pass")
            if self.reviewed_by and any(p.decision is None for p in self.proposals):
                raise ValueError("a reviewed case needs a decision on every proposal")
        return self


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^g\d+-\d{3}$")
    brief: str = Field(min_length=1)
    constraints: dict[str, Any] = {}
    usage_mode: Literal["reference_only", "reproduction"] = "reference_only"
    expected_decision: Literal["retrieve", "decline"] = "retrieve"
    expected: list[ExpectedRef]
    labels: dict[str, Any] = {}
    source: str
    labeller: str
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str] = []
    version: str
    provenance: Literal["synthetic", "human"]
    corpus_version: str
    rule: dict[str, Any] | None = None  # how `expected` was derived (synthetic cases)
    detail: Literal["sparse", "moderate", "rich"] | None = None  # how much the brief says
    review: Review | None = None  # how a human-labelled case was labelled (ADR-018)

    @model_validator(mode="after")
    def _consistent(self) -> GoldenCase:
        if self.expected_decision == "decline" and self.expected:
            raise ValueError("a decline case has no expected references")
        if self.expected_decision == "retrieve" and not self.expected:
            raise ValueError("a retrieve case needs expected references")
        if "synthetic" in self.version and self.provenance != "synthetic":
            raise ValueError("a synthetic version must mark every case provenance: synthetic")
        if self.provenance == "human" and self.review is None:
            raise ValueError("a human-labelled case needs a review record (ADR-018)")
        if self.review and self.review.blind:
            outside = {e.record_id for e in self.expected} - set(self.review.pool)
            if outside:
                raise ValueError(f"blind labels must come from the pool: {sorted(outside)}")
        return self


@dataclass
class ValidationReport:
    cases: list[GoldenCase] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    referenced_records: int = 0


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def validate_cases(
    lines: list[str],
    corpus_ids: set[str],
    corpus_version: str,
    *,
    prompt_texts: dict[str, str] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            report.cases.append(GoldenCase(**json.loads(line)))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            report.errors.append(f"line {number}: {error}".splitlines()[0])

    ids = Counter(c.id for c in report.cases)
    report.errors += [f"duplicate id {i}" for i, n in ids.items() if n > 1]

    for c in report.cases:
        if c.corpus_version != corpus_version:
            report.errors.append(f"{c.id}: corpus_version {c.corpus_version} != {corpus_version}")
        outside = [e.record_id for e in c.expected if e.record_id not in corpus_ids]
        if outside:
            report.errors.append(f"{c.id}: references outside the corpus: {outside}")

    for i, a in enumerate(report.cases):
        for b in report.cases[i + 1 :]:
            if a.id != b.id and _similarity(a.brief, b.brief) >= NEAR_DUPLICATE:
                report.errors.append(f"near-duplicate briefs: {a.id} and {b.id}")

    for path, text in (prompt_texts or {}).items():
        for c in report.cases:
            if c.brief.lower() in text.lower():
                report.errors.append(f"{c.id}: brief leaks into {path}")

    report.counts = {
        key: dict(Counter(getattr(c, key) for c in report.cases))
        for key in ("difficulty", "expected_decision", "usage_mode", "source")
    }
    report.counts["tags"] = dict(Counter(t for c in report.cases for t in c.tags))
    report.referenced_records = len({e.record_id for c in report.cases for e in c.expected})
    return report


# Rules: how golden-v0 expected references are derived. Every clause must hold (AND).
# Deliberately plain so anyone can re-derive a case by hand from the records.


class RuleError(ValueError):
    pass


def _tags(record: ArtworkRecord) -> set[str]:
    return {t.lower() for t in record.subject_tags}


def _century(record: ArtworkRecord) -> int | None:
    begin = record.date_begin
    return begin // 100 + 1 if begin is not None and begin > 0 else None


def _words(text: str | None) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


_CLAUSES: dict[str, Any] = {
    "tags_all": lambda r, v: {t.lower() for t in v} <= _tags(r),
    "tags_any": lambda r, v: bool({t.lower() for t in v} & _tags(r)),
    "century": lambda r, v: _century(r) == v,
    "year_range": lambda r, v: r.date_begin is not None and v[0] <= r.date_begin <= v[1],
    "title_any": lambda r, v: bool({w.lower() for w in v} & _words(r.title)),
    "medium_any": lambda r, v: bool({w.lower() for w in v} & _words(r.medium)),
    "artist_contains": lambda r, v: v.lower() in (r.artist or "").lower(),
    "artist_excludes": lambda r, v: v.lower() not in (r.artist or "").lower(),
    "classification": lambda r, v: r.classification in v,
    "rights": lambda r, v: v == "open" and r.rights.status is RightsStatus.OPEN,
    "exclude_ids": lambda r, v: r.id not in v,
}


def apply_rule(rule: dict[str, Any], records: list[ArtworkRecord]) -> list[str]:
    """Record IDs (sorted) that satisfy every clause of the rule."""
    if not rule:
        raise RuleError("a rule needs at least one clause")
    unknown = set(rule) - set(_CLAUSES)
    if unknown:
        raise RuleError(f"unknown rule clause(s): {sorted(unknown)}")
    return sorted(r.id for r in records if all(_CLAUSES[k](r, v) for k, v in rule.items()))


def corpus_version(records: list[ArtworkRecord]) -> str:
    """'<source>:<count>:<hash of sorted IDs>'. Changes whenever the corpus does."""
    ids = sorted(r.id for r in records)
    sources = "+".join(sorted({r.source for r in records}))
    digest = hashlib.sha256("\n".join(ids).encode()).hexdigest()[:12]
    return f"{sources}:{len(ids)}:{digest}"
