"""Run phi4 over Claude's golden-v1 proposals (ADR-018 step 4, issue #15).

Reads runs/labelling-v1/proposals.jsonl (Claude's proposals, kept out of git until Joe's
second blind pass is done, so he never sees proposals for the blind cases) and writes
runs/labelling-v1/proposals-judged.jsonl with a verdict on each. Local only: briefs and
records go to Ollama on this machine.

Usage (PowerShell or WSL2, Ollama running): uv run python scripts/judge_proposals.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from refdesk.evals.proposals import judge_proposals, load_proposal_prompt
from refdesk.llm.client import LLMClient
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.llm.model_manager import ModelManager, OllamaBackend, load_specs
from refdesk.store import Store

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs" / "labelling-v1"
DRAFTS = ROOT / "evals" / "labelling" / "v1" / "briefs-draft.jsonl"


def main() -> None:
    cases = [
        json.loads(line) for line in (RUNS / "proposals.jsonl").read_text("utf-8").splitlines()
    ]
    briefs = {
        d["draft_id"]: d["brief"]
        for d in map(json.loads, DRAFTS.read_text(encoding="utf-8").splitlines())
    }
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        ids = {p["record_id"] for c in cases for p in c["proposals"]}
        records = {i: store.get_record(i) for i in ids}
    ModelManager(
        load_specs(str(ROOT / "config" / "models.yaml")), {"ollama": OllamaBackend()}
    ).ensure("phi4")
    client = LLMClient(
        ProvidersConfig.load(ROOT / "config" / "providers.yaml"), Budgets({}), env={}
    )
    prompt = load_proposal_prompt()
    out, counts = [], Counter()
    for case in cases:
        judged = judge_proposals(
            client, case, briefs[case["draft_id"]], records, judge_tier="judge-phi4", prompt=prompt
        )
        counts.update(p["judge_verdict"] for p in judged)
        out.append(case | {"proposals": judged, "judge_prompt": prompt.name,
                           "judge_prompt_sha256": prompt.sha256})  # fmt: skip
        print(case["draft_id"], Counter(p["judge_verdict"] for p in judged))
    (RUNS / "proposals-judged.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in out), encoding="utf-8"
    )
    print(dict(counts))


if __name__ == "__main__":
    main()
