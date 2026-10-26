"""Run the judge probe over local Ollama models and write a report (issue: judge probe).

For each model, one at a time on the GPU: unload everything, load the model, measure the
VRAM it took, judge every item, unload. Predictions go to
runs/judge-probe/<set>-<model>.jsonl (gitignored); the summary goes to
evals/reports/judge-probe-<date>-<set>.md, so a second set the same day never overwrites it.

Usage (PowerShell or WSL2, Ollama running):
    uv run python scripts/judge_probe.py [--set v1|hard] [--per-claim] MODEL [MODEL ...]

--set hard     five-claim rationales with subtle errors (issue #122); default v1.
--per-claim    also run general judges (phi4) one claim at a time, as the fact-check
               models already are, so every judge is compared in both modes.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

from refdesk.evals.judge_probe import (
    ERROR_TYPES,
    HARD_ERROR_TYPES,
    build_hard_items,
    build_items,
    parse_verdict,
    score_judge,
)
from refdesk.llm.model_manager import nvidia_free_vram_mib
from refdesk.store import Store

BASE = "http://127.0.0.1:11434"
ROOT = Path(__file__).resolve().parent.parent
SYSTEM = (
    "You check a rationale against a museum record. Every factual claim in the rationale "
    "(title, artist, date, medium, subjects, owners or history, anything else factual) must "
    "be stated in the record. Opinions about mood, tone or fit for a brief are not factual "
    "claims. Reply with exactly one word: SUPPORTED if every factual claim is in the "
    "record, otherwise UNSUPPORTED."
)


def post(path, payload, timeout=600):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def loaded():
    with urllib.request.urlopen(BASE + "/api/ps", timeout=10) as response:
        return {m["name"]: m for m in json.load(response).get("models", [])}


def unload_all():
    for name in loaded():
        post("/api/generate", {"model": name, "keep_alive": 0})
    time.sleep(2)


def style(model: str) -> str:
    if "minicheck" in model:
        return "minicheck"
    if "guardian" in model:
        return "guardian"
    return "general"


def messages(model: str, item) -> list[dict]:
    if style(model) == "minicheck":
        # Bespoke-MiniCheck's documented format; it answers Yes or No.
        return [{"role": "user", "content": f"Document: {item.document}\nClaim: {item.rationale}"}]
    if style(model) == "guardian":
        # Granite Guardian groundedness check: context = the record, assistant = the rationale.
        # It answers Yes if the risk (ungrounded) is present, so the verdict is inverted below.
        return [
            {"role": "system", "content": "groundedness"},
            {"role": "context", "content": item.document},
            {"role": "assistant", "content": item.rationale},
        ]
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Record:\n{item.document}\n\nRationale:\n{item.rationale}"},
    ]


def judge(model: str, item) -> tuple[str | None, str, float]:
    payload = {
        "model": model,
        "stream": False,
        "messages": messages(model, item),
        "options": {"temperature": 0, "num_predict": 16},
    }
    if style(model) == "general":
        payload["think"] = False
    started = time.perf_counter()
    try:
        text = post("/api/chat", payload)["message"]["content"]
    except urllib.error.HTTPError:
        payload.pop("think", None)  # models without a thinking switch reject the flag
        text = post("/api/chat", payload)["message"]["content"]
    seconds = time.perf_counter() - started
    verdict = parse_verdict(text)
    if style(model) == "guardian" and verdict is not None:
        # Guardian answers whether the risk is present: Yes = ungrounded.
        verdict = {"supported": "unsupported", "unsupported": "supported"}[verdict]
    return verdict, text, seconds


def judge_claims(model: str, item) -> tuple[str | None, str, float]:
    """Claim checkers are built for single factual claims: check each one; the rationale is
    unsupported if any claim is. Opinion is never sent, because it is not a claim."""
    verdicts, texts, seconds = [], [], 0.0
    for claim in item.claims:
        verdict, text, s = judge(model, dataclasses.replace(item, rationale=claim))
        verdicts.append(verdict)
        texts.append(text.strip()[:20])
        seconds += s
    if None in verdicts:
        return None, " | ".join(texts), seconds
    overall = "unsupported" if "unsupported" in verdicts else "supported"
    return overall, " | ".join(texts), seconds


def main(models: list[str], item_set: str = "v1", per_claim_all: bool = False) -> None:
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        records = list(store.iter_records())
    if item_set == "hard":
        items = build_hard_items(records, n_per_type=10, seed=0)
    else:
        items = build_items(records, n_records=30, seed=0)
    out_dir = ROOT / "runs" / "judge-probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for model in models:
        unload_all()
        free_before = nvidia_free_vram_mib()
        started = time.perf_counter()
        post("/api/generate", {"model": model, "keep_alive": "15m"})
        load_s = time.perf_counter() - started
        # Ollama lists an untagged model as "<name>:latest".
        running = loaded()
        info = running.get(model) or running.get(f"{model}:latest", {})
        gpu_pct = round(100 * info.get("size_vram", 0) / info["size"]) if info.get("size") else 0
        vram = free_before - nvidia_free_vram_mib()
        modes = [("", judge)]
        if per_claim_all or style(model) in ("minicheck", "guardian"):
            modes.append((" (per claim)", judge_claims))
        for suffix, run in modes:
            name = model + suffix
            predictions, latencies = [], []
            out = out_dir / f"{item_set}-{re.sub(r'[^A-Za-z0-9.-]', '_', name)}.jsonl"
            with out.open("w") as f:
                for item in items:
                    verdict, text, seconds = run(model, item)
                    predictions.append(verdict)
                    latencies.append(seconds)
                    record = {"id": item.id, "label": item.label, "error": item.error_type,
                              "verdict": verdict, "raw": text[:200]}  # fmt: skip
                    f.write(json.dumps(record) + "\n")
            score = score_judge(items, predictions, seed=0)
            rows.append(
                (name, score, vram, gpu_pct, load_s, sorted(latencies)[len(latencies) // 2])
            )
            print(
                f"{name}: accuracy {score.accuracy:.3f} catch {score.catch_rate:.2f} "
                f"false alarm {score.false_alarm_rate:.2f} invalid {score.invalid_rate:.2f}"
            )
    unload_all()
    write_report(rows, len(items), item_set)


INTROS = {
    "v1": [
        "> **Synthetic test with known answers.** Each item is a one-sentence rationale built from",
        "> a real record's fields. Half are faithful (record facts plus an opinion about mood);",
        "> half contain exactly one false fact. It measures whether a model catches a false",
        "> fact against the record. It is not agreement with Joe's judgement (needs the 100",
        "> ratings, #16), and real rationales are longer and harder.",
    ],
    "hard": [
        "> **Synthetic test with known answers, hard set (#122).** Each item is a five-claim",
        "> rationale built from a real record, claims in random order, plus an opinion. Faithful",
        "> items are paraphrased (to tempt false alarms); corrupted items carry one subtle error:",
        "> a date just outside the record's range, a dropped attribution prefix, a subject more",
        "> specific than the record, or canvas and wood swapped. Not agreement with Joe's",
        "> judgement (#16). Met records have no long description text, so checks across",
        "> paragraph fields remain untested.",
    ],
}


def write_report(rows, n, item_set="v1"):
    types = HARD_ERROR_TYPES if item_set == "hard" else ERROR_TYPES
    lines = [
        f"# Judge probe, {item_set} set ({date.today().isoformat()})",
        "",
        *INTROS[item_set],
        "",
        f"- Items: {n} ({n // 2} faithful, {n // 2} corrupted: {n // 2 // len(types)} each of "
        f"{', '.join(types)}). Seed 0, temperature 0, thinking off where supported.",
        "- Hardware: RTX 5080 (16 GB), Ollama. One model on the GPU at a time.",
        "",
        "| Model | Accuracy [95% CI] | Catches false facts | False alarms | Invalid | "
        "VRAM | On GPU | Load | Median per item |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for model, s, vram, gpu, load_s, median in sorted(rows, key=lambda r: -r[1].accuracy):
        lines.append(
            f"| `{model}` | {s.accuracy:.3f} [{s.accuracy_ci[0]:.3f}, {s.accuracy_ci[1]:.3f}] | "
            f"{s.catch_rate:.0%} | {s.false_alarm_rate:.0%} | {s.invalid_rate:.0%} | "
            f"{vram / 1024:.1f} GB | {gpu}% | {load_s:.0f} s | {median:.2f} s |"
        )
    lines += [
        "",
        "## Catch rate by error type",
        "",
        "| Model | " + " | ".join(types) + " |",
        "|---|" + "---|" * len(types),
    ]
    for model, s, *_ in sorted(rows, key=lambda r: -r[1].accuracy):
        cells = " | ".join(f"{s.catch_by_type.get(t, 0):.0%}" for t in types)
        lines.append(f"| `{model}` | {cells} |")
    path = ROOT / "evals" / "reports" / f"judge-probe-{date.today().isoformat()}-{item_set}.md"
    if path.exists():
        raise SystemExit(f"{path.name} exists; reports are never overwritten (CLAUDE.md)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    item_set = "v1"
    if "--set" in args:
        at = args.index("--set")
        item_set = args[at + 1]
        del args[at : at + 2]
    per_claim_all = "--per-claim" in args
    args = [a for a in args if a != "--per-claim"]
    if item_set not in INTROS or not args:
        raise SystemExit(__doc__)
    main(args, item_set, per_claim_all)
