"""Build the small store the browser tests run against (issue #46).

Offline: the records come from the recorded Met fixtures in tests/fixtures/met (one open
painting, two that need permission), mapped by the real adapter. The store is rebuilt from
scratch each time, so a test run never sees boards from an earlier one.

Usage: uv run python scripts/make_e2e_store.py runs/e2e/store.sqlite
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from refdesk.sources.met import to_record
from refdesk.store import Store

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "met"


def build(path: Path) -> None:
    # Each record's rights check time is when its fixture was recorded (MANIFEST.json).
    manifest = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    path.unlink(missing_ok=True)
    store = Store(path)
    try:
        for fixture in sorted(FIXTURES.glob("object_*.json")):
            raw = json.loads(fixture.read_text(encoding="utf-8"))["body"]
            checked = datetime.fromisoformat(manifest[fixture.stem]["recorded_at"])
            store.save(to_record(raw, checked_at=checked), raw)
    finally:
        store.close()


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/e2e/store.sqlite")
    build(target)
    print(f"wrote {target}")
