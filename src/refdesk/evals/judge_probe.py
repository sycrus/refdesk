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

The hard set (`build_hard_items`, issue #122) is closer to real rationales: five claims
in a random order, faithful items paraphrased rather than copied (to tempt false alarms),
and subtle errors (a date just outside the record's range, an attribution prefix such as
"Workshop of" dropped, a subject made more specific than the record, canvas and wood
swapped). What breaks without it: the v1 set's blatant errors cannot separate the best
judges, so a judge choice would rest on one item. Met records have no long description
text, so checks across paragraph fields are still untested.
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
HARD_ERROR_TYPES = ("near_date", "dropped_prefix", "overspecific_subject", "near_medium")
# How each attribution prefix reads in a sentence; dropping it overstates the attribution.
PREFIX_PHRASES = {
    "Workshop of": "a work from the workshop of",
    "Attributed to": "a work attributed to",
    "Style of": "a work in the style of",
    "Follower of": "a work by a follower of",
    "Circle of": "a work from the circle of",
    "Copy after": "a copy after",
    "Studio of": "a work from the studio of",
    "Manner of": "a work in the manner of",
}
# A record tag and a more specific claim the record does not support.
OVERSPECIFIC = {
    "Men": "an admiral", "Women": "a duchess", "Landscapes": "the Swiss Alps",
    "Dogs": "a spaniel", "Horses": "an Arabian stallion", "Boats": "a Dutch frigate",
    "Flowers": "tulips", "Rivers": "the Thames", "Cows": "Jersey cattle",
    "Mountains": "Mont Blanc", "Forests": "the Black Forest", "Interiors": "a palace ballroom",
}  # fmt: skip
NEAR_MEDIA = {
    "Oil on canvas": "an oil painting on wood",
    "Oil on wood": "an oil painting on canvas",
}
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
    claims: tuple[str, ...] = ()  # the factual claims only, one sentence each


def _claims(title, artist, date, medium, subject, extra=""):
    claims = [
        f"{title} is by {artist} and dated {date}.",
        f"{title} is {medium.lower()}.",
        f"The subject of {title} includes {subject}.",
    ]
    if extra:
        claims.append(f"{title}{extra.removeprefix(';').replace(' it ', ' ', 1)}.")
    return tuple(claims)


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
        fact_parts = {k: v for k, v in parts.items() if k != "opinion"}
        items.append(
            JudgeItem(
                f"j{n:03d}a",
                r.id,
                doc,
                _sentence(**parts),
                "supported",
                claims=_claims(**fact_parts),
            )
        )

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
        bad_facts = {k: v for k, v in bad.items() if k != "opinion"}
        items.append(
            JudgeItem(
                f"j{n:03d}b",
                r.id,
                doc,
                _sentence(**bad, extra=extra),
                "unsupported",
                error,
                claims=_claims(**bad_facts, extra=extra),
            )
        )
    return items


def hard_document(r: ArtworkRecord) -> str:
    return "\n".join([
        f"Title: {r.title}", f"Artist: {r.artist}", f"Date: {r.date or 'not given'}",
        f"Years: {r.date_begin} to {r.date_end}", f"Medium: {r.medium}",
        f"Classification: {r.classification}", f"Subjects: {', '.join(r.subject_tags)}",
    ])  # fmt: skip


def _prefix(artist: str) -> str | None:
    return next((p for p in PREFIX_PHRASES if artist.startswith(p + " ")), None)


def _subject_tag(r: ArtworkRecord) -> str | None:
    """A tag with an over-specific stand-in that the title does not already support."""
    return next(
        (t for t in r.subject_tags
         if t in OVERSPECIFIC and OVERSPECIFIC[t].split()[-1].lower() not in r.title.lower()),
        None,
    )  # fmt: skip


def _hard_claims(r: ArtworkRecord, tag: str) -> dict[str, str]:
    prefix = _prefix(r.artist)
    phrase = PREFIX_PHRASES[prefix] if prefix else "a work by"
    master = r.artist[len(prefix) + 1 :] if prefix else r.artist
    if r.date_begin == r.date_end:
        when = f"in {r.date_begin}"
    else:
        when = f"between {r.date_begin} and {r.date_end}"
    if r.medium.startswith("Oil on "):
        medium = f"an oil painting on {r.medium[len('Oil on ') :].lower()}"
    else:
        medium = f"executed in {r.medium.lower()}"
    return {
        "artist": f"{r.title} is {phrase} {master}.",
        "date": f"It was painted {when}.",
        "medium": f"It is {medium}.",
        "subject": f"Its subjects include {tag.lower()}.",
        "classification": f"The museum classifies it under {r.classification.lower()}.",
    }


def _hard_eligible(r: ArtworkRecord, error: str) -> bool:
    base = (
        r.title and r.artist and r.medium and r.classification and r.subject_tags
        and r.date_begin is not None and r.date_end is not None
    )  # fmt: skip
    if not base:
        return False
    if error == "dropped_prefix":
        return _prefix(r.artist) is not None
    if error == "overspecific_subject":
        return _subject_tag(r) is not None
    if error == "near_medium":
        return r.medium in NEAR_MEDIA
    return True


def build_hard_items(records: list[ArtworkRecord], *, n_per_type: int = 10, seed: int = 0):
    """Pairs of five-claim rationales: one faithful (paraphrased), one with one subtle error."""
    rng = random.Random(seed)
    pool = sorted(records, key=lambda r: r.id)
    used: set[str] = set()
    items = []
    n = 0
    for error in HARD_ERROR_TYPES:
        eligible = [r for r in pool if r.id not in used and _hard_eligible(r, error)]
        if len(eligible) < n_per_type:
            raise ValueError(
                f"not enough eligible records for {error}: need {n_per_type}, have {len(eligible)}"
            )
        for r in rng.sample(eligible, n_per_type):
            used.add(r.id)
            tag = _subject_tag(r) or r.subject_tags[0]
            good = _hard_claims(r, tag)
            bad = dict(good)
            if error == "near_date":
                gap = rng.randint(12, 30)
                year = r.date_end + gap if rng.random() < 0.5 else r.date_begin - gap
                bad["date"] = f"It was painted in {year}."
            elif error == "dropped_prefix":
                bad["artist"] = f"{r.title} is a work by {r.artist[len(_prefix(r.artist)) + 1 :]}."
            elif error == "overspecific_subject":
                bad["subject"] = f"Its subjects include {OVERSPECIFIC[tag]}."
            elif error == "near_medium":
                bad["medium"] = f"It is {NEAR_MEDIA[r.medium]}."
            order = list(good)
            rng.shuffle(order)
            opinion = f"Overall it {OPINIONS[n % len(OPINIONS)]}."
            doc = hard_document(r)
            for suffix, claims, label, err in (
                ("a", good, "supported", None),
                ("b", bad, "unsupported", error),
            ):
                ordered = tuple(claims[k] for k in order)
                items.append(
                    JudgeItem(
                        f"h{n:03d}{suffix}",
                        r.id,
                        doc,
                        " ".join(ordered) + " " + opinion,
                        label,
                        err,
                        claims=ordered,
                    )
                )
            n += 1
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
        catch_by_type={
            t: caught[t] / by_type[t] for t in ERROR_TYPES + HARD_ERROR_TYPES if by_type[t]
        },
    )
