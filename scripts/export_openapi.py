"""Write the API contract to docs/api/openapi.json from the FastAPI app.

The spec is generated from code so it cannot drift from it; a test fails if the
committed file is stale. Usage: uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from refdesk.api.app import app

OUT = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": the committed file has LF endings; without this, Windows writes CRLF
    # and every regeneration shows a whole-file diff.
    OUT.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"wrote {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT}")
