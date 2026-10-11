"""Record real Met Collection API responses as test fixtures (tests/fixtures/met/).

Why: adapter tests must run offline and deterministically (CLAUDE.md: recorded responses,
not live calls), but the fixtures must be real responses, not hand-written guesses, or the
drift tests would only check our own assumptions. Re-run this to refresh them; the diff
shows any change in what the Met returns.

Polite: one request per second (the documented cap is 80/s). No API key is needed.

Usage: uv run python scripts/record_met_fixtures.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE = "https://collectionapi.metmuseum.org/public/collection"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "met"
USER_AGENT = "refdesk/0.1 (research project; github.com/sycrus/refdesk)"

# name -> path. Chosen to cover: an open painting, an in-copyright painting with a
# copyright notice, an in-copyright painting with an empty notice, the department list,
# the v1.1 search, and the retired v1 search.
FIXTURES = {
    "object_436535_open_painting": "/v1/objects/436535",
    "object_490190_copyright_notice": "/v1/objects/490190",
    "object_492759_copyright_no_notice": "/v1/objects/492759",
    "departments": "/v1/departments",
    "search_v1_1_european_paintings": (
        "/v1.1/search?departmentId=11&hasImages=true&q=painting&limit=5"
    ),
    "search_v1_retired": "/v1/search?q=sunflowers",
}


def fetch(path: str) -> tuple[int, object]:
    request = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return error.code, body


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, path in FIXTURES.items():
        status, body = fetch(path)
        (OUT / f"{name}.json").write_text(
            json.dumps({"status": status, "body": body}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest[name] = {
            "url": BASE + path,
            "status": status,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        print(f"{status} {name}")
        time.sleep(1)
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
