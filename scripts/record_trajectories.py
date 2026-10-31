"""Record the trajectory suite's runs against the in-process mock server (issue #173).

For each brief in the suite and each of its k runs, this runs the loop once against the
mock generator and mock judge, with the run's planted faults, and writes the run log
(`<suite>/<case>/run-<i>.jsonl`, briefs redacted as in every run log). It then replays each
recording through the loop and refuses to finish unless it classifies as the suite says,
so a recording never contradicts its expected outcome.

Planted faults (`plants` in suite.json):
- `generator: {record_id: behaviour}`: the mock's behaviours ("malformed", "badfield", ...)
  plus "wrongtext": a medium claim whose value matches the record but whose sentence
  states another medium. Code checks cannot see it; the judge is recorded answering
  UNSUPPORTED to every statement about that record, as a working judge would.
- `retrieve: [ids]`: the order the retriever hands out candidates (default: the Open
  records in pool order). Listing a restricted record plants a wrong retrieval.

Offline, no paid call, no network: the transport talks to the mock apps in-process.

What breaks without it: recordings would be hand-written JSON that no loop ever produced,
or would have to be re-made by hand whenever a prompt or the run-log schema changes.

Usage (PowerShell or WSL2):
    uv run python scripts/record_trajectories.py [--suite DIR] [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from refdesk.evals.trajectory import (
    DEFAULT_SUITE,
    RunSpec,
    Suite,
    TrajectoryCase,
    load_suite,
    make_reasoner,
    replay_run,
)
from refdesk.llm.mock_server import _record_fields, create_app
from refdesk.loop import LoopConfig, LoopController
from refdesk.runlog import RunLog

# The medium claim keeps the record's value but its sentence says otherwise. Code checks
# the medium's value only (the attribution's text is checked too, so a wrong artist
# sentence would never reach the judge), so only the judge can catch this one.
WRONG_MEDIUM_TEXT = "It is tempera on a gold ground."


class PlantedTransport:
    """Routes each request to a mock app scripted with the behaviour planted for the
    record the request is about (found by the record's title in the prompt)."""

    def __init__(self, case: TrajectoryCase, run: RunSpec, judge_host: str):
        self.by_title = {r.title: r.id for r in case.pool}
        self.generator = run.plants.get("generator", {})
        self.judge_host = judge_host
        self.apps: dict[str, TestClient] = {}

    def _app(self, behaviour: str) -> TestClient:
        if behaviour not in self.apps:
            self.apps[behaviour] = TestClient(create_app(script=[behaviour]))
        return self.apps[behaviour]

    def post_json(self, url, headers, payload):
        user = next(m["content"] for m in reversed(payload["messages"]) if m["role"] == "user")
        record_id = self.by_title[_record_fields(user)["title"]]
        planted = self.generator.get(record_id, "ok")
        if urlsplit(url).hostname == self.judge_host:
            behaviour = "unsupported" if planted == "wrongtext" else "ok"
        else:
            behaviour = "ok" if planted == "wrongtext" else planted
        response = self._app(behaviour).post(urlsplit(url).path, json=payload)
        body = response.json()
        if planted == "wrongtext" and urlsplit(url).hostname != self.judge_host:
            message = body["choices"][0]["message"]
            rationale = json.loads(message["content"])
            for claim in rationale["claims"]:
                if claim["field"] == "medium":
                    claim["text"] = WRONG_MEDIUM_TEXT
            message["content"] = json.dumps(rationale)
        return response.status_code, body


def record_run(suite: Suite, case: TrajectoryCase, run: RunSpec) -> Path:
    path = suite.recording(case, run)
    path.unlink(missing_ok=True)
    by_id = {r.id: r for r in case.pool}
    order = run.plants.get("retrieve") or sorted(case.eligible, key=list(by_id).index)
    left = [by_id[rid] for rid in order]

    def retrieve(n: int):
        nonlocal left
        taken, left = left[:n], left[n:]
        return taken

    judge_host = urlsplit(make_reasoner(suite, None).config.providers["mock-judge"].base_url)
    transport = PlantedTransport(case, run, judge_host.hostname)
    log = RunLog(path, run_id=f"{case.id}-run-{run.index}", brief=case.brief)
    controller = LoopController(
        LoopConfig(**suite.loop), make_reasoner(suite, transport), clock=lambda: 0.0, log=log
    )
    controller.run(
        brief=case.brief, retrieve=retrieve, target=case.target, keep_local=case.keep_local,
        cap_usd=case.cap_usd,
    )  # fmt: skip
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--force", action="store_true", help="replace existing recordings")
    args = parser.parse_args(argv)
    suite = load_suite(args.suite)
    existing = [suite.recording(c, r) for c in suite.cases for r in c.runs]
    if any(p.exists() for p in existing) and not args.force:
        print(f"recordings exist under {suite.root}; pass --force to replace them")
        return 1
    failed = 0
    for case in suite.cases:
        for run in case.runs:
            path = record_run(suite, case, run)
            outcome = replay_run(suite, case, run)
            mark = "ok " if not outcome.regressed else "BAD"
            failed += outcome.regressed
            print(f"{mark} {path.as_posix()}: {outcome.outcome} ({outcome.detail})")
    if failed:
        print(f"{failed} recordings do not give their expected outcome")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
