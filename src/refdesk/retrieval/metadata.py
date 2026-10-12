"""Metadata-only baseline (FR-4, ADR-012): Jaccard similarity over attribute sets.

Each record becomes a set of attributes named after the field they come from:
`tag:landscape`, `medium:oil`, `artist:vincent van gogh`, `century:19`,
`classification:painting`. A query becomes a set in the same terms: brief words are
looked up in the corpus vocabulary, conditions map to named attributes, and an anchor
contributes its own attributes. The score is |query ∩ record| / |query ∪ record|.

Why it exists: it is the simple baseline every cleverer retriever must beat (PRD 1A.4),
and every result is explained by the exact attributes it shares with the query.

Deliberately simple: no title words (subjects come from tags), no synonyms, and negation
in the brief ("not red") is ignored. Ties are broken by record ID so rankings are stable.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from refdesk.retrieval import Hit, Query, allowed
from refdesk.schema import ArtworkRecord

STOPWORDS = frozenset(
    "a an and the with of on in for to but not or at by from ca into its it is are as".split()
)
_WORD = re.compile(r"[a-z0-9]+")
_YEAR = re.compile(r"\b(\d{3,4})")
# Query conditions (PRD 8: period, material, motif, department) -> attribute namespace.
_CONDITION_FIELD = {"material": "medium", "motif": "tag", "department": "classification"}


def normalise(word: str) -> str:
    """Lowercase and reduce simple English plurals, the same way on both sides."""
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("sses", "ches", "shes", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "as", "os")):
        return w[:-1]
    return w


def _words(text: str) -> list[str]:
    return [normalise(w) for w in _WORD.findall(text.lower()) if w not in STOPWORDS]


def _phrase(text: str) -> str:
    return " ".join(_words(text))


def _century(date: str | None) -> str | None:
    match = _YEAR.search(date or "")
    return str(int(match.group(1)) // 100 + 1) if match else None


# Centuries are written many ways: "17th century", "17th-century", "17th c.", "17th cent.",
# and BCE as "5th century BC", "5th-century B.C.E.". BCE years: "500 BCE", "500 B.C.".
_BCE = r"(?:b\.?\s?c\.?(?:\s?e\.?)?)(?![a-z])"
_ORDINAL_CENTURY = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)[\s-]*(?:century|cent\.?|c\.?)(?![a-z])\s*({_BCE})?",
    re.IGNORECASE,
)
_BCE_YEAR = re.compile(rf"\b(\d{{1,4}})\s*{_BCE}", re.IGNORECASE)

ACCEPTED_PERIODS = (
    'a century ("17th century", "17th-century", "17th c.", "5th century BCE") '
    'or a year ("1650", "c. 1650", "500 BCE")'
)


def _bce_century(year: int) -> str:
    """Year 500 BCE -> "5bce": 500 to 401 BCE is the 5th century BCE. The suffix keeps a
    BCE century from ever matching the CE century with the same number."""
    return f"{(year - 1) // 100 + 1}bce"


def _period_century(period: str) -> str | None:
    """A period condition or display date: a written century, a BCE year, or a CE year.
    Named periods ("Baroque") give None until there is a cited mapping (issue #64)."""
    if match := _ORDINAL_CENTURY.search(period):
        return f"{match.group(1)}bce" if match.group(2) else match.group(1)
    if match := _BCE_YEAR.search(period):
        return _bce_century(int(match.group(1)))
    return _century(period)


def _record_century(record: ArtworkRecord) -> str | None:
    """The structured start year if the source gives one (negative = BCE), else the
    display date. There is no year 0, so a start year of 0 gives no century."""
    if record.date_begin is not None:
        if record.date_begin > 0:
            return str(record.date_begin // 100 + 1)
        return _bce_century(-record.date_begin) if record.date_begin < 0 else None
    return _period_century(record.date or "")


def attributes(record: ArtworkRecord) -> frozenset[str]:
    attrs: set[str] = set()
    attrs.update(f"tag:{_phrase(t)}" for t in record.subject_tags if _phrase(t))
    attrs.update(f"medium:{w}" for w in _words(record.medium or ""))
    if record.artist and _phrase(record.artist):
        attrs.add(f"artist:{record.artist.strip().lower()}")
    if record.classification:
        attrs.add(f"classification:{_phrase(record.classification)}")
    if century := _record_century(record):
        attrs.add(f"century:{century}")
    return frozenset(attrs)


def condition_attributes(key: str, value: str) -> set[str]:
    """The attributes one query condition stands for. A condition names its field, so it
    maps straight to that attribute namespace. Unknown keys and unparseable periods give
    an empty set."""
    if key == "period":
        century = _period_century(value)
        return {f"century:{century}"} if century else set()
    namespace = _CONDITION_FIELD.get(key)
    if namespace == "medium":
        return {f"medium:{w}" for w in _words(value)}
    if namespace:
        return {f"{namespace}:{_phrase(value)}"}
    return set()


class JaccardRetriever:
    def __init__(self, records: Iterable[ArtworkRecord]):
        records = list(records)
        self.records: dict[str, ArtworkRecord] = {r.id: r for r in records}
        self.attrs: dict[str, frozenset[str]] = {r.id: attributes(r) for r in records}
        # word -> attributes whose value contains it ("gogh" -> "artist:vincent van gogh")
        self.vocab: dict[str, set[str]] = defaultdict(set)
        for attr_set in self.attrs.values():
            for attr in attr_set:
                for word in _words(attr.split(":", 1)[1]):
                    self.vocab[word].add(attr)

    def _lookup(self, text: str) -> set[str]:
        found: set[str] = set()
        for word in _words(text):
            found |= self.vocab.get(word, set())
        return found

    def query_attributes(self, query: Query) -> set[str]:
        attrs = self._lookup(query.brief)
        for key, value in query.conditions.items():
            attrs |= condition_attributes(key, value)
        if query.anchor_id is not None:
            attrs |= self.attrs[query.anchor_id]  # KeyError for an unknown anchor
        return attrs

    def excluded(self, query: Query) -> set[str]:
        """Record IDs the avoid list rules out: named IDs, plus records that share an
        attribute with an avoid term ("avoid Monet")."""
        excluded = {a for a in query.avoid if ":" in a}
        terms = set().union(*(self._lookup(a) for a in query.avoid if ":" not in a))
        if terms:
            excluded |= {rid for rid, attrs in self.attrs.items() if attrs & terms}
        return excluded

    def search(self, query: Query) -> list[Hit]:
        q = self.query_attributes(query)
        if not q:
            return []
        avoid_ids = {a for a in query.avoid if ":" in a}
        avoid_attrs = set().union(*(self._lookup(a) for a in query.avoid if ":" not in a))
        hits = []
        for record_id, attrs in self.attrs.items():
            if not allowed(self.records[record_id], query):
                continue
            if record_id == query.anchor_id or record_id in avoid_ids or attrs & avoid_attrs:
                continue
            shared = q & attrs
            if shared:
                union = len(q | attrs)
                hits.append(Hit(record_id, len(shared) / union, tuple(sorted(shared)), union))
        hits.sort(key=lambda h: (-h.score, h.record_id))
        return hits[: query.k]
