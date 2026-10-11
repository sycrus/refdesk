"""SQLite metadata store (PRD 10: "Metadata store: SQLite").

Three tables:
- `records`: one normalised ArtworkRecord per `source:object_id`, upserted, so re-ingesting
  updates a row instead of adding a duplicate.
- `raw_records`: the untouched source response, keyed by the record's `raw_record_ref`
  (FR-1), so any stored field can be traced back to what the museum returned.
- `ingest_progress`: one row per object ID the ingest has handled, including skips. This is
  what makes the ingest resumable.

`save()` writes the record, the raw response and the progress row in one transaction. If
the process dies mid-ingest, at most the object in flight is lost, and it is fetched again
on the next run. Without the shared transaction, a crash could leave a record marked done
with no raw response, or the reverse.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from refdesk.schema import ArtworkRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    object_id     TEXT NOT NULL,
    rights_status TEXT NOT NULL,
    data          TEXT NOT NULL,   -- ArtworkRecord as JSON
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_records (
    ref        TEXT PRIMARY KEY,   -- ArtworkRecord.raw_record_ref
    body       TEXT NOT NULL,      -- the source response, verbatim JSON
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_progress (
    source     TEXT NOT NULL,
    object_id  TEXT NOT NULL,
    outcome    TEXT NOT NULL,      -- "done" or "skipped:<reason>"
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source, object_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    # Writes. Each one is a single transaction (`with self.db` commits or rolls back).

    def save(self, record: ArtworkRecord, raw: dict[str, Any]) -> None:
        now = _now()
        with self.db:
            self.db.execute(
                "INSERT INTO records (id, source, object_id, rights_status, data, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "rights_status = excluded.rights_status, data = excluded.data, "
                "updated_at = excluded.updated_at",
                (
                    record.id,
                    record.source,
                    record.object_id,
                    record.rights.status.value,
                    record.model_dump_json(),
                    now,
                ),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO raw_records (ref, body, fetched_at) VALUES (?, ?, ?)",
                (record.raw_record_ref, json.dumps(raw, ensure_ascii=False), now),
            )
            self._mark(record.source, record.object_id, "done", now)

    def mark_skipped(self, source: str, object_id: str, reason: str) -> None:
        with self.db:
            self._mark(source, object_id, f"skipped:{reason}", _now())

    def _mark(self, source: str, object_id: str, outcome: str, now: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO ingest_progress (source, object_id, outcome, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (source, object_id, outcome, now),
        )

    # Reads.

    def handled_object_ids(self, source: str) -> set[str]:
        rows = self.db.execute("SELECT object_id FROM ingest_progress WHERE source = ?", (source,))
        return {row[0] for row in rows}

    def get_record(self, record_id: str) -> ArtworkRecord | None:
        row = self.db.execute("SELECT data FROM records WHERE id = ?", (record_id,)).fetchone()
        return ArtworkRecord.model_validate_json(row[0]) if row else None

    def get_raw(self, ref: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT body FROM raw_records WHERE ref = ?", (ref,)).fetchone()
        return json.loads(row[0]) if row else None

    def count_records(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    def count_by_rights_status(self) -> dict[str, int]:
        rows = self.db.execute("SELECT rights_status, COUNT(*) FROM records GROUP BY 1")
        return dict(rows.fetchall())

    def progress_counts(self, source: str) -> dict[str, int]:
        rows = self.db.execute(
            "SELECT outcome FROM ingest_progress WHERE source = ?", (source,)
        ).fetchall()
        return dict(Counter(row[0] for row in rows))
