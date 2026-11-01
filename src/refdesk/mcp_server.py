"""Read-only MCP server on top of the refdesk API (issue #160, FR-12, ADR-015).

A separate process. Each tool makes exactly one HTTP call to the API and passes the
answer through; the server holds no logic of its own (no store, no retrieval, no rights
rules). Every tool maps to an API operation tagged `read`. Approve, export, reports and
starting a board are never exposed: starting a board runs the LLM loop and spends
budget, and MCP tools never spend (Joe, 2026-10-31, #160).

Museum text is untrusted input (PRD 13). Every JSON result is wrapped in an envelope
that marks it as untrusted data, with the fixed notice from `refdesk.wording`.

What breaks without it: an agent client would need the library itself (duplicated
logic that can drift from the API), or would talk to the API with no read-only fence.

Run (PowerShell, with the API already on :8000):
    uv sync --extra mcp
    uv run python -m refdesk.mcp_server                    # stdio
    uv run python -m refdesk.mcp_server --transport http   # http://127.0.0.1:8765/mcp
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from refdesk.wording import MCP_UNTRUSTED_NOTICE

API_URL = os.environ.get("REFDESK_API_URL", "http://127.0.0.1:8000")
# Streamable HTTP binds to loopback only until auth and scopes land (#201). There is
# deliberately no --host option.
HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765


@dataclass(frozen=True)
class Route:
    """The one API operation a tool calls. The contract tests read this table."""

    method: str
    path: str  # OpenAPI path template, e.g. /records/{record_id}


ROUTES: dict[str, Route] = {
    "list_runs": Route("GET", "/runs"),
    "get_run": Route("GET", "/runs/{run_id}"),
    "get_record": Route("GET", "/records/{record_id}"),
    "get_rights_record": Route("GET", "/records/{record_id}/rights"),
    "search_references": Route("POST", "/search"),
    "get_image": Route("GET", "/records/{record_id}/image"),
    "get_provenance": Route("POST", "/provenance"),
}

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

RecordId = Annotated[str, Field(description="'<source>:<object_id>', e.g. 'met:436535'")]
ClientFactory = Callable[[], httpx.AsyncClient]


def default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_URL, timeout=30.0)


def _segment(value: str) -> str:
    """Quote one path segment, so an ID can never add a path segment or walk up one
    (`/`, `..`). Transport safety, not a rule about records."""
    if value in {"", ".", ".."}:
        raise ToolError(f"Not a valid ID: {value!r}")
    return quote(value, safe=":")


def _envelope(route: Route, path: str, body: Any) -> str:
    return json.dumps(
        {
            "untrusted_museum_data": True,
            "notice": MCP_UNTRUSTED_NOTICE,
            "api_call": f"{route.method} {path}",
            "data": body,
        },
        ensure_ascii=False,
    )


def build_server(client_factory: ClientFactory = default_client) -> FastMCP:
    """The server with its seven read tools. Tests pass a factory over a stub API."""
    server = FastMCP(
        "refdesk",
        instructions=(
            "Read-only access to refdesk runs, records, search, images and rights "
            "records. " + MCP_UNTRUSTED_NOTICE
        ),
        host=HTTP_HOST,
        port=DEFAULT_HTTP_PORT,
    )

    async def call(name: str, params: dict[str, str] | None = None, body: Any = None):
        """The single HTTP call behind a tool. Non-2xx answers become tool errors, with
        the API's own problem body."""
        route = ROUTES[name]
        path = route.path.format(**{k: _segment(v) for k, v in (params or {}).items()})
        async with client_factory() as client:
            response = await client.request(route.method, path, json=body)
        if response.is_error:
            raise ToolError(f"API {response.status_code} on {route.method} {path}: "
                            f"{response.text}")
        return route, path, response

    async def json_tool(name: str, params: dict[str, str] | None = None, body: Any = None):
        route, path, response = await call(name, params, body)
        return _envelope(route, path, response.json())

    def tool(fn):
        server.add_tool(fn, name=fn.__name__, annotations=READ_ONLY, structured_output=False)
        return fn

    @tool
    async def list_runs() -> str:
        """Run history, newest first: state, stop reason, cost, where each brief was sent
        and who approved. Briefs are redacted."""
        return await json_tool("list_runs")

    @tool
    async def get_run(run_id: str) -> str:
        """One run: state, gates, items, cost and any stop reason."""
        return await json_tool("get_run", {"run_id": run_id})

    @tool
    async def get_record(record_id: RecordId) -> str:
        """One museum record as the source gave it. image_url only for Open works."""
        return await json_tool("get_record", {"record_id": record_id})

    @tool
    async def get_rights_record(record_id: RecordId) -> str:
        """The rights record: status, the source field and value it was read from,
        licence, credit line and when it was checked. Not legal advice."""
        return await json_tool("get_rights_record", {"record_id": record_id})

    @tool
    async def search_references(
        query: str = "",
        anchor_id: str | None = None,
        conditions: dict[str, Any] | None = None,
        k: Annotated[int, Field(ge=1, le=50)] = 12,
    ) -> str:
        """Retrieval only (no model call, no spend): ranked hits with rights status,
        credit line and, for Open works, an image URL on the museum's own host. Give a
        query, an anchor_id, or both."""
        body: dict[str, Any] = {"query": query, "k": k}
        if anchor_id is not None:
            body["anchor_id"] = anchor_id
        if conditions is not None:
            body["conditions"] = conditions
        return await json_tool("search_references", body=body)

    @tool
    async def get_image(record_id: RecordId) -> list:
        """The cached image of an Open work, from refdesk's own cache. For the credit
        line to keep with it, call get_rights_record or get_provenance."""
        route, path, response = await call("get_image", {"record_id": record_id})
        media = response.headers.get("content-type", "image/jpeg").split(";")[0]
        return [
            _envelope(route, path, {"record_id": record_id, "media_type": media}),
            Image(data=response.content, format=media.removeprefix("image/")),
        ]

    @tool
    async def get_provenance(record_ids: list[str]) -> str:
        """Record-level rights rows for up to 100 IDs, to keep the rights evidence with
        a download. Each row is a rights record, not an approved export."""
        return await json_tool("get_provenance", body={"record_ids": record_ids})

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="refdesk.mcp_server", description=__doc__.split("\n")[0])
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT, help="http only")
    args = parser.parse_args(argv)
    server = build_server()
    if args.transport == "http":
        server.settings.port = args.port
        server.run("streamable-http")
    else:
        server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
