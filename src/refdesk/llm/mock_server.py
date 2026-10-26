"""Mock LLM server (PRD 10, tier 1; issue #39). The default backend for tests and CI.

Speaks the same OpenAI-style `POST /v1/chat/completions` as the real providers, so the
real client and transport are exercised end to end. Answers are deterministic.

Failure modes for tests and drills (PRD 13A: "provider 429s from the mock server"):
- `latency_s`: delay every answer.
- `script`: behaviours applied to successive requests, cycling: "ok", "429", "500",
  "timeout" (wait `timeout_s`, longer than the client's timeout, then answer).
- `POST /_mock/script` changes the script while the server runs.

Rationale prompts (system message containing "Task: refdesk-rationale", issue #94) get
structured claims built from the record block, so the pipeline runs end to end without a
model. Scripted bad answers for those prompts: "malformed" (not JSON), "nofit" (no fit
sentence), "badfield" (a claim on a field records do not have). Judge prompts (issue #97)
answer SUPPORTED, or UNSUPPORTED / a malformed answer when scripted "unsupported" /
"malformed".

Run: uv run python -m refdesk.llm.mock_server --port 8100 [--latency 0.2] [--script ok,429]
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
from typing import Annotated, Any

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

BEHAVIOURS = {"ok", "429", "500", "timeout", "malformed", "nofit", "badfield", "unsupported"}
RATIONALE_TASK = "Task: refdesk-rationale"
JUDGE_TASKS = (
    "You check a rationale against a museum record.",  # prompts/judge-v1.md
    "You check one sentence of opinion about an artwork",  # prompts/fit-v1.md
)


def _record_fields(user: str) -> dict[str, str]:
    """`field: value` lines after the "Record" line of a rationale prompt."""
    _, _, block = user.partition("Record")
    fields = {}
    for line in block.splitlines()[1:]:
        key, sep, value = line.partition(": ")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def _rationale(user: str, behaviour: str) -> str:
    if behaviour == "malformed":
        return "This painting would look lovely on the tin."
    fields = _record_fields(user)
    claims = [
        {"field": f, "value": fields[f], "text": f"The record gives the {f} as {fields[f]}."}
        for f in ("artist", "date", "medium")
        if f in fields
    ]
    if "subject_tags" in fields:
        tag = fields["subject_tags"].split("; ")[0]
        claims.append(
            {"field": "subject_tags", "value": tag, "text": f"Its subjects include {tag}."}
        )
    if behaviour == "badfield":
        claims.append(
            {"field": "provenance", "value": "Empress Josephine", "text": "It belonged to her."}
        )
    body: dict[str, Any] = {"claims": claims}
    if behaviour != "nofit":
        body["fit"] = "Its quiet mood suits the brief (mock)."
    return json.dumps(body)


def _answer(payload: dict[str, Any], behaviour: str = "ok") -> dict[str, Any]:
    messages = payload.get("messages", [])
    last = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    if RATIONALE_TASK in system:
        text = _rationale(last, behaviour)
    elif any(task in system for task in JUDGE_TASKS):
        text = {"unsupported": "UNSUPPORTED", "malformed": "Maybe."}.get(behaviour, "SUPPORTED")
    else:
        text = f"MOCK: {last[:60]}"
    prompt_tokens = sum(len(m.get("content", "")) for m in messages) // 4
    return {
        "model": "mock-1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": len(text) // 4},
    }


def create_app(
    *, latency_s: float = 0.0, script: list[str] | None = None, timeout_s: float = 30.0
) -> FastAPI:
    app = FastAPI(title="refdesk mock LLM")
    state = {"cycle": None}

    def set_script(new: list[str]) -> None:
        unknown = set(new) - BEHAVIOURS
        if not new or unknown:
            raise ValueError(f"script must use {sorted(BEHAVIOURS)}, got {new}")
        state["cycle"] = itertools.cycle(new)

    set_script(script or ["ok"])

    @app.post("/v1/chat/completions")
    async def chat(payload: Annotated[dict[str, Any], Body()]):
        behaviour = next(state["cycle"])
        if latency_s:
            await asyncio.sleep(latency_s)
        if behaviour == "429":
            return JSONResponse({"error": "rate limited (mock)"}, status_code=429)
        if behaviour == "500":
            return JSONResponse({"error": "server error (mock)"}, status_code=500)
        if behaviour == "timeout":
            await asyncio.sleep(timeout_s)
        return _answer(payload, behaviour)

    @app.post("/_mock/script")
    async def change_script(body: Annotated[dict[str, list[str]], Body()]):
        try:
            set_script(body["script"])
        except (KeyError, ValueError) as error:
            return JSONResponse({"error": str(error)}, status_code=422)
        return {"script": body["script"]}

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="refdesk mock LLM server")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--latency", type=float, default=0.0)
    parser.add_argument("--script", default="ok", help="comma-separated: ok,429,500,timeout")
    parser.add_argument("--timeout-s", type=float, default=30.0)
    args = parser.parse_args()
    app = create_app(
        latency_s=args.latency, script=args.script.split(","), timeout_s=args.timeout_s
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
