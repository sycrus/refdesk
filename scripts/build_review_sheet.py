"""The review sheet for golden-v1's non-blind cases (ADR-018 step 5, issue #15).

One row per pool candidate of the 21 non-blind retrieve cases, with Claude's proposal
(grade and reason, blank if Claude did not propose it) and phi4's verdict. Joe labels each
row in the labelling page (`uv run python -m refdesk.evals.label_app --review`): relevant
y/n and a grade, whatever Claude said. His decision on each proposal (accepted, rejected,
regraded) and any work he adds are derived from that later, so the page never asks him to
"agree". Blind cases are left out: Joe never sees proposals for them.

Reads runs/labelling-v1/proposals-judged.jsonl (scripts/judge_proposals.py) and
evals/labelling/v1/review-pools.json. Never rebuilds a sheet that holds labels.

Usage (PowerShell or WSL2): uv run python scripts/build_review_sheet.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_labelling_pools import DRAFTS, OUT, ROOT, has_labels  # noqa: E402

from refdesk.store import Store  # noqa: E402

SHEET = OUT / "review-sheet.csv"
JUDGED = ROOT / "runs" / "labelling-v1" / "proposals-judged.jsonl"
FIELDS = [
    "draft_id", "brief", "usage_mode", "candidate", "title", "artist", "date", "medium",
    "subjects", "record_url", "image_url", "claude_grade", "claude_reason", "judge_verdict",
    "relevant", "grade", "note",
]  # fmt: skip


def main() -> None:
    if has_labels(SHEET):
        raise SystemExit("review-sheet.csv holds labels; rebuilding would erase them")
    drafts = {d["draft_id"]: d for d in map(json.loads, DRAFTS.read_text("utf-8").splitlines())}
    pools = json.loads((OUT / "review-pools.json").read_text(encoding="utf-8"))["cases"]
    judged = {c["draft_id"]: c for c in map(json.loads, JUDGED.read_text("utf-8").splitlines())}
    rows = []
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        for draft_id, pool in pools.items():
            case = judged[draft_id]
            if case["blind"] or case["pool"] != pool:
                raise SystemExit(f"{draft_id}: proposals were not made on this review pool")
            proposed = {p["record_id"]: p for p in case["proposals"]}
            for record_id in pool:
                r, p = store.get_record(record_id), proposed.get(record_id, {})
                rows.append({
                    "draft_id": draft_id, "brief": drafts[draft_id]["brief"],
                    "usage_mode": drafts[draft_id]["usage_mode"], "candidate": record_id,
                    "title": r.title or "", "artist": r.artist or "",
                    "date": r.date or f"{r.date_begin}-{r.date_end}", "medium": r.medium or "",
                    "subjects": ", ".join(r.subject_tags), "record_url": r.record_url or "",
                    "image_url": r.image_url or "", "claude_grade": str(p.get("grade", "")),
                    "claude_reason": p.get("reason", ""),
                    "judge_verdict": p.get("judge_verdict", ""),
                    "relevant": "", "grade": "", "note": "",
                })  # fmt: skip
    with SHEET.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    proposed = sum(bool(r["claude_grade"]) for r in rows)
    print(f"{len(pools)} cases, {len(rows)} rows, {proposed} proposed")


if __name__ == "__main__":
    main()
