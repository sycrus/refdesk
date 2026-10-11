"""Mock LLM server (PRD 10, tier 1; issue #39). The default backend for tests and CI.

Speaks the same OpenAI-style `POST /v1/chat/completions` as the real providers, so the
real client and transport are exercised end to end. Answers are deterministic.

Failure modes for tests and drills (PRD 13A: "provider 429s from the mock server"):
- `latency_s`: delay every answer.
- `script`: behaviours applied to successive requests, cycling: "ok", "429", "500",
  "timeout" (wait `timeout_s`, longer than the client's timeout, then answer).
- `POST /_mock/script` changes the script while the server runs.

Run: uv run python -m refdesk.llm.mock_server --port 8100 [--latency 0.2] [--script ok,429]
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
from typing import Annotated, Any

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

BEHAVIOURS = {"ok", "429", "500", "timeout"}


def _answer(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages", [])
    last = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
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
        return _answer(payload)

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
