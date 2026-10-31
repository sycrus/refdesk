"""HTTP API (PRD 13A). Every route has its real request and response models; routes not
implemented by their issue return 501. /healthz is liveness; /readyz (issue #168) runs
the real dependency checks.

Tags matter for the MCP server (FR-12, ADR-015): it may expose only `read` operations.
`gates` operations (approve, export) are never exposed through MCP.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
    QueuedReport,
    Readiness,
    ReportAccepted,
    ReviewRequest,
    RunCreated,
    RunView,
)
from refdesk.boards import (
    BoardService,
    ExportFailed,
    FormatNotSupported,
    GateRefused,
    UnknownAnchor,
    UnknownItem,
    UnknownRun,
    default_service,
)
from refdesk.readiness import report as readiness_report
from refdesk.retrieval.combined import ConditionNotUnderstood

app = FastAPI(
    title="refdesk API",
    version=__version__,
    description=(
        "Rights-checked, explained art references from open museum collections. "
        "The API enforces approval gates; clients only reflect them (PRD 8B)."
    ),
)


@lru_cache(maxsize=1)
def get_service() -> BoardService:
    """The board service: one per process, created on first use. Tests override this
    dependency with a service over a temporary store."""
    return default_service(os.environ.get("REFDESK_DB", "data/refdesk.sqlite"))


Service = Annotated[BoardService, Depends(get_service)]

NOT_FOUND = {404: {"model": Problem, "description": "Unknown run"}}
NOT_IMPLEMENTED = {501: {"model": Problem, "description": "Not implemented yet"}}
GATE_BLOCKED = {409: {"model": GateBlocked, "description": "A gate has not passed"}}


def _unknown_run(run_id: str) -> JSONResponse:
    problem = Problem(code="unknown_run", message=f"No run {run_id!r}.")
    return JSONResponse(status_code=404, content=problem.model_dump())


def _gate_blocked(error: GateRefused) -> JSONResponse:
    blocked = GateBlocked(gate=error.gate, reason=error.reason)
    return JSONResponse(status_code=409, content=blocked.model_dump())


def _not_implemented() -> JSONResponse:
    problem = Problem(code="not_implemented", message="Contract only (issue #13).")
    return JSONResponse(status_code=501, content=problem.model_dump())


@app.post(
    "/boards",
    status_code=202,
    response_model=RunCreated,
    tags=["runs"],
    responses={
        400: {"model": Problem, "description": "Declined: unknown anchor or unusable condition"}
    },
)
def create_board(
    request: BoardRequest,
    background: BackgroundTasks,
    service: Service,
):
    """Start a run from a brief (S1). The search runs after this returns; poll
    GET /runs/{run_id}. Retrieval only for now (issue #45): no model is called."""
    try:
        view = service.create(request)
    except UnknownAnchor:
        problem = Problem(code="unknown_anchor", message=f"No record {request.anchor_id!r}.")
        return JSONResponse(status_code=400, content=problem.model_dump())
    except ConditionNotUnderstood as error:
        problem = Problem(code="condition_not_understood", message=str(error))
        return JSONResponse(status_code=400, content=problem.model_dump())
    background.add_task(service.execute, view.run_id, request)
    return RunCreated(run_id=view.run_id, state=view.state)


@app.get(
    "/runs/{run_id}",
    response_model=RunView,
    tags=["read"],
    responses={**NOT_FOUND},
)
def get_run(run_id: str, service: Service):
    """Run state, gates, items, cost and any stop reason (S2, S3, S7)."""
    view = service.get(run_id)
    if view is None:
        problem = Problem(code="unknown_run", message=f"No run {run_id!r}.")
        return JSONResponse(status_code=404, content=problem.model_dump())
    return view


@app.post(
    "/runs/{run_id}/review",
    response_model=RunView,
    tags=["runs"],
    responses={
        **NOT_FOUND,
        **GATE_BLOCKED,
        400: {"model": Problem, "description": "The board has no such item"},
    },
)
def review(run_id: str, request: ReviewRequest, service: Service):
    """G3: keep (with a note) or drop each flagged item, recorded with who and when.
    Only flagged items can be reviewed; approval (G4) opens when all are decided."""
    try:
        return service.review(run_id, request)
    except UnknownRun:
        problem = Problem(code="unknown_run", message=f"No run {run_id!r}.")
        return JSONResponse(status_code=404, content=problem.model_dump())
    except UnknownItem as error:
        problem = Problem(code="unknown_item", message=f"This board has no item {error.args[0]!r}.")
        return JSONResponse(status_code=400, content=problem.model_dump())
    except GateRefused as error:
        blocked = GateBlocked(gate=error.gate, reason=error.reason)
        return JSONResponse(status_code=409, content=blocked.model_dump())


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
    responses={**NOT_FOUND, **GATE_BLOCKED},
)
def approve(run_id: str, request: ApprovalRequest, service: Service):
    """G4: record approval. Blocked (409) until G3 has no undecided items."""
    try:
        return service.approve(run_id, request)
    except UnknownRun:
        return _unknown_run(run_id)
    except GateRefused as error:
        return _gate_blocked(error)


