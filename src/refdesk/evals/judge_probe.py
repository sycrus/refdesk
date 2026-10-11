"""Judge probe: can a model tell a faithful rationale from one with a false fact?

Synthetic items with answers known by construction (FR-5; evidence for ADR-021):
- a faithful rationale states only record facts (title, artist, date, medium, a subject
  tag) plus opinion about mood and fit, which is not a factual claim;
- a corrupted rationale is the same sentence with exactly one false fact: wrong date,
  wrong artist (another artist from the corpus), wrong medium, an invented provenance,
  or a subject the record does not mention.

Rationales come from templates, not a model, so every label is exact. This measures
fact-catching on simple, single-sentence rationales. It is not agreement with Joe's
judgement (that needs the 100 ratings, issue #16), and real rationales are harder.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field

from refdesk.evals.scorers import bootstrap_ci
from refdesk.schema import ArtworkRecord

ERROR_TYPES = (
    "wrong_date",
    "wrong_artist",
    "wrong_medium",
    "invented_provenance",
    "invented_subject",
)
OPINIONS = (
    "gives a calm, atmospheric feel that suits the label",
    "brings a quiet, reflective mood the brief asks for",
    "has the understated tone this campaign needs",
)
INVENTED_SUBJECTS = ("a lighthouse", "a hot-air balloon", "a steam locomotive", "a windmill")
WRONG_MEDIA = ("watercolour on paper", "tempera on panel", "pastel on vellum")


@dataclass(frozen=True)
class JudgeItem:
    id: str
    record_id: str
    document: str
    rationale: str
    label: str  # "supported" or "unsupported"
    error_type: str | None = None


def record_document(r: ArtworkRecord) -> str:
    return "\n".join([
        f"Title: {r.title}", f"Artist: {r.artist}", f"Date: {r.date}", f"Medium: {r.medium}",
        f"Classification: {r.classification}", f"Subjects: {', '.join(r.subject_tags)}",
    ])  # fmt: skip


def _sentence(title, artist, date, medium, subject, opinion, extra=""):
    facts = f"{title} by {artist}, dated {date}, {medium.lower()}"
    return f"{facts}: its {subject} subject {opinion}{extra}."


def _eligible(records: list[ArtworkRecord]) -> list[ArtworkRecord]:
    return [
        r for r in records
        if r.title and r.artist and r.date and r.medium and r.subject_tags
        and r.date_begin is not None and "watercolour" not in r.medium.lower()
    ]  # fmt: skip


def build_items(records: list[ArtworkRecord], *, n_records: int = 30, seed: int = 0):
    rng = random.Random(seed)
    pool = sorted(_eligible(records), key=lambda r: r.id)
    chosen = rng.sample(pool, n_records)
    artists = sorted({r.artist for r in pool})
    items = []
    for n, r in enumerate(chosen):
        subject = r.subject_tags[0].lower()
        opinion = OPINIONS[n % len(OPINIONS)]
        parts = dict(
            title=r.title,
            artist=r.artist,
            date=r.date,
            medium=r.medium,
            subject=subject,
            opinion=opinion,
        )
        doc = record_document(r)
        items.append(JudgeItem(f"j{n:03d}a", r.id, doc, _sentence(**parts), "supported"))

        error = ERROR_TYPES[n % len(ERROR_TYPES)]
        bad = dict(parts)
        extra = ""
        if error == "wrong_date":
            bad["date"] = str(r.date_begin + 150)
        elif error == "wrong_artist":
            bad["artist"] = rng.choice([a for a in artists if a != r.artist])
        elif error == "wrong_medium":
            bad["medium"] = rng.choice(WRONG_MEDIA)
        elif error == "invented_provenance":
            extra = "; it once belonged to Empress Josephine"
        elif error == "invented_subject":
            bad["subject"] = rng.choice(INVENTED_SUBJECTS)
        items.append(
            JudgeItem(f"j{n:03d}b", r.id, doc, _sentence(**bad, extra=extra), "unsupported", error)
        )
    return items


_FIRST_WORD = re.compile(r"[A-Za-z]+")


def parse_verdict(text: str) -> str | None:
    """SUPPORTED/UNSUPPORTED (general judges) or Yes/No (fact-check models)."""
    match = _FIRST_WORD.search(text or "")
    word = match.group(0).lower() if match else ""
    return {"supported": "supported", "yes": "supported",
            "unsupported": "unsupported", "no": "unsupported"}.get(word)  # fmt: skip


@dataclass
class JudgeScore:
    n: int
    accuracy: float
    accuracy_ci: tuple[float, float]
    catch_rate: float  # corrupted items flagged unsupported
    false_alarm_rate: float  # faithful items flagged unsupported
    invalid_rate: float
    catch_by_type: dict[str, float] = field(default_factory=dict)


def score_judge(items: list[JudgeItem], predictions: list[str | None], *, seed: int = 0):
    correct = [float(p == i.label) for i, p in zip(items, predictions, strict=True)]
    _, low, high = bootstrap_ci(correct, seed=seed)
    bad = [(i, p) for i, p in zip(items, predictions, strict=True) if i.label == "unsupported"]
    good = [(i, p) for i, p in zip(items, predictions, strict=True) if i.label == "supported"]
    by_type = Counter(i.error_type for i, _ in bad)
    caught = Counter(i.error_type for i, p in bad if p == "unsupported")
    return JudgeScore(
        n=len(items),
        accuracy=sum(correct) / len(correct),
        accuracy_ci=(low, high),
        catch_rate=sum(p == "unsupported" for _, p in bad) / len(bad),
        false_alarm_rate=sum(p == "unsupported" for _, p in good) / len(good),
        invalid_rate=sum(p is None for p in predictions) / len(predictions),
        catch_by_type={t: caught[t] / by_type[t] for t in ERROR_TYPES if by_type[t]},
    )
