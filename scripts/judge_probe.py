"""Run the judge probe over local Ollama models and write a report (issue: judge probe).

For each model, one at a time on the GPU: unload everything, load the model, measure the
VRAM it took, judge every item, unload. Predictions go to runs/judge-probe/<model>.jsonl
(gitignored); the summary goes to evals/reports/judge-probe-<date>.md.

Usage (PowerShell or WSL2, Ollama running):
    uv run python scripts/judge_probe.py MODEL [MODEL ...]
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

from refdesk.evals.judge_probe import ERROR_TYPES, build_items, parse_verdict, score_judge
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


def main(models: list[str]) -> None:
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        items = build_items(list(store.iter_records()), n_records=30, seed=0)
    out_dir = ROOT / "runs" / "judge-probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for model in models:
        unload_all()
        free_before = nvidia_free_vram_mib()
        started = time.perf_counter()
        post("/api/generate", {"model": model, "keep_alive": "15m"})
        load_s = time.perf_counter() - started
        info = loaded().get(model, {})
        gpu_pct = round(100 * info.get("size_vram", 0) / info["size"]) if info.get("size") else 0
        vram = free_before - nvidia_free_vram_mib()
        predictions, latencies = [], []
        with (out_dir / f"{re.sub(r'[^A-Za-z0-9.-]', '_', model)}.jsonl").open("w") as f:
            for item in items:
                verdict, text, seconds = judge(model, item)
                predictions.append(verdict)
                latencies.append(seconds)
                f.write(
                    json.dumps(
                        {
                            "id": item.id,
                            "label": item.label,
                            "error": item.error_type,
                            "verdict": verdict,
                            "raw": text[:200],
                        }
                    )
                    + "\n"
                )
        score = score_judge(items, predictions, seed=0)
        rows.append((model, score, vram, gpu_pct, load_s, sorted(latencies)[len(latencies) // 2]))
        print(
            f"{model}: accuracy {score.accuracy:.3f} catch {score.catch_rate:.2f} "
            f"false alarm {score.false_alarm_rate:.2f} invalid {score.invalid_rate:.2f}"
        )
    unload_all()
    write_report(rows, len(items))


def write_report(rows, n):
    lines = [
        f"# Judge probe ({date.today().isoformat()})",
        "",
        "> **Synthetic test with known answers.** Each item is a one-sentence rationale built from",
        "> a real record's fields. Half are faithful (record facts plus an opinion about mood);",
        "> half contain exactly one false fact. It measures whether a model catches a false",
        "> fact against the record. It is not agreement with Joe's judgement (needs the 100",
        "> ratings, #16), and real rationales are longer and harder.",
        "",
        f"- Items: {n} ({n // 2} faithful, {n // 2} corrupted: {n // 10} each of "
        f"{', '.join(ERROR_TYPES)}). Seed 0, temperature 0, thinking off where supported.",
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
        "| Model | " + " | ".join(ERROR_TYPES) + " |",
        "|---|" + "---|" * len(ERROR_TYPES),
    ]
    for model, s, *_ in sorted(rows, key=lambda r: -r[1].accuracy):
        cells = " | ".join(f"{s.catch_by_type.get(t, 0):.0%}" for t in ERROR_TYPES)
        lines.append(f"| `{model}` | {cells} |")
    path = ROOT / "evals" / "reports" / f"judge-probe-{date.today().isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