@app.post(
    "/runs/{run_id}/export",
    response_model=ExportReceipt,
    tags=["gates"],
    responses={
        **NOT_FOUND,
        **GATE_BLOCKED,
        400: {"model": Problem, "description": "Format not supported yet"},
        500: {"model": Problem, "description": "Export failed; the board stays unlocked"},
    },
)
def export(run_id: str, request: ExportRequest, service: Service):
    """G5: export the provenance pack (CSV), then the board is read-only. Irreversible.
    Blocked (409) without an approval record."""
    try:
        return service.export(run_id, request)
    except UnknownRun:
        return _unknown_run(run_id)
    except GateRefused as error:
        return _gate_blocked(error)
    except FormatNotSupported as error:
        problem = Problem(
            code="format_not_supported",
            message=f"{error.args[0]!r} export is not built yet; use csv.",
        )
        return JSONResponse(status_code=400, content=problem.model_dump())
    except ExportFailed as error:
        problem = Problem(
            code="export_failed",
            message=f"{error} The board is still unlocked; nothing was exported.",
        )
        return JSONResponse(status_code=500, content=problem.model_dump())


# S8 reports are tagged `reports`, not `read`: filing is a write, and the queue holds
# operator notes for Joe's review, so neither is exposed through MCP (ADR-015).
@app.post(
    "/reports",
    status_code=202,
    response_model=ReportAccepted,
    tags=["reports"],
    responses={**NOT_FOUND, 400: {"model": Problem, "description": "The board has no such item"}},
)
def report_error(request: ErrorReport, service: Service):
    """S8: "This is wrong". Queued for human review, with who and when. The board is not
    changed."""
    try:
        queued = service.report(request)
    except UnknownRun:
        return _unknown_run(request.run_id)
    except UnknownItem as error:
        problem = Problem(code="unknown_item", message=f"This board has no item {error.args[0]!r}.")
        return JSONResponse(status_code=400, content=problem.model_dump())
    return ReportAccepted(report_id=queued.report_id)


@app.get("/reports", response_model=list[QueuedReport], tags=["reports"])
def list_reports(service: Service):
    """The S8 review queue, oldest first."""
    return service.reports()


@app.get("/healthz", response_model=Health, tags=["ops"])
def healthz():
    """Liveness: the process is up. Touches no dependency, so it answers even when
    /readyz fails."""
    return Health()


# Where the embedding index lives (refdesk.retrieval.registry.Resources.default reads
# the same place; override for a deployment that keeps it elsewhere).
INDEX_DIR = Path(os.environ.get("REFDESK_INDEX_DIR", "data/index/met-clip"))


@app.get(
    "/readyz",
    response_model=Readiness,
    tags=["ops"],
    responses={503: {"model": Readiness, "description": "Not ready"}},
)
def readyz(service: Service):
    """Readiness (issue #168): 503 when the metadata store, the embedding index or a
    required model backend is unavailable, with the reason per check. The store path is
    the metadata store: the runs store shares its SQLite file (default_service)."""
    result = readiness_report(
        store_path=service.runs.path,
        retriever_name=service.retriever_name,
        reasoner=service.reasoner,
        index_dir=INDEX_DIR,
    )
    return JSONResponse(
        status_code=200 if result.ready else 503, content=result.model_dump()
    )


# The UI (PRD 8A, issue #41): the static build of ui/, served at /. It is mounted after
# every API route, so API paths always win. It is not an API operation, so it stays out
# of the OpenAPI spec and can never be exposed through MCP. Without it, the operator
# would need a second server for the UI (ADR-017 chose one service).
UI_DIST = Path(
    os.environ.get("REFDESK_UI_DIST", Path(__file__).resolve().parents[3] / "ui" / "dist")
)


def mount_ui(target: FastAPI, dist: Path) -> None:
    """Serve `dist` at /, or, if the UI is not built, say how to build it. Checked once at
    startup: restart the API after the first `npm run build`."""
    if (dist / "index.html").is_file():
        target.mount("/", StaticFiles(directory=dist, html=True), name="ui")
        return

    @target.get("/", include_in_schema=False)
    def ui_not_built():
        problem = Problem(
            code="ui_not_built",
            message=f"UI not built: run `npm run build` in ui/ ({dist} has no index.html).",
        )
        return JSONResponse(status_code=503, content=problem.model_dump())


mount_ui(app, UI_DIST)
