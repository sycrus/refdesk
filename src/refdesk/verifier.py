"""Rationale verifier, stage 1: plain-code checks (issue #96; ADR-022; FR-2, FR-5, FR-6).

Each claim names a record field and a value. Code checks that value against the record:
equal after normalising case and spacing, a date inside the record's years, a subject
that is one of the record's tags. Attribution gets a stricter check: the claim's *text*,
which the operator reads, must also contain the record's full attribution, so "by X"
for a record that says "Workshop of X" fails here, before any model sees it.

Item-level checks: the record must give an attribution, and its rights must have been
read from a structured source field (FR-2).

Stage 2 (issue #97) has `phi4` check each claim's text and the fit sentence. An item is
"Attribution verified from record" only when both stages pass (`item_status`); anything
else, including a missing judge verdict, is "Needs human check" (scenario 6). What breaks
without this module: a claim with a wrong date or a dropped attribution prefix would
depend entirely on a model noticing it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from refdesk.rationale import Claim, Rationale, field_value
from refdesk.schema import ArtworkRecord
from refdesk.wording import AttributionStatus

_YEAR = re.compile(r"\b\d{3,4}\b")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(text.split()).strip(" .,;:")


def _contains_phrase(haystack: str, needle: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


@dataclass(frozen=True)
class ClaimCheck:
    index: int  # 1-based, as named in reasons
    field: str
    value: str
    status: str  # "pass" or "fail"
    reason: str | None = None


@dataclass(frozen=True)
class CodeVerification:
    checks: tuple[ClaimCheck, ...]
    item_failures: tuple[str, ...]

    @property
    def failures(self) -> tuple[str, ...]:
        claim_failures = tuple(c.reason for c in self.checks if c.status == "fail")
        return claim_failures + self.item_failures

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class JudgeVerdict:
    """Stage 2's result for one item (issue #97).

    `passed` covers the claims only. `fit_failure` says why the fit sentence was flagged;
    it does not affect `passed` or the attribution status (Joe, 2026-10-27, issue #135):
    the fit is opinion, so a flag on it is shown on the sentence instead of withholding
    "Attribution verified from record" from claims that passed."""

    passed: bool
    failures: tuple[str, ...]
    fit_failure: str | None = None


def _check_value(claim: Claim, record: ArtworkRecord) -> str | None:
    """Why the claim's value does not match the record, or None when it matches."""
    field = claim.field
    stated = _norm(claim.value)
    if field == "date":
        if record.date is None and record.date_begin is None:
            return "this record has no date"
        years = [int(y) for y in _YEAR.findall(claim.value)]
        if not years:
            ok = record.date is not None and stated == _norm(record.date)
            return None if ok else f"date {claim.value!r} is not the record's {record.date!r}"
        low, high = record.date_begin, record.date_end
        if low is None or high is None:
            ok = record.date is not None and stated == _norm(record.date)
            return None if ok else f"date {claim.value!r} is not the record's {record.date!r}"
        outside = [y for y in years if not low <= y <= high]
        if outside:
            return f"date {claim.value!r} is outside the record's years {low}-{high}"
        return None
    actual = field_value(record, field)
    if actual is None:
        return f"this record has no {field}"
    if field == "subject_tags":
        tags = {_norm(t) for t in record.subject_tags}
        parts = [_norm(p) for p in re.split(r"[;,]", claim.value) if p.strip()]
        missing = [p for p in parts if p not in tags]
        return f"subject {missing[0]!r} is not one of the record's tags" if missing else None
    if field == "classification":
        ok = stated.rstrip("s") == _norm(actual).rstrip("s")
        return None if ok else f"classification {claim.value!r} is not the record's {actual!r}"
    if field == "medium":
        ok = stated == _norm(actual) or _contains_phrase(_norm(actual), stated)
        return None if ok else f"medium {claim.value!r} is not the record's {actual!r}"
    if field == "artist":
        if stated != _norm(actual):
            return f"attribution {claim.value!r} differs from the record's {actual!r}"
        if not _contains_phrase(_norm(claim.text), _norm(actual)):
            return f"attribution in the text differs from the record's {actual!r}"
        return None
    if stated != _norm(actual):
        return f"{field} {claim.value!r} is not the record's {actual!r}"
    return None


def check_claims(rationale: Rationale, record: ArtworkRecord) -> CodeVerification:
    checks = []
    for n, claim in enumerate(rationale.claims, start=1):
        reason = _check_value(claim, record)
        status = "fail" if reason else "pass"
        label = f"claim {n} ({claim.field}): {reason}" if reason else None
        checks.append(ClaimCheck(n, claim.field, claim.value, status, label))
    item_failures = []
    if not record.artist:
        item_failures.append("the record gives no attribution")
    if not record.rights.flag_field:
        item_failures.append("rights were not read from a structured source field")
    return CodeVerification(tuple(checks), tuple(item_failures))


def item_status(code: CodeVerification | None, judged: JudgeVerdict | None) -> AttributionStatus:
    """Verified only when there is a rationale, code checks pass and the judge supported
    every claim. The fit-sentence verdict is not part of it (see `JudgeVerdict`)."""
    if code is None or judged is None or not code.passed or not judged.passed:
        return AttributionStatus.NEEDS_HUMAN_CHECK
    return AttributionStatus.VERIFIED
