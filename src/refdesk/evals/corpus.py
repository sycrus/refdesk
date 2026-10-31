"""Corpus snapshots: which records a golden set was built against (issue #151, ADR-023).

The store keeps growing as museums add works, but a golden set's expected references only
mean something against the corpus they were labelled on. A snapshot is a committed list of
that corpus's record IDs, one per `corpus_version`, in `evals/golden/corpus/`. The sorted
IDs hash to the `corpus_version` itself, so frozen golden files need no change.

`pin` filters the store to the snapshot before any retriever is built, so new works are
never ranked. It refuses when a pinned record is missing from the store or its rights
status has changed (a flip can turn a correct expected reference into one that must not be
shown), and reports other field changes as drift. What breaks without it: every re-ingest
that adds a work makes every frozen golden set unusable, and the only fix is deleting
records from the store by hand.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from refdesk.evals.golden import corpus_version
from refdesk.schema import ArtworkRecord

SNAPSHOT_DIR = Path("evals/golden/corpus")
HEADER = "# id\trights_status\tcontent_sha256 (descriptive fields; ADR-023)"


class CorpusMismatch(Exception):
    """The store cannot reproduce the golden set's corpus."""


@dataclass(frozen=True)
class SnapshotRow:
    rights_status: str
    digest: str


def record_digest(record: ArtworkRecord) -> str:
    """Hash of what the source says about the work. Rights are compared by status instead
    (a re-check only changes `checked_at`), and `raw_record_ref` is storage, not content."""
    fields = record.model_dump(mode="json", exclude={"rights", "raw_record_ref"})
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:16]


def snapshot_path(version: str, directory: Path = SNAPSHOT_DIR) -> Path:
    return Path(directory) / f"{version.replace(':', '-')}.tsv"  # no colons on Windows


def _text(records: Iterable[ArtworkRecord]) -> str:
    rows = sorted((r.id, r.rights.status.value, record_digest(r)) for r in records)
    return "\n".join([HEADER, *("\t".join(row) for row in rows)]) + "\n"


def write_snapshot(records: list[ArtworkRecord], directory: Path = SNAPSHOT_DIR) -> Path:
    """Write the snapshot for these records. Rewriting an identical one is a no-op; a
    different one under the same name is refused, because snapshots are frozen."""
    path = snapshot_path(corpus_version(records), directory)
    text = _text(records)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise FileExistsError(f"{path.name} exists with other content; snapshots are frozen")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def load_snapshot(path: Path) -> dict[str, SnapshotRow]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            record_id, status, digest = line.split("\t")
            rows[record_id] = SnapshotRow(status, digest)
    ids = sorted(rows)
    sources = "+".join(sorted({i.split(":", 1)[0] for i in ids}))
    digest = hashlib.sha256("\n".join(ids).encode()).hexdigest()[:12]
    if path.stem != f"{sources}-{len(ids)}-{digest}":
        raise CorpusMismatch(f"{path.name}: its IDs hash to {sources}:{len(ids)}:{digest}")
    return rows


def ensure_snapshot(
    version: str, records: list[ArtworkRecord], directory: Path = SNAPSHOT_DIR
) -> Path:
    """The snapshot for `version`, written from `records` if it does not exist yet. Used when
    a golden set is frozen. Once the store has grown, a missing snapshot is lost for good."""
    path = snapshot_path(version, directory)
    if path.exists():
        load_snapshot(path)  # checks the IDs still hash to the name
        return path
    if corpus_version(records) != version:
        raise CorpusMismatch(
            f"no snapshot for {version}, and it cannot be rebuilt: the store is now "
            f"{corpus_version(records)}"
        )
    return write_snapshot(records, directory)


@dataclass
class PinnedCorpus:
    version: str
    records: list[ArtworkRecord]
    extra: int  # store records outside the snapshot, ignored
    content_changed: list[str] = field(default_factory=list)

    @property
    def drift(self) -> str:
        """'' when nothing changed; otherwise a hash of the changed records' content, so
        a run on drifted records gets its own config hash and report."""
        if not self.content_changed:
            return ""
        changed = {r.id: record_digest(r) for r in self.records if r.id in self.content_changed}
        return hashlib.sha256(json.dumps(changed, sort_keys=True).encode()).hexdigest()[:12]

    def notes(self) -> list[str]:
        notes = [f"Pinned to `{self.version}`; {self.extra} newer store records ignored."]
        changed = self.content_changed
        if changed:
            more = f" and {len(changed) - 20} more" if len(changed) > 20 else ""
            notes.append(
                f"**Warning:** {len(changed)} pinned records changed since the snapshot "
                f"(rights unchanged): {', '.join(changed[:20])}{more}."
            )
        return notes


def pin(records: list[ArtworkRecord], version: str, directory: Path = SNAPSHOT_DIR) -> PinnedCorpus:
    path = snapshot_path(version, directory)
    if not path.exists():
        raise CorpusMismatch(f"no snapshot for {version} ({path.as_posix()})")
    snapshot = load_snapshot(path)
    by_id = {r.id: r for r in records}
    missing = sorted(set(snapshot) - set(by_id))
    if missing:
        raise CorpusMismatch(f"{len(missing)} pinned records not in the store: {missing[:20]}")
    pinned = sorted((by_id[i] for i in snapshot), key=lambda r: r.id)
    flipped = [r.id for r in pinned if r.rights.status.value != snapshot[r.id].rights_status]
    if flipped:
        raise CorpusMismatch(f"rights status changed on pinned records: {flipped[:20]}")
    changed = [r.id for r in pinned if record_digest(r) != snapshot[r.id].digest]
    return PinnedCorpus(version, pinned, len(records) - len(pinned), changed)
