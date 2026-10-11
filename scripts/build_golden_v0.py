"""Build evals/golden/golden-v0-synthetic.jsonl and its validation report (issue #10, ADR-018).

Every case here was written by Claude Code. Expected references are NOT chosen by
judgement: each case has an explicit `rule`, applied to the ingested corpus by
`refdesk.evals.golden.apply_rule`. Anyone can re-derive a case by hand from the records.

Known bias, stated in the report: rules over metadata favour the metadata baseline, so
golden-v0 must never be used to compare retrievers or support any claim. It exists to
build and test the eval harness.

Usage (PowerShell or WSL2):
    uv run python scripts/build_golden_v0.py --dry-run   # print match counts only
    uv run python scripts/build_golden_v0.py             # write the set and the report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from refdesk.evals.golden import apply_rule, corpus_version, validate_cases
from refdesk.store import Store

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "golden" / "golden-v0-synthetic.jsonl"
REPORT = ROOT / "evals" / "reports" / "golden-v0-synthetic-validation.md"
MIN_REFS, MAX_REFS = 3, 60

# (brief, rule, difficulty, tags, extras). extras may set constraints, usage_mode,
# expected_decision and labels. Rule clauses: see refdesk.evals.golden._CLAUSES.
CASES = [
    # Straightforward subject briefs.
    (
        "Seventeenth-century flower still lifes for a spring tea tin",
        {"tags_all": ["Still Life", "Flowers"], "century": 17},
        "easy",
        ["still life", "period"],
        {},
    ),
    (
        "Dogs in portraits, for a pet-food brand's heritage campaign",
        {"tags_all": ["Dogs", "Portraits"]},
        "easy",
        ["animals", "portraits"],
        {},
    ),
    (
        "Horses in open landscapes for an equestrian event poster",
        {"tags_all": ["Horses", "Landscapes"]},
        "easy",
        ["animals", "landscape"],
        {},
    ),
    ("Cows in pasture for a heritage dairy brand", {"tags_all": ["Cows"]}, "easy", ["animals"], {}),
    ("Birds for a bird-seed packaging range", {"tags_all": ["Birds"]}, "easy", ["animals"], {}),
    (
        "Portrait miniatures of women from around 1800 for a jewellery-box lid",
        {"classification": ["Miniatures"], "tags_all": ["Women"], "year_range": [1780, 1820]},
        "easy",
        ["miniatures", "portraits", "period"],
        {},
    ),
    ("Cats, any period, for a cat-café menu", {"tags_all": ["Cats"]}, "easy", ["animals"], {}),
    # Subject plus period, medium or mood.
    (
        "Nineteenth-century mountain scenery for an outdoor gear catalogue",
        {"tags_all": ["Mountains"], "century": 19},
        "medium",
        ["landscape", "period"],
        {},
    ),
    (
        "Fruit and grape still lifes for a wine label",
        {"tags_all": ["Still Life"], "tags_any": ["Fruit", "Grapes"]},
        "medium",
        ["still life"],
        {},
    ),
    (
        "Classical ruins in landscape, Grand Tour mood, for a travel journal cover",
        {"tags_all": ["Ruins"]},
        "medium",
        ["landscape", "architecture"],
        {},
    ),
    (
        "Music-making and musical instruments for a concert-hall season brochure",
        {"tags_any": ["Musical Instruments", "Music"]},
        "medium",
        ["music"],
        {},
    ),
    (
        "People absorbed in reading, for a library membership campaign",
        {"tags_all": ["Reading"]},
        "medium",
        ["people"],
        {},
    ),
    (
        "Views of Venice for a travel poster series",
        {"tags_any": ["Venice"]},
        "medium",
        ["cities", "place"],
        {},
    ),
    (
        "Fifteenth-century Madonna and Child panels with gold for a museum-shop notebook",
        {"tags_all": ["Madonna and Child"], "century": 15, "medium_any": ["gold"]},
        "medium",
        ["religious", "period", "medium"],
        {},
    ),
    ("Gardens for a seed catalogue cover", {"tags_all": ["Gardens"]}, "medium", ["landscape"], {}),
    (
        "Seventeenth-century domestic interiors with women for a homeware brand",
        {"tags_all": ["Interiors", "Women"], "century": 17},
        "medium",
        ["interiors", "people", "period"],
        {},
    ),
    (
        "Ships at sea for a maritime museum's shop range",
        {"tags_any": ["Ships"]},
        "medium",
        ["boats"],
        {},
    ),
    (
        "Boats at night for a whisky label",
        {"tags_all": ["Boats"], "tags_any": ["Night", "Evening"]},
        "medium",
        ["boats", "mood"],
        {},
    ),
    (
        "Rivers in eighteenth-century landscapes for a riverside hotel",
        {"tags_all": ["Rivers"], "century": 18},
        "medium",
        ["landscape", "period"],
        {},
    ),
    (
        "Girls in nineteenth-century paintings for a children's clothing brand",
        {"tags_all": ["Girls"], "century": 19},
        "medium",
        ["people", "period"],
        {},
    ),
    # Conditions, anchors and avoid lists.
    (
        "More like this: Van Gogh's Wheat Field with Cypresses",
        {"artist_contains": "van gogh", "exclude_ids": ["met:436535"]},
        "hard",
        ["anchor"],
        {"constraints": {"anchor_id": "met:436535"}},
    ),
    (
        "Flower paintings, but not Van Gogh: too familiar for this client",
        {"tags_all": ["Flowers"], "artist_excludes": "van gogh"},
        "hard",
        ["avoid list"],
        {"constraints": {"avoid": ["Vincent van Gogh"]}},
    ),
    (
        "Oil sketches and pastels on paper, any subject, for a sketchbook range",
        {"classification": ["Pastels & Oil Sketches on Paper"]},
        "medium",
        ["medium"],
        {"constraints": {"conditions": {"department": "Pastels & Oil Sketches on Paper"}}},
    ),
    (
        "Saints in sixteenth-century paintings",
        {"tags_all": ["Saints"], "century": 16},
        "medium",
        ["religious", "period"],
        {"constraints": {"conditions": {"period": "16th century"}}},
    ),
    # Reproduction mode: only open works may be expected.
    (
        "Sheep and shepherds for a wool brand's packaging, to be reproduced",
        {"tags_any": ["Sheep", "Shepherds"], "rights": "open"},
        "medium",
        ["animals", "reproduction"],
        {"usage_mode": "reproduction"},
    ),
    (
        "Twentieth-century paintings to reproduce on packaging",
        {"century": 20, "rights": "open"},
        "hard",
        ["reproduction", "rights"],
        {
            "usage_mode": "reproduction",
            "labels": {"note": "Most 20th-century works in the slice are permission required"},
        },
    ),
    # Culturally sensitive subjects: retrieve, but they need a review flag (PRD 10.1, Q3).
    (
        "Crucifixion imagery for a fashion print",
        {"tags_all": ["Crucifixion"]},
        "hard",
        ["religious", "culturally sensitive"],
        {"labels": {"sensitivity": "religious imagery in a commercial use"}},
    ),
    (
        "Orientalist scenes for a restaurant interior",
        {"tags_any": ["Orientalist"]},
        "hard",
        ["culturally sensitive"],
        {"labels": {"sensitivity": "Orientalist depictions"}},
    ),
    # Requests that must be declined (PRD 6 non-goals, PRD 10.1 Q5).
    (
        "Make a new painting in the style of David Hockney for our label",
        None,
        "hard",
        ["decline", "living artist"],
        {"expected_decision": "decline"},
    ),
    (
        "Is the Rembrandt I bought at auction genuine?",
        None,
        "hard",
        ["decline", "authentication"],
        {"expected_decision": "decline"},
    ),
    (
        "Generate an image of our product painted like a Monet",
        None,
        "hard",
        ["decline", "image generation"],
        {"expected_decision": "decline"},
    ),
]


def build(records, version):
    cases, problems = [], []
    for n, (brief, rule, difficulty, tags, extras) in enumerate(CASES, start=1):
        case_id = f"g0-{n:03d}"
        decision = extras.get("expected_decision", "retrieve")
        refs = apply_rule(rule, records) if rule else []
        if decision == "retrieve" and not MIN_REFS <= len(refs) <= MAX_REFS:
            problems.append(f"{case_id}: {len(refs)} references (want {MIN_REFS}-{MAX_REFS})")
        cases.append(
            {
                "id": case_id,
                "brief": brief,
                "constraints": extras.get("constraints", {}),
                "usage_mode": extras.get("usage_mode", "reference_only"),
                "expected_decision": decision,
                "expected": [{"record_id": r, "grade": 2} for r in refs],
                "labels": extras.get("labels", {}),
                "source": "synthetic:claude-code",
                "labeller": "claude-code",
                "difficulty": difficulty,
                "tags": tags,
                "version": "v0-synthetic",
                "provenance": "synthetic",
                "corpus_version": version,
                "rule": rule,
            }
        )
    return cases, problems


def prompt_texts():
    texts = {}
    for folder in ("prompts", "evals/fewshot"):
        for path in sorted((ROOT / folder).rglob("*")) if (ROOT / folder).exists() else []:
            if path.is_file():
                texts[str(path.relative_to(ROOT))] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
    return texts


def write_report(report, cases, version, problems, prompts):
    sizes = [len(c["expected"]) for c in cases if c["expected_decision"] == "retrieve"]
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    median = sorted(sizes)[len(sizes) // 2]
    errors, size_problems = len(report.errors), len(problems)
    leakage = len(prompts) or "none exist yet"
    lines = [
        "# golden-v0-synthetic: validation report",
        "",
        f"- Generated: {generated} by `scripts/build_golden_v0.py`",
        f"- Corpus version: `{version}`",
        f"- Cases: {len(cases)}. Errors: **{errors}**. Rule-size problems: **{size_problems}**.",
        f"- Distinct records referenced: {report.referenced_records}",
        f"- Expected references per retrieve case: min {min(sizes)}, median {median}, "
        f"max {max(sizes)}",
        f"- Prompt files checked for leakage: {leakage}",
        "",
        "> **Synthetic. Never use for claims (ADR-018).** Every case was written by",
        "> Claude Code, and its expected references come from an explicit rule over",
        "> metadata, not from judgement. Rules over metadata favour the metadata",
        "> baseline, so this set must not be used to compare retrievers. It exists to",
        "> build and test the eval harness.",
        "",
        "## Errors",
        "",
        *([f"- {e}" for e in report.errors + problems] or ["None."]),
        "",
    ]
    for key in ("difficulty", "expected_decision", "usage_mode", "tags"):
        lines += [f"## By {key}", "", "| Value | Cases |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(report.counts[key].items())]
        lines.append("")
    lines += ["## Cases", "", "| ID | Difficulty | Expected | Rule |", "|---|---|---|---|"]
    for c in cases:
        expected = (
            c["expected_decision"] if c["expected_decision"] == "decline" else len(c["expected"])
        )
        lines.append(f"| {c['id']} | {c['difficulty']} | {expected} | `{json.dumps(c['rule'])}` |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/refdesk.sqlite")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with Store(args.db) as store:
        records = list(store.iter_records("met"))
    version = corpus_version(records)
    cases, problems = build(records, version)

    if args.dry_run:
        for c in cases:
            print(f"{c['id']} {len(c['expected']):>3}  {c['brief'][:70]}")
        print(*problems, sep="\n")
        return 1 if problems else 0

    if OUT.exists():
        print(f"{OUT} exists and is frozen. Create a new version instead.")
        return 2
    lines = [json.dumps(c, ensure_ascii=False) for c in cases]
    prompts = prompt_texts()
    report = validate_cases(lines, {r.id for r in records}, version, prompt_texts=prompts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_report(report, cases, version, problems, prompts)
    print(
        f"wrote {len(cases)} cases; errors {len(report.errors)}; rule-size problems {len(problems)}"
    )
    print(Counter(c["difficulty"] for c in cases))
    return 1 if report.errors or problems else 0


if __name__ == "__main__":
    sys.exit(main())
