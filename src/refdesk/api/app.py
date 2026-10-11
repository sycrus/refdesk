"""HTTP API skeleton (PRD 13A, issue #13). Contract only: every route has its real request
and response models, but returns 501 until its issue implements it. /healthz is live;
/readyz honestly reports not ready.

Tags matter for the MCP server (FR-12, ADR-015): it may expose only `read` operations.
`gates` operations (approve, export) are never exposed through MCP.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from refdesk import __version__
from refdesk.api.models import (
    ApprovalRequest,
    BoardRequest,
    CapRaise,
    ErrorReport,
    ExportReceipt,
    ExportRequest,
    GateBlocked,
    Health,
    Problem,
    Readiness,
    ReportAccepted,
    ReviewRequest,
    RunCreated,
    RunView,
)

app = FastAPI(
    title="refdesk API",
    version=__version__,
    description=(
        "Rights-checked, explained art references from open museum collections. "
        "The API enforces approval gates; clients only reflect them (PRD 8B)."
    ),
)

NOT_FOUND = {404: {"model": Problem, "description": "Unknown run"}}
NOT_IMPLEMENTED = {501: {"model": Problem, "description": "Not implemented yet"}}
GATE_BLOCKED = {409: {"model": GateBlocked, "description": "A gate has not passed"}}


def _not_implemented() -> JSONResponse:
    problem = Problem(code="not_implemented", message="Contract only (issue #13).")
    return JSONResponse(status_code=501, content=problem.model_dump())


@app.post(
    "/boards",
    status_code=202,
    response_model=RunCreated,
    tags=["runs"],
    responses={**NOT_IMPLEMENTED, 400: {"model": Problem, "description": "Declined at G0"}},
)
def create_board(request: BoardRequest):
    """Start a run from a brief (S1). G0 intake may decline it with a reason."""
    return _not_implemented()


@app.get(
    "/runs/{run_id}",
    response_model=RunView,
    tags=["read"],
    responses={**NOT_FOUND, **NOT_IMPLEMENTED},
)
def get_run(run_id: str):
    """Run state, gates, items, cost and any stop reason (S2, S3, S7)."""
    return _not_implemented()


@app.post(
    "/runs/{run_id}/review",
    response_model=RunView,
    tags=["runs"],
    responses={**NOT_FOUND, **GATE_BLOCKED, **NOT_IMPLEMENTED},
)
def review(run_id: str, request: ReviewRequest):
    """G3: keep (with a note) or drop each flagged item."""
    return _not_implemented()


@app.post(
    "/runs/{run_id}/cap",
    response_model=RunView,
    tags=["runs"],
    responses={**NOT_FOUND, **GATE_BLOCKED, **NOT_IMPLEMENTED},
)
def raise_cap(run_id: str, request: CapRaise):
    """G1: raise the spend cap (recorded with name and time) and resume from the checkpoint."""
    return _not_implemented()


@app.post(
    "/runs/{run_id}/approve",
    response_model=RunView,
    tags=["gates"],
    responses={**NOT_FOUND, **GATE_BLOCKED, **NOT_IMPLEMENTED},
)
def approve(run_id: str, request: ApprovalRequest):
    """G4: record approval. Blocked (409) until G3 has no undecided items."""
    return _not_implemented()


@app.post(
    "/runs/{run_id}/export",
    response_model=ExportReceipt,
    tags=["gates"],
    responses={**NOT_FOUND, **GATE_BLOCKED, **NOT_IMPLEMENTED},
)
def export(run_id: str, request: ExportRequest):
    """G5: export the provenance pack. Blocked (409) without an approval record."""
    return _not_implemented()


@app.post(
    "/reports",
    status_code=202,
    response_model=ReportAccepted,
    tags=["runs"],
    responses=NOT_IMPLEMENTED,
)
def report_error(request: ErrorReport):
    """S8: "This is wrong". Queued for human review."""
    return _not_implemented()


@app.get("/healthz", response_model=Health, tags=["ops"])
def healthz():
    """Liveness."""
    return Health()


@app.get(
    "/readyz",
    response_model=Readiness,
    tags=["ops"],
    responses={503: {"model": Readiness, "description": "Not ready"}},
)
def readyz():
    """Readiness: fails when the metadata store, embedding index or model backend is down."""
    checks = dict.fromkeys(
        ("metadata_store", "embedding_index", "model_backend"), "not implemented"
    )
    return JSONResponse(status_code=503, content=Readiness(ready=False, checks=checks).model_dump())
