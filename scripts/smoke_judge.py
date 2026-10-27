"""Manual smoke test of the phi4 judge against local Ollama (issue #97). Not run in CI.

Loads phi4 through the ModelManager (unloading anything else; the load time is printed as
an event), then judges two rationales for real Met records: one faithful, one with a
dropped attribution prefix and a sentence that adds a fact. Prints every verdict.

Usage (PowerShell or WSL2, Ollama running, phi4 pulled):
    uv run python scripts/smoke_judge.py
"""

from __future__ import annotations

import json
from pathlib import Path

from refdesk.judge import judge_rationale
from refdesk.llm.client import LLMClient
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.llm.model_manager import ModelManager, OllamaBackend, load_specs
from refdesk.rationale import Claim, Rationale
from refdesk.store import Store
from refdesk.verifier import check_claims, item_status

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        records = [
            r for r in store.iter_records() if r.artist and r.artist.startswith("Workshop of")
        ]
    record = sorted(records, key=lambda r: r.id)[0]
    master = record.artist.removeprefix("Workshop of ")
    fit = "Its composed, quiet mood suits the brief."
    medium = record.medium.lower()
    good = Rationale(
        claims=(
            Claim(
                field="artist", value=record.artist, text=f"It is from the workshop of {master}."
            ),
            Claim(field="medium", value=record.medium, text=f"It is {medium}."),
        ),
        fit=fit,
    )
    bad = Rationale(
        claims=(
            Claim(field="artist", value=record.artist, text=f"It is a work by {master}."),
            Claim(
                field="medium",
                value=record.medium,
                text=f"It is {medium}, painted for a royal patron.",
            ),
        ),
        fit=fit,
    )

    events = []
    manager = ModelManager(
        load_specs(str(ROOT / "config" / "models.yaml")),
        {"ollama": OllamaBackend()},
        on_event=events.append,
    )
    manager.ensure("phi4")
    print("event:", json.dumps(events[-1]) if events else "phi4 already loaded")

    config = ProvidersConfig.load(ROOT / "config" / "providers.yaml")
    client = LLMClient(config, Budgets({}), env={})
    print("record:", record.id, "|", record.artist, "|", record.medium)
    for name, rationale in (("faithful", good), ("corrupted", bad)):
        code = check_claims(rationale, record)
        judged = judge_rationale(
            client, judge_tier="judge-phi4", generator_tier="local-small", record=record,
            rationale=rationale, keep_local=True, job="smoke",
        )  # fmt: skip
        print(
            f"{name}: code {'pass' if code.passed else 'fail'} {list(code.failures)} | "
            f"judge {'pass' if judged.verdict.passed else 'fail'} {list(judged.verdict.failures)} "
            f"| {judged.calls} calls, model {judged.model_reported} | "
            f"status: {item_status(code, judged.verdict)}"
        )


if __name__ == "__main__":
    main()
