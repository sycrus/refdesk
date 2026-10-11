"""ModelManager: one GPU model at a time, VRAM checked before loading (issue #40)."""

import pytest

from refdesk.llm.model_manager import InsufficientVRAM, ModelManager, ModelSpec


class FakeBackend:
    def __init__(self, name, log):
        self.name, self.log = name, log
        self.loaded: set[str] = set()

    def loaded_models(self):
        return set(self.loaded)

    def load(self, model):
        self.log.append(("load", self.name, model))
        self.loaded.add(model)

    def unload(self, model):
        self.log.append(("unload", self.name, model))
        self.loaded.discard(model)


class FakeVRAM:
    def __init__(self, free_mib):
        self.free_mib = free_mib

    def __call__(self):
        return self.free_mib


SPECS = {
    "qwen-small": ModelSpec("qwen-small", backend="ollama", vram_mib=3_000),
    "kev-4b": ModelSpec("kev-4b", backend="kev", vram_mib=9_000),
}


def manager(free_mib=14_000):
    log, events = [], []
    backends = {"ollama": FakeBackend("ollama", log), "kev": FakeBackend("kev", log)}
    m = ModelManager(SPECS, backends, free_vram_mib=FakeVRAM(free_mib), on_event=events.append)
    return m, backends, log, events


def test_loads_a_model_when_nothing_is_loaded():
    m, backends, log, _ = manager()
    m.ensure("qwen-small")
    assert log == [("load", "ollama", "qwen-small")]


def test_unloads_every_other_model_before_loading():
    m, backends, log, _ = manager()
    m.ensure("qwen-small")
    m.ensure("kev-4b")
    assert log == [
        ("load", "ollama", "qwen-small"),
        ("unload", "ollama", "qwen-small"),
        ("load", "kev", "kev-4b"),
    ]
    assert backends["ollama"].loaded == set() and backends["kev"].loaded == {"kev-4b"}


def test_ensure_is_a_no_op_when_the_model_is_already_the_only_one_loaded():
    m, _, log, _ = manager()
    m.ensure("kev-4b")
    m.ensure("kev-4b")
    assert log == [("load", "kev", "kev-4b")]


def test_refuses_to_load_without_enough_free_vram():
    m, _, log, _ = manager(free_mib=5_000)
    with pytest.raises(InsufficientVRAM, match="kev-4b"):
        m.ensure("kev-4b")
    assert ("load", "kev", "kev-4b") not in log


def test_vram_is_checked_after_unloading_the_others():
    # Other models are unloaded first, then free VRAM is measured.
    m, _, log, _ = manager()
    m.ensure("qwen-small")
    m.vram = FakeVRAM(2_000)
    with pytest.raises(InsufficientVRAM):
        m.ensure("kev-4b")
    assert log[-1] == ("unload", "ollama", "qwen-small")


def test_load_time_is_logged_as_an_event():
    m, _, _, events = manager()
    m.ensure("qwen-small")
    [event] = events
    assert event["event"] == "model_loaded" and event["model"] == "qwen-small"
    assert event["load_s"] >= 0 and event["free_vram_mib_before"] == 14_000


def test_unknown_model_is_an_error():
    m, *_ = manager()
    with pytest.raises(KeyError):
        m.ensure("gpt-9")


def test_models_loaded_outside_the_manager_are_unloaded_too():
    m, backends, log, _ = manager()
    backends["ollama"].loaded.add("someone-elses-model")
    m.ensure("kev-4b")
    assert ("unload", "ollama", "someone-elses-model") in log


def test_repository_specs_use_measured_vram_and_leave_out_unmeasured_models():
    from refdesk.llm.model_manager import load_specs

    specs = load_specs("config/models.yaml")
    assert specs["qwen3:4b"].vram_mib == 7600
    assert "kev-4b" not in specs  # not measured yet, so the manager will not load it
