"""Probe: can phi4 check a fit sentence (opinion) for smuggled facts? (issue #97)

The smoke test showed judge-v1 flagging a pure-opinion fit sentence as UNSUPPORTED. The
judge probe (#122) never sent an opinion sentence on its own (per-claim mode leaves it
out), so this case was unmeasured. Items, labels known by construction, on real records:
- faithful: an opinion about mood or use, sometimes naming one of the record's own subject
  tags ("Its flowers suit a spring tin");
- corrupted: the same opinion plus one fact the record does not give (a patron, an
  exhibition, a place, a date).
Each prompt is run per sentence, temperature 0. Writes evals/reports/fit-probe-<date>.md.

The realistic set (issue #135) is shaped like what generators wrote in the first local
eval: fit sentences that repeat the record's own facts and the brief's words, on a brief
and a record that belong together (golden-v0 cases and their expected records), with and
without one smuggled fact. A first version paired records with random briefs ("female
nudes suit a poster for an equestrian event"); phi4 flagged half of those faithful items,
judging the pairing rather than the facts, so it was not what generators produce. Prompts
measured without the brief (`judge.WITHOUT_BRIEF`) still get none, so their numbers stay
comparable.

Usage (PowerShell or WSL2, Ollama running): uv run python scripts/probe_fit.py
"""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

from refdesk.evals.judge_probe import parse_verdict
from refdesk.judge import WITHOUT_BRIEF, judge_messages
from refdesk.llm.client import LLMClient
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.llm.model_manager import ModelManager, OllamaBackend, load_specs
from refdesk.rationale import PROMPTS, load_prompt
from refdesk.store import Store

ROOT = Path(__file__).resolve().parent.parent
OPINIONS = [
    "Its composed, quiet mood suits the brief.",
    "The calm atmosphere would sit well on a spring tea tin.",
    "Its restrained palette gives the campaign an understated tone.",
    "The {tag} give it a warm, inviting feel for the brief.",
    "Its sense of drama makes it a strong cover image.",
]
SMUGGLED = [
    "Painted for a royal patron, it brings a quiet mood to the brief.",
    "Shown at the Paris Salon of 1855, it gives the campaign an understated tone.",
    "Its Venetian setting gives it a warm, inviting feel for the brief.",
    "Once owned by Empress Josephine, it would sit well on a spring tea tin.",
    "Restored in 1990 after fire damage, it still makes a strong cover image.",
]


def items(records, n=20, seed=0):
    rng = random.Random(seed)
    chosen = rng.sample(sorted((r for r in records if r.subject_tags), key=lambda r: r.id), n)
    out = []
    for i, r in enumerate(chosen):
        tag = r.subject_tags[0].lower()
        out.append((r, OPINIONS[i % len(OPINIONS)].format(tag=tag), "supported", None))
        out.append((r, SMUGGLED[i % len(SMUGGLED)], "unsupported", None))
    return out


def _tag(record, brief):
    """The record's subject tag the brief mentions (singular or plural), else its first."""
    words = brief.lower()
    for tag in record.subject_tags:
        if tag.lower().rstrip("s") in words:
            return tag.lower()
    return record.subject_tags[0].lower()


REALISTIC = [
    "This {medium} work showing {tag} suits the brief: {brief}.",
    "Its {tag} and quiet tone make it a fitting answer to the brief ({brief}).",
    "As a {classification} of {tag}, it gives the brief a classic feel: {brief}.",
    "The {tag} in this {medium} work fit what the brief asks for: {brief}.",
    "Dated {date}, its {tag} lend the brief a sense of heritage: {brief}.",
]
REALISTIC_SMUGGLED = [
    "Painted for a royal patron, this {medium} work showing {tag} suits the brief: {brief}.",
    "Its {tag}, painted near Venice, make it a fitting answer to the brief ({brief}).",
    "As a {classification} once owned by Empress Josephine, it gives the brief a classic "
    "feel: {brief}.",
    "The {tag} in this {medium} work, shown at the Paris Salon, fit what the brief asks for: "
    "{brief}.",
    "Restored in 1990, its {tag} lend the brief a sense of heritage: {brief}.",
]


