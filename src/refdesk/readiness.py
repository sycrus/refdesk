"""Readiness checks behind GET /readyz (issue #168; PRD 13A).

`/healthz` says the process is alive; `/readyz` says it can serve boards. Three
dependencies can stand in the way, and each check answers with the reason in words:

- metadata_store: the SQLite file opens read-only and its `records` table answers a
  count. Read-only, so a probe can never create or lock the database as a side effect.
- embedding_index: the FAISS index actually loads (faiss-cpu is a main dependency; no
  torch here). Required only when the configured retriever reads the index
  (`registry.NEEDS_INDEX`); a metadata-only deployment is ready without one.
- model_backend: every tier the boards need (generator, then the resolved judge) is
  callable. Free providers (mock, Ollama) are probed with `GET {base}/models`, the one
  OpenAI-style path both speak. A paid provider is never probed -- a readiness probe
  must not make a paid call -- so the client's own pre-call guards are mirrored
  instead: an unpriced tier or a missing key refuses every call, which is exactly
  "unavailable".

Kept a leaf module (no imports from boards/reasoning at runtime) so it stays trivially
testable: the caller passes a store path, a retriever name and a `Reasoner`. What
breaks without it: the API would look healthy while no board can complete, and the
PRD 13A failure drill "readiness failing because the index is unavailable" would have
nothing to trigger.
"""

from __future__ import annotations

import os
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from refdesk.api.models import Readiness

if TYPE_CHECKING:
    from refdesk.llm.config import ProvidersConfig
    from refdesk.reasoning import Reasoner

PROBE_TIMEOUT_S = 2.0  # a probe waits two seconds, not the client's sixty


@dataclass(frozen=True)
class Check:
    ok: bool
    detail: str


def probe_models(url: str, timeout: float = PROBE_TIMEOUT_S) -> Check:
    """`GET {url}` must answer 200; used against a provider's `{base_url}/models`."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as error:
        return Check(False, f"HTTP {error.code} from {url}")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return Check(False, f"cannot reach {url}: {error}")
    return Check(True, f"ok ({url})")


def check_metadata_store(path: Path) -> Check:
    """The store opens read-only and its `records` table answers."""
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            (count,) = db.execute("SELECT COUNT(*) FROM records").fetchone()
        finally:
            db.close()
    except sqlite3.Error as error:
        return Check(False, f"metadata store unavailable: {error}")
    return Check(True, f"ok ({count} records)")


def check_embedding_index(index_dir: Path) -> Check:
    """The index loads: files exist, parse, and the vectors reach a FAISS index."""
    from refdesk.embeddings import EmbeddingIndex  # deferred: imports faiss

    try:
        index = EmbeddingIndex.load(index_dir)
    except Exception as error:  # noqa: BLE001 - anything unreadable means "unavailable"
        return Check(False, f"embedding index unavailable: {type(error).__name__}: {error}")
    model = index.manifest.get("model_id", "unknown model")
    return Check(True, f"ok ({len(index.ids)} vectors, {model})")


def check_model_backend(
    config: ProvidersConfig,
    tiers: Sequence[str],
    env: Mapping[str, str],
    probe: Callable[[str], Check] = probe_models,
) -> Check:
    """Every named tier must be callable; the first unavailable one fails the check."""
    details = []
    for tier in tiers:
        result = _check_tier(config, tier, env, probe)
        if not result.ok:
            return result
        details.append(result.detail)
    if not details:
        return Check(True, "ok (no tiers configured)")
    return Check(True, "; ".join(details))


def _check_tier(
    config: ProvidersConfig, tier: str, env: Mapping[str, str], probe: Callable[[str], Check]
) -> Check:
    if tier not in config.tiers:
        return Check(False, f"model backend unavailable: tier {tier!r} is not in providers config")
    declared = config.tiers[tier]
    provider = config.provider_of(tier)
    if not declared.model:
        return Check(False, f"model backend unavailable: tier {tier!r} has no model")
    if provider.paid:
        # No probe: that would be a paid call. The client refuses an unpriced tier or a
        # missing key before every call, so those are exactly "unavailable" here too.
        price = declared.price_usd_per_mtok
        if price.input is None or price.output is None:
            return Check(False, f"model backend unavailable: tier {tier!r} has no price")
        if not env.get(provider.key_env or ""):
            return Check(False, f"model backend unavailable: {provider.key_env} is not set")
        return Check(True, f"ok ({tier} configured; paid, not probed)")
    base = provider.base_url or env.get(provider.base_url_env or "")
    if not base:
        return Check(False, f"model backend unavailable: {provider.base_url_env} is not set")
    result = probe(base.rstrip("/") + "/models")
    if not result.ok:
        return Check(False, f"model backend unavailable: tier {tier!r}: {result.detail}")
    return Check(True, f"ok ({tier} at {base})")


def report(
    *,
    store_path: Path,
    retriever_name: str,
    reasoner: Reasoner | None,
    index_dir: Path,
    env: Mapping[str, str] | None = None,
    probe: Callable[[str], Check] = probe_models,
) -> Readiness:
    """One check per dependency; `ready` only when all three pass."""
    from refdesk.retrieval.registry import NEEDS_INDEX

    env = os.environ if env is None else env
    checks = {"metadata_store": check_metadata_store(store_path)}
    if retriever_name in NEEDS_INDEX:
        checks["embedding_index"] = check_embedding_index(index_dir)
    else:
        checks["embedding_index"] = Check(True, f"not required (retriever: {retriever_name})")
    if reasoner is None:
        checks["model_backend"] = Check(True, "not required (retrieval-only boards)")
    else:
        tiers = [reasoner.generator_tier]
        judge = reasoner.judge_tier()
        if judge is not None:
            tiers.append(judge)
        checks["model_backend"] = check_model_backend(reasoner.config, tiers, env, probe)
    return Readiness(
        ready=all(check.ok for check in checks.values()),
        checks={name: check.detail for name, check in checks.items()},
    )
