"""Provider, tier and budget configuration (config/providers.yaml, config/budgets.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provider(_Model):
    family: str
    cloud: bool
    paid: bool
    base_url: str | None = None
    base_url_env: str | None = None
    key_env: str | None = None

    @model_validator(mode="after")
    def _has_a_base_url(self) -> Provider:
        if not (self.base_url or self.base_url_env):
            raise ValueError("a provider needs base_url or base_url_env")
        if self.paid and not self.key_env:
            raise ValueError("a paid provider needs key_env")
        return self


class Price(_Model):
    input: float | None = None  # USD per million tokens
    output: float | None = None


class Tier(_Model):
    provider: str
    model: str | None = None
    price_usd_per_mtok: Price = Price()


class ProvidersConfig(_Model):
    providers: dict[str, Provider]
    tiers: dict[str, Tier]
    routing: list[str]

    @model_validator(mode="after")
    def _references_exist(self) -> ProvidersConfig:
        for name, tier in self.tiers.items():
            if tier.provider not in self.providers:
                raise ValueError(f"tier {name}: unknown provider {tier.provider}")
        unknown = [t for t in self.routing if t not in self.tiers]
        if unknown:
            raise ValueError(f"routing names unknown tiers: {unknown}")
        return self

    @classmethod
    def load(cls, path: str | Path) -> ProvidersConfig:
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    def provider_of(self, tier: str) -> Provider:
        return self.providers[self.tiers[tier].provider]


class Budgets:
    """Per-job budgets in USD: `<job>_budget_usd` in config/budgets.yaml."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: str | Path) -> Budgets:
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    def for_job(self, job: str) -> float | None:
        value = self.data.get(f"{job}_budget_usd")
        return None if value is None else float(value)
