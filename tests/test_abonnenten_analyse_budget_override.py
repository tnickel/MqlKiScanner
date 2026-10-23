"""Per-run token budgets reach the worker without changing global settings."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, config
from mqlkiscanner.abonnenten_analyse_store import Store


APPROVED = {"llm_max_total_tokens": 50_000_000,
            "agenten_tagesbudget_tokens": 50_000_000,
            "agenten_monatsbudget_tokens": 60_000_000}


@pytest.fixture
def launch(monkeypatch):
    global_settings = {"llm_max_total_tokens": 10_000_000,
                       "agenten_tagesbudget_tokens": 10_000_000,
                       "agenten_monatsbudget_tokens": 10_000_000,
                       "model_stufe1": "original-model", "glm_base_url": "original-endpoint"}
    config.SETTINGS_FILE.write_text('{"global":"unchanged"}', encoding="utf-8")
    original_bytes = config.SETTINGS_FILE.read_bytes()
    captured = {"starts": [], "execute": []}
    # Return the same dict: the merge must not mutate even an aliased object.
    monkeypatch.setattr(config, "load_settings", lambda: global_settings)
    monkeypatch.setattr(config, "save_settings", lambda *a, **k: pytest.fail("No global settings write"))
    def execute(store, run_id, settings):
        captured["execute"].append((run_id, copy.deepcopy(settings)))
    def start(target, **kwargs):
        captured["starts"].append(kwargs)
        target()
        return SimpleNamespace()
    monkeypatch.setattr(analyse, "_execute", execute)
    monkeypatch.setattr(analyse.scan_worker, "start", start)
    return Store(), global_settings, original_bytes, captured


def test_run_budget_is_last_priority_and_only_reaches_its_worker(launch):
    store, globals_, original_bytes, captured = launch
    before = copy.deepcopy(globals_)
    store.create({"id": "approved", "budget_settings": APPROVED})
    start_settings = {"llm_max_total_tokens": 15_000_000, "model_stufe1": "explicit-model"}
    analyse._launch("approved", start_settings)
    run_id, worker_settings = captured["execute"][0]
    assert run_id == "approved"
    assert {key: worker_settings[key] for key in APPROVED} == APPROVED
    assert worker_settings["model_stufe1"] == "explicit-model"
    assert worker_settings["glm_base_url"] == "original-endpoint"
    assert globals_ == before
    assert start_settings == {"llm_max_total_tokens": 15_000_000, "model_stufe1": "explicit-model"}
    assert config.SETTINGS_FILE.read_bytes() == original_bytes
    assert captured["starts"][0]["workflow"] == {"abonnenten_id": "approved"}


@pytest.mark.parametrize("overrides", [None, {}])
def test_no_override_preserves_defaults_or_explicit_start_settings(launch, overrides):
    store, globals_, original_bytes, captured = launch
    run = {"id": "default"}
    if overrides is not None:
        run["budget_settings"] = overrides
    store.create(run)
    analyse._launch("default", {"llm_max_total_tokens": 12_000_000})
    settings = captured["execute"][0][1]
    assert settings["llm_max_total_tokens"] == 12_000_000
    assert settings["agenten_tagesbudget_tokens"] == globals_["agenten_tagesbudget_tokens"]
    assert settings["agenten_monatsbudget_tokens"] == globals_["agenten_monatsbudget_tokens"]
    assert config.SETTINGS_FILE.read_bytes() == original_bytes


def test_override_does_not_leak_to_another_run(launch):
    store, globals_, original_bytes, captured = launch
    store.create({"id": "approved", "budget_settings": APPROVED})
    store.create({"id": "normal"})
    analyse._launch("approved")
    analyse._launch("normal")
    assert captured["execute"][0][1]["llm_max_total_tokens"] == 50_000_000
    assert captured["execute"][1][1]["llm_max_total_tokens"] == 10_000_000


@pytest.mark.parametrize("invalid", [None, [], "50000000", 50_000_000, False])
def test_invalid_override_object_stops_before_worker(launch, invalid):
    store, globals_, original_bytes, captured = launch
    store.create({"id": "invalid", "budget_settings": invalid})
    with pytest.raises(ValueError, match="Objekt"):
        analyse._launch("invalid")
    assert captured == {"starts": [], "execute": []}
    assert config.SETTINGS_FILE.read_bytes() == original_bytes


@pytest.mark.parametrize("key", sorted(APPROVED))
@pytest.mark.parametrize("invalid", [0, -1, True, False, "50000000", 50_000_000.0, None, [], {}])
def test_invalid_allowed_budget_value_stops_before_worker(launch, key, invalid):
    store, globals_, original_bytes, captured = launch
    store.create({"id": "invalid", "budget_settings": {key: invalid}})
    with pytest.raises(ValueError, match=key):
        analyse._launch("invalid")
    assert captured == {"starts": [], "execute": []}


def test_foreign_fields_cannot_change_endpoint_models_or_evaluation(launch):
    store, globals_, original_bytes, captured = launch
    store.create({"id": "scoped", "budget_settings": {
        **APPROVED, "glm_base_url": "foreign-endpoint", "model_stufe1": "foreign-model",
        "dd_grenze": 99, "markt_start_erlauben": True, "unrecognized": None}})
    analyse._launch("scoped")
    settings = captured["execute"][0][1]
    assert settings["glm_base_url"] == "original-endpoint"
    assert settings["model_stufe1"] == "original-model"
    assert "dd_grenze" not in settings and "markt_start_erlauben" not in settings
    assert "unrecognized" not in settings
    assert {key: settings[key] for key in APPROVED} == APPROVED


def test_missing_run_cannot_start_worker(launch):
    store, globals_, original_bytes, captured = launch
    with pytest.raises(ValueError, match="Unbekannter"):
        analyse._launch("missing")
    assert captured == {"starts": [], "execute": []}
