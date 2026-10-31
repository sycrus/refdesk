"""Provider-agnostic LLM client (issue #38; PRD 10, FR-11; ADR-020, ADR-021).

All providers speak the OpenAI-style `POST <base>/chat/completions` (GLM, DeepSeek,
Ollama, and the mock server). Before any request the client checks, in order:

1. keep_local: a keep-local brief never reaches a cloud provider (FR-11).
2. the tier has a model, and (for paid providers) a price, so the call can be costed;
3. paid only: an API key, a budget for this job, explicit approval (`--approve`), and
   that the worst-case cost of this call fits in what is left of the budget.

Every failure is a hard error. Nothing falls back silently to the mock or to another
provider. The model the provider reports is recorded on every completion, because some
providers serve a newer model behind the same name (docs/data-sources.md, DeepSeek).
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol

from refdesk.llm.config import Budgets, ProvidersConfig

RETRY_STATUSES = {429, 500, 502, 503, 504}


class LLMPolicyError(Exception):
    """A guard refused the call before any request was made."""


class KeepLocalViolation(LLMPolicyError):
    pass


class MissingModel(LLMPolicyError):
    pass


class MissingPrice(LLMPolicyError):
    pass


class MissingKey(LLMPolicyError):
    pass


class MissingBudget(LLMPolicyError):
    pass


class NotApproved(LLMPolicyError):
    pass


class BudgetExceeded(LLMPolicyError):
    pass


class NoValidJudge(LLMPolicyError):
    pass


class ProviderError(Exception):
    """The provider failed (error status, timeout, unreachable). Raised as-is after any
    retries against the same provider; never replaced by a call to another provider."""


class ProviderTimeout(ProviderError):
    pass


class EmptyCompletion(ProviderError):
    """The provider answered 200 with no text, e.g. a thinking model that spent every
    output token on reasoning. Never passed on as an empty rationale."""


class Transport(Protocol):
    def post_json(
        self, url: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> tuple[int, Any]: ...


class UrllibTransport:
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def post_json(self, url, headers, payload):
        data = json.dumps(payload).encode()
        request = urllib.request.Request(
            url, data=data, method="POST", headers={"Content-Type": "application/json", **headers}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")
        except TimeoutError as error:
            raise ProviderTimeout(f"timeout after {self.timeout}s: {url}") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise ProviderTimeout(f"timeout after {self.timeout}s: {url}") from error
            raise ProviderError(f"cannot reach {url}: {error.reason}") from error


@dataclass(frozen=True)
class Estimate:
    tokens_in: int
    tokens_out_max: int
    cost_usd: float


@dataclass(frozen=True)
class Completion:
    text: str
    tier: str
    provider: str
    family: str
    model_requested: str
    model_reported: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_s: float
    attempts: int = 1


@dataclass(frozen=True)
class CallObservation:
    """One request attempt as the transport answered it: what the run log records so a
    run can be replayed (issue #156). `status` is None for a timeout. `completion` is set
    only on the attempt that succeeded, so its cost is counted once."""

    tier: str
    url: str
    payload: dict[str, Any]
    status: int | None
    body: Any
    latency_s: float
    completion: Completion | None = None


def _approx_tokens(messages: list[dict[str, str]]) -> int:
    # A deliberately simple estimate (about 4 characters per token), used only to check
    # the budget before a call. The real cost uses the provider's reported usage.
    return math.ceil(sum(len(m.get("content", "")) for m in messages) / 4)


class LLMClient:
    def __init__(
        self,
        config: ProvidersConfig,
        budgets: Budgets,
        *,
        env: Mapping[str, str] | None = None,
        approved: bool = False,
        transport: Transport | None = None,
        max_retries: int = 2,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        observe: Callable[[CallObservation], None] | None = None,
    ):
        self.config = config
        # Told about every request attempt and its raw answer (the run log, issue #156).
        self.observe = observe or (lambda observation: None)
        self.budgets = budgets
        self.env = os.environ if env is None else env
        self.approved = approved
        self.transport = transport or UrllibTransport()
        self.max_retries = max_retries  # same provider only; 429, 5xx and timeouts
        self.backoff = backoff
        self._sleep = sleep
        self.spent: dict[str, float] = defaultdict(float)  # USD per job, this session

    def _price(self, tier: str, tokens_in: int, tokens_out: int) -> float:
        if not self.config.provider_of(tier).paid:
            return 0.0
        price = self.config.tiers[tier].price_usd_per_mtok
        if price.input is None or price.output is None:
            raise MissingPrice(f"tier {tier} has no price in config/providers.yaml")
        return (tokens_in * price.input + tokens_out * price.output) / 1_000_000

    def estimate(self, tier: str, messages: list[dict[str, str]], *, max_tokens: int) -> Estimate:
        """Worst-case cost of one call, for dry runs. Makes no request."""
        tokens_in = _approx_tokens(messages)
        return Estimate(tokens_in, max_tokens, self._price(tier, tokens_in, max_tokens))

    def _check(self, tier: str, estimate: Estimate, *, job: str, keep_local: bool) -> str | None:
        provider = self.config.provider_of(tier)
        if keep_local and provider.cloud:
            raise KeepLocalViolation(f"brief is keep-local; tier {tier} is a cloud provider")
        if not self.config.tiers[tier].model:
            raise MissingModel(f"tier {tier} has no model in config/providers.yaml")
        if not provider.paid:
            return None
        key = self.env.get(provider.key_env or "")
        if not key:
            raise MissingKey(f"{provider.key_env} is not set (.env)")
        budget = self.budgets.for_job(job)
        if budget is None:
            raise MissingBudget(f"no {job}_budget_usd in config/budgets.yaml")
        if not self.approved:
            raise NotApproved("paid call without --approve; run the dry-run estimate first")
        if self.spent[job] + estimate.cost_usd > budget:
            raise BudgetExceeded(
                f"{job}: spent {self.spent[job]:.4f} + estimate {estimate.cost_usd:.4f} "
                f"> budget {budget:.4f} USD"
            )
        return key

    def _base_url(self, tier: str) -> str:
        provider = self.config.provider_of(tier)
        base = provider.base_url or self.env.get(provider.base_url_env or "")
        if not base:
            raise LLMPolicyError(f"{provider.base_url_env} is not set (.env)")
        return base.rstrip("/")

    def complete(
        self,
        tier: str,
        messages: list[dict[str, str]],
        *,
        job: str,
        keep_local: bool,
        max_tokens: int = 512,
        temperature: float | None = None,
    ) -> Completion:
        estimate = self.estimate(tier, messages, max_tokens=max_tokens)
        key = self._check(tier, estimate, job=job, keep_local=keep_local)
        model = self.config.tiers[tier].model
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            payload["temperature"] = temperature
        if self.config.tiers[tier].reasoning_effort is not None:
            payload["reasoning_effort"] = self.config.tiers[tier].reasoning_effort
        url = f"{self._base_url(tier)}/chat/completions"
        start = time.perf_counter()
        for attempt in range(1, self.max_retries + 2):
            sent = time.perf_counter()
            try:
                status, body = self.transport.post_json(url, headers, payload)
            except ProviderTimeout:
                self.observe(
                    CallObservation(tier, url, payload, None, None, time.perf_counter() - sent)
                )
                if attempt > self.max_retries:
                    raise
                self._sleep(self.backoff * 2 ** (attempt - 1))
                continue
            observation = CallObservation(
                tier, url, payload, status, body, time.perf_counter() - sent
            )
            if status == 200:
                break
            self.observe(observation)
            if status is not None and (status not in RETRY_STATUSES or attempt > self.max_retries):
                raise ProviderError(f"{tier}: HTTP {status}: {str(body)[:200]}")
            self._sleep(self.backoff * 2 ** (attempt - 1))
        latency = time.perf_counter() - start
        message = body["choices"][0]["message"]
        if not (message.get("content") or "").strip():
            self.observe(observation)
            where = "reasoning" if message.get("reasoning") else "nothing"
            raise EmptyCompletion(
                f"{tier}: empty answer; output tokens went to {where}. "
                "Use a non-thinking model or raise max_tokens."
            )
        usage = body.get("usage") or {}
        tokens_in = int(usage.get("prompt_tokens", estimate.tokens_in))
        tokens_out = int(usage.get("completion_tokens", 0))
        cost = self._price(tier, tokens_in, tokens_out)
        self.spent[job] += cost
        provider = self.config.provider_of(tier)
        completion = Completion(
            text=message["content"],
            tier=tier,
            provider=self.config.tiers[tier].provider,
            family=provider.family,
            model_requested=model,
            model_reported=body.get("model"),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            latency_s=latency,
            attempts=attempt,
        )
        self.observe(replace(observation, completion=completion))
        return completion


def pick_judge(config: ProvidersConfig, *, generator_tier: str, candidates: list[str]) -> str:
    """The first candidate tier whose family differs from the generator's (ADR-021).

    Candidates must also be callable (have a model and, if paid, a price)."""
    generator_family = config.provider_of(generator_tier).family
    for tier in candidates:
        t, provider = config.tiers[tier], config.provider_of(tier)
        priced = not provider.paid or (
            t.price_usd_per_mtok.input is not None and t.price_usd_per_mtok.output is not None
        )
        if provider.family != generator_family and t.model and priced:
            return tier
    raise NoValidJudge(f"no callable judge outside family {generator_family!r} in {candidates}")
