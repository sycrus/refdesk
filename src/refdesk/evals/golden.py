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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from refdesk.schema import ArtworkRecord, RightsStatus

NEAR_DUPLICATE = 0.8  # token Jaccard between two briefs
_WORD = re.compile(r"[a-z0-9]+")


class ExpectedRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str
    grade: int = Field(ge=1, le=2)  # 2 = matches the whole rule, 1 = partial


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

    @model_validator(mode="after")
    def _consistent(self) -> GoldenCase:
        if self.expected_decision == "decline" and self.expected:
            raise ValueError("a decline case has no expected references")
        if self.expected_decision == "retrieve" and not self.expected:
            raise ValueError("a retrieve case needs expected references")
        if "synthetic" in self.version and self.provenance != "synthetic":
            raise ValueError("a synthetic version must mark every case provenance: synthetic")
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
