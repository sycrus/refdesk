"""golden-v1 trust report, and the freeze once it passes (ADR-018, issue #15).

Reads the labelling files (see `refdesk.evals.golden_v1`) and writes
evals/reports/golden-v1-trust-<date>-<inputs hash>.md, never overwriting one. Runs at
any stage: missing pass 2 or an unfinished review shows as pending.

`--freeze` also writes evals/golden/golden-v1.jsonl, only when every case is built, pass 2
is done, the review is done and both trust rules pass. Freezing is Joe's call: he runs it,
or approves the run (golden-set edits are on the ask list).

Usage (PowerShell or WSL2):
    uv run python scripts/golden_v1_report.py [--caveat "Pass 2 on the same day"] [--freeze]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from refdesk.evals.golden_v1 import assemble, report

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "evals" / "labelling" / "v1"
JUDGED = ROOT / "runs" / "labelling-v1" / "proposals-judged.jsonl"
GOLDEN = ROOT / "evals" / "golden" / "golden-v1.jsonl"
STANDING_CAVEATS = [
    "Pools come from the system's own retrievers plus 2 random records per case, so recall "
    "is recall within the pools.",
    "phi4's relevance judgement is unmeasured (the judge probe screened false facts); its "
    "verdicts flagged proposals for Joe and decided nothing.",
    "Claude proposed from the brief, the record and the cached image; phi4 saw text only.",
]


def _rows(path: Path) -> list[dict[str, str]] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="golden-v1 trust report")
    parser.add_argument("--caveat", action="append", default=[], help="add a caveat line")
    parser.add_argument("--freeze", action="store_true", help="write golden-v1.jsonl if it passes")
    args = parser.parse_args()

    inputs = [V1 / "briefs-draft.jsonl", V1 / "blind-cases.json", V1 / "blind-sheet.csv",
              V1 / "blind-sheet-pass2.csv", V1 / "review-sheet.csv", JUDGED]  # fmt: skip
    digest = hashlib.sha256()
    for path in inputs:
        digest.update(path.name.encode() + (path.read_bytes() if path.exists() else b"-"))
    blind = json.loads((V1 / "blind-cases.json").read_text(encoding="utf-8"))
    assembly = assemble(
        drafts=[json.loads(x) for x in (V1 / "briefs-draft.jsonl").read_text("utf-8").splitlines()],
        blind_ids=set(blind["blind"]),
        corpus_version=blind["corpus_version"],
        pass1=_rows(V1 / "blind-sheet.csv") or [],
        pass2=_rows(V1 / "blind-sheet-pass2.csv"),
        proposals={
            c["draft_id"]: c for c in map(json.loads, JUDGED.read_text("utf-8").splitlines())
        },
        review=_rows(V1 / "review-sheet.csv") or [],
        reviewed_at=datetime.now(UTC),
    )
    name = f"golden-v1-trust-{date.today().isoformat()}-{digest.hexdigest()[:12]}"
    text, result = report(assembly, title=name, caveats=STANDING_CAVEATS + args.caveat)
    out = ROOT / "evals" / "reports" / f"{name}.md"
    if out.exists():
        raise SystemExit(f"{out.name} exists; reports are never overwritten")
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {out.relative_to(ROOT).as_posix()}")

    if args.freeze:
        reviewed = any(c.review and not c.review.blind for c in assembly.cases)
        if assembly.problems or result is None or not reviewed or not result.passed:
            raise SystemExit("not frozen: every case must be built, pass 2 and the review done, "
                             "and both trust rules must pass")  # fmt: skip
        if GOLDEN.exists():
            raise SystemExit("golden-v1.jsonl exists; frozen sets are never edited")
        GOLDEN.write_text(
            "".join(c.model_dump_json(exclude_none=True) + "\n" for c in assembly.cases),
            encoding="utf-8",
        )
        print(f"froze {len(assembly.cases)} cases to {GOLDEN.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
