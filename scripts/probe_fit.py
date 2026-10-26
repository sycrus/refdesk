"""Probe: can phi4 check a fit sentence (opinion) for smuggled facts? (issue #97)

The smoke test showed judge-v1 flagging a pure-opinion fit sentence as UNSUPPORTED. The
judge probe (#122) never sent an opinion sentence on its own (per-claim mode leaves it
out), so this case was unmeasured. Items, labels known by construction, on real records:
- faithful: an opinion about mood or use, sometimes naming one of the record's own subject
  tags ("Its flowers suit a spring tin");
- corrupted: the same opinion plus one fact the record does not give (a patron, an
  exhibition, a place, a date).
Each prompt is run per sentence, temperature 0. Writes evals/reports/fit-probe-<date>.md.

Usage (PowerShell or WSL2, Ollama running): uv run python scripts/probe_fit.py
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from refdesk.evals.judge_probe import parse_verdict
from refdesk.judge import judge_messages
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
        out.append((r, OPINIONS[i % len(OPINIONS)].format(tag=tag), "supported"))
        out.append((r, SMUGGLED[i % len(SMUGGLED)], "unsupported"))
    return out


def run(client, prompt, probe_items):
    rows = []
    for record, sentence, label in probe_items:
        text = client.complete(
            "judge-phi4", judge_messages(record, sentence, prompt), job="probe",
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
    probe_items = items(records)
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
        "| Prompt | Smuggled facts caught | False alarms on pure opinion | Invalid |",
        "|---|---|---|---|",
    ]
    for path in sorted(PROMPTS.glob("*.md")):
        if not path.stem.startswith(("judge-", "fit-")):
            continue
        prompt = load_prompt(*path.stem.rsplit("-", 1))
        caught, alarms, invalid, half = run(client, prompt, probe_items)
        lines.append(f"| `{prompt.name}` | {caught}/{half} | {alarms}/{half} | {invalid} |")
        print(lines[-1])
    out = ROOT / "evals" / "reports" / f"fit-probe-{date.today().isoformat()}.md"
    if out.exists():
        raise SystemExit(f"{out.name} exists; reports are never overwritten")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
