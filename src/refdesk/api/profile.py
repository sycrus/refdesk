"""Deployment profiles (issue #167, ADR-025).

`full` (the default) is the normal system. `demo` is the public hosted demo: recorded
runs, read-only. In the demo profile only operations tagged `read` or `ops` answer;
every other operation (starting a board, review, cap raise, cancel, approval, export,
the S8 reports queue) is refused with 403 before it reaches the board service.

What it does: one app-wide dependency checks the matched route's OpenAPI tags. The rule
is by tag, so a route added later is covered without a change here, and an untagged
route is refused (fail closed). The same tags decide what MCP may expose (ADR-015).

What breaks without it: a public instance would accept approvals and exports from
anonymous visitors (PRD 8B: the API enforces gates; hiding buttons is not enough), and
would collect S8 reports from people who never agreed to it (ADR-025).

Set with REFDESK_PROFILE. An unknown value is an error, so a typo on the host stops
startup rather than starting the full profile in public.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, Request

PROFILES = ("full", "demo")
DEMO_ALLOWED_TAGS = frozenset({"read", "ops"})
DEMO_MESSAGE = (
    "This is the public demo: recorded runs, read-only. Starting boards, review, "
    "approval and export are disabled here (ADR-025); they work in a local run."
)


class DisabledInDemo(Exception):
    """An operation the demo profile does not allow."""


def get_profile() -> str:
    profile = os.environ.get("REFDESK_PROFILE", "full")
    if profile not in PROFILES:
        raise ValueError(f"REFDESK_PROFILE={profile!r}: expected one of {', '.join(PROFILES)}")
    return profile


def demo_guard(request: Request, profile: Annotated[str, Depends(get_profile)]) -> None:
    """Refuse every operation outside `read` and `ops` when the profile is `demo`."""
    if profile != "demo":
        return
    tags = set(getattr(request.scope.get("route"), "tags", None) or ())
    if not tags or not tags <= DEMO_ALLOWED_TAGS:
        raise DisabledInDemo(request.url.path)
