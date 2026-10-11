"""ModelManager: one GPU-heavy model at a time (issue #40; CLAUDE.md; PRD 10).

`ensure(model)` makes `model` the only model on the GPU:
1. unload every other model on every backend, including ones loaded outside refdesk;
2. measure free VRAM and refuse (InsufficientVRAM) if it is below the model's stated need;
3. load the model and emit a `model_loaded` event with the load time.

Why: on a 16 GB card a local generation model and Kev-4B do not fit together. Swapping
blindly would fail mid-run, or thrash. The load time is logged so latency reports can show
the cost of swapping instead of hiding it inside "generation time".

Backends: Ollama (load with a 1-token request, unload with keep_alive=0, list via
/api/ps) and Kev (scripts/kev.ps1 serve/stop). Both sit behind a small interface so the
swap logic is unit-tested with fakes.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class InsufficientVRAM(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    backend: str
    vram_mib: int  # stated need; set from the first measured run, not guessed (CLAUDE.md)


class Backend(Protocol):
    def loaded_models(self) -> set[str]: ...

    def load(self, model: str) -> None: ...

    def unload(self, model: str) -> None: ...


def nvidia_free_vram_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return int(out.splitlines()[0].strip())


class ModelManager:
    def __init__(
        self,
        specs: dict[str, ModelSpec],
        backends: dict[str, Backend],
        *,
        free_vram_mib: Callable[[], int] = nvidia_free_vram_mib,
        on_event: Callable[[dict[str, Any]], None] = lambda event: None,
    ):
        self.specs = specs
        self.backends = backends
        self.vram = free_vram_mib
        self.on_event = on_event

    def ensure(self, model: str) -> None:
        spec = self.specs[model]  # KeyError for an unknown model
        target = self.backends[spec.backend]
        for name, backend in self.backends.items():
            for loaded in sorted(backend.loaded_models()):
                if not (name == spec.backend and loaded == model):
                    backend.unload(loaded)
        if model in target.loaded_models():
            return
        free = self.vram()
        if free < spec.vram_mib:
            raise InsufficientVRAM(
                f"{model} needs {spec.vram_mib} MiB, only {free} MiB free. "
                "Close other GPU programs (one GPU job at a time)."
            )
        started = time.perf_counter()
        target.load(model)
        self.on_event({
            "event": "model_loaded", "model": model, "backend": spec.backend,
            "load_s": round(time.perf_counter() - started, 3), "free_vram_mib_before": free,
        })  # fmt: skip


class OllamaBackend:
    """Ollama's native API: /api/ps lists loaded models; keep_alive controls residency."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> None:
        request = urllib.request.Request(
            self.base_url + path, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"},
        )  # fmt: skip
        urllib.request.urlopen(request, timeout=self.timeout).close()

    def loaded_models(self) -> set[str]:
        with urllib.request.urlopen(self.base_url + "/api/ps", timeout=10) as response:
            return {m["name"] for m in json.load(response).get("models", [])}

    def load(self, model: str) -> None:
        # An empty generate request loads the model and keeps it resident.
        self._post("/api/generate", {"model": model, "keep_alive": "30m"})

    def unload(self, model: str) -> None:
        self._post("/api/generate", {"model": model, "keep_alive": 0})


class KevBackend:
    """Kev runs in WSL2 behind scripts/kev.ps1 (allow-listed; raw wsl is not)."""

    def __init__(self, port: int = 8009):
        self.port = port

    def _kev(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", "scripts/kev.ps1", *args],
            capture_output=True, text=True,
        )  # fmt: skip

    def loaded_models(self) -> set[str]:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=3).close()
            return {"kev-4b"}
        except OSError:
            return set()

    def load(self, model: str) -> None:
        result = self._kev("serve")
        if result.returncode != 0:
            raise RuntimeError(f"kev.ps1 serve failed: {result.stdout} {result.stderr}")

    def unload(self, model: str) -> None:
        self._kev("stop")


def load_specs(path: str = "config/models.yaml") -> dict[str, ModelSpec]:
    """Model specs with measured VRAM needs. A model with no measurement is refused."""
    import yaml

    with open(path, encoding="utf-8") as f:
        models = yaml.safe_load(f)["models"]
    # Unmeasured models are left out, so ensure() on them fails with a KeyError.
    return {
        name: ModelSpec(name, m["backend"], m["vram_mib"])
        for name, m in models.items()
        if m.get("vram_mib") is not None
    }