def realistic_items(records, golden=ROOT / "evals" / "golden" / "golden-v0-synthetic.jsonl"):
    """One (brief, record) pair per golden-v0 retrieve case: the first expected record with
    a medium, a date and a subject tag, so the brief and the work belong together, as they
    do after retrieval. Sentences repeat the record's own facts and the brief's words."""
    by_id = {r.id: r for r in records}
    out = []
    for line in golden.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        candidates = [by_id.get(e["record_id"]) for e in case["expected"]]
        r = next((c for c in candidates if c and c.subject_tags and c.medium and c.date), None)
        if r is None or len(out) == 40:
            continue
        k = (len(out) // 2) % len(REALISTIC)
        brief = case["brief"]
        values = {
            "medium": r.medium.lower(), "tag": _tag(r, case["brief"]),
            "brief": brief[0].lower() + brief[1:], "date": r.date,
            "classification": (r.classification or "work").lower().rstrip("s"),
        }  # fmt: skip
        out.append((r, REALISTIC[k].format(**values), "supported", brief))
        out.append((r, REALISTIC_SMUGGLED[k].format(**values), "unsupported", brief))
    return out


def run(client, prompt, probe_items):
    rows = []
    for record, sentence, label, brief in probe_items:
        brief = None if prompt.name in WITHOUT_BRIEF or prompt.name.startswith("judge") else brief
        text = client.complete(
            "judge-phi4", judge_messages(record, sentence, prompt, brief), job="probe",
            keep_local=True, max_tokens=16, temperature=0,
        ).text  # fmt: skip
        rows.append((label, parse_verdict(text)))
    caught = sum(1 for lab, v in rows if lab == "unsupported" and v == "unsupported")
    alarms = sum(1 for lab, v in rows if lab == "supported" and v != "supported")
    invalid = sum(1 for _, v in rows if v is None)
    half = len(rows) // 2
    return caught, alarms, invalid, half


def main() -> None:
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        records = list(store.iter_records())
    sets = {
        "synthetic opinions": items(records),
        "realistic fit sentences": realistic_items(records),
    }
    ModelManager(
        load_specs(str(ROOT / "config" / "models.yaml")), {"ollama": OllamaBackend()}
    ).ensure("phi4")
    client = LLMClient(
        ProvidersConfig.load(ROOT / "config" / "providers.yaml"), Budgets({}), env={}
    )
    lines = [
        f"# Fit-sentence probe ({date.today().isoformat()})",
        "",
        "> phi4, one fit sentence at a time, temperature 0. Faithful items are opinions about",
        "> mood or use (some name one of the record's own subject tags); corrupted items add",
        "> one fact the record does not give. Synthetic, 20 records, seed 0 (issue #97).",
        "",
        "> The realistic set (#135) repeats the record's own facts and names the brief's",
        "> use, as generators do; prompts measured without the brief still get none.",
        "",
        "| Set | Prompt | Smuggled facts caught | False alarms on faithful items | Invalid |",
        "|---|---|---|---|---|",
    ]
    for path in sorted(PROMPTS.glob("*.md")):
        if not path.stem.startswith(("judge-", "fit-")):
            continue
        prompt = load_prompt(*path.stem.rsplit("-", 1))
        for name, probe_items in sets.items():
            caught, alarms, invalid, half = run(client, prompt, probe_items)
            lines.append(
                f"| {name} | `{prompt.name}` | {caught}/{half} | {alarms}/{half} | {invalid} |"
            )
            print(lines[-1])
    out = ROOT / "evals" / "reports" / f"fit-probe-{date.today().isoformat()}-realistic.md"
    if out.exists():
        raise SystemExit(f"{out.name} exists; reports are never overwritten")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
