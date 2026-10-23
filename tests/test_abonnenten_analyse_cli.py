"""Headless resume lifetime and scheduling, with no source or model calls."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse as analyse


@pytest.fixture
def cli(monkeypatch):
    state = {"id": "existing", "status": "laeuft", "detail": "synthetic"}
    calls = {"resume": [], "stop": [], "create": []}
    class Storage:
        def read(self, run_id):
            assert run_id == "existing"
            return dict(state)
    monkeypatch.setattr(analyse, "Store", Storage)
    monkeypatch.setattr(analyse, "fortsetzen", lambda run_id: calls["resume"].append(run_id) or True)
    monkeypatch.setattr(analyse, "starten", lambda *args, **kwargs: calls["create"].append(args))
    monkeypatch.setattr(analyse, "stoppen", lambda run_id: calls["stop"].append(run_id))
    monkeypatch.setattr(analyse.scan_worker, "active_run", lambda: None)
    return state, calls


def test_cli_without_explicit_resume_cannot_launch_or_create(cli):
    state, calls = cli
    with pytest.raises(SystemExit) as exc:
        analyse.main([])
    assert exc.value.code == 2
    assert calls == {"resume": [], "stop": [], "create": []}


def test_cli_help_cannot_launch_or_create(cli):
    state, calls = cli
    with pytest.raises(SystemExit) as exc:
        analyse.main(["--help"])
    assert exc.value.code == 0
    assert calls == {"resume": [], "stop": [], "create": []}


@pytest.mark.parametrize("status,expected", [
    ("abgeschlossen", 0), ("teilweise", 2), ("wartet_budget", 2),
    ("fehlgeschlagen", 2), ("laeuft", 2), ("angehalten", 130),
])
def test_cli_reads_terminal_status_even_if_worker_finished_before_lookup(cli, status, expected):
    state, calls = cli
    state["status"] = status
    assert analyse.main(["--resume", "existing"]) == expected
    assert calls["resume"] == ["existing"]
    assert calls["create"] == []


def test_cli_waits_for_its_real_daemon_thread(monkeypatch, cli):
    state, calls = cli
    finished = threading.Event()
    def work():
        assert finished.wait(2)
        state["status"] = "abgeschlossen"
    thread = threading.Thread(target=work, daemon=True)
    worker = SimpleNamespace(workflow={"abonnenten_id": "existing"}, thread=thread)
    def resume(run_id):
        calls["resume"].append(run_id)
        thread.start()
        return True
    monkeypatch.setattr(analyse, "fortsetzen", resume)
    monkeypatch.setattr(analyse.scan_worker, "active_run", lambda: worker)
    timer = threading.Timer(.05, finished.set)
    timer.start()
    try:
        assert analyse.main(["--resume", "existing"]) == 0
        assert not thread.is_alive()
    finally:
        finished.set()
        timer.join()
        thread.join(timeout=2)


def test_cli_interruption_requests_stop_and_still_waits_for_cleanup(monkeypatch, cli):
    state, calls = cli
    class Thread:
        joins = 0
        def is_alive(self):
            return self.joins < 2
        def join(self, timeout):
            assert timeout == 1
            self.joins += 1
            if self.joins == 1:
                raise KeyboardInterrupt
            assert calls["stop"] == ["existing"]
            state["status"] = "angehalten"
            state["detail"] = "cleanup complete"
    thread = Thread()
    monkeypatch.setattr(analyse.scan_worker, "active_run", lambda: SimpleNamespace(
        workflow={"abonnenten_id": "existing"}, thread=thread))
    assert analyse.main(["--resume", "existing"]) == 130
    assert thread.joins == 2
    assert state["detail"] == "cleanup complete"


def test_cli_does_not_take_over_running_or_unrelated_worker(monkeypatch, cli):
    state, calls = cli
    monkeypatch.setattr(analyse, "fortsetzen", lambda _: False)
    assert analyse.main(["--resume", "existing"]) == 3
    monkeypatch.setattr(analyse, "fortsetzen", lambda _: True)
    monkeypatch.setattr(analyse.scan_worker, "active_run", lambda: SimpleNamespace(
        workflow={"abonnenten_id": "other"}, thread=None))
    assert analyse.main(["--resume", "existing"]) == 1


def test_cli_reports_unknown_run_without_starting_new_one(monkeypatch, cli):
    state, calls = cli
    def fail(_):
        raise ValueError("Unbekannter Bewertungslauf")
    monkeypatch.setattr(analyse, "fortsetzen", fail)
    assert analyse.main(["--resume", "missing"]) == 1
    assert calls["create"] == []


def test_cli_cp1252_output_cannot_kill_process_on_provider_emoji(monkeypatch, cli):
    import io
    import sys
    state, calls = cli
    state.update(status="abgeschlossen", detail="Provider \U0001f600 \u4e2d\u6587")
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    assert analyse.main(["--resume", "existing"]) == 0
    stream.flush()
    assert b"\\U0001f600" in raw.getvalue()
    assert b"\\u4e2d\\u6587" in raw.getvalue()


def test_cli_missing_key_preserves_data_and_reports_partial_without_model_call(monkeypatch):
    from mqlkiscanner import abonnenten_analyse_daten as data_module, config
    from mqlkiscanner.abonnenten_analyse_store import Store
    store = Store()
    store.create({"id": "no-key", "status": "geplant", "quellen": ["mql5"],
                  "retdd_gewicht": 70, "dd_grenze": None,
                  "snapshot_quellen": {"mql5": {"status": "fertig"}}, "logs": []})
    store.save_task("no-key", {"signal_ref": 1, "id": 8, "name": "Synthetic", "quelle": "mql5",
                               "abonnenten": 1, "abo_perzentil": 50})
    class Data:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def berechne(self, entry, should_stop):
            return {"data_complete": True, "eligible": True, "retdd_jahr": 3,
                    "trades_path": "fixture", "trades_sha256": "synthetic",
                    "trades": 50, "dauer_monate": 2.5, "forensik": {"forensics": {}}}
    class AI:
        def __init__(self, *args, **kwargs): self.client = SimpleNamespace(has_key=False)
        def analyse(self, *args, **kwargs): pytest.fail("No paid call without configured key")
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    monkeypatch.setattr(analyse, "_snapshot", lambda *args: None)
    def resume(run_id):
        analyse._execute(store, run_id, config.load_settings())
        return True
    monkeypatch.setattr(analyse, "fortsetzen", resume)
    monkeypatch.setattr(analyse.scan_worker, "active_run", lambda: None)
    assert analyse.main(["--resume", "no-key"]) == 2
    assert store.tasks("no-key")[0]["data_done"] is True
    assert store.read("no-key")["status"] == "teilweise"
    assert "Kein GLM-Key" in store.read("no-key")["fehler"]


def test_work_order_preserves_membership_and_prioritizes_source_then_subscribers():
    entries = [
        dict(quelle="zulu", abonnenten=9000, id=9, signal_ref=1),
        dict(quelle="mql5", abonnenten=10, id=4, signal_ref=80),
        dict(quelle="pelik", abonnenten=40, id=3, signal_ref=2),
        dict(quelle="mql5", abonnenten=30, id=8, signal_ref=90),
        dict(quelle="mql5", abonnenten=30, id=2, signal_ref=99),
        dict(quelle="mql5", abonnenten=None, id=1, signal_ref=10),
    ]
    ordered = analyse._arbeitsreihenfolge(entries, ["mql5", "pelik", "robo", "vant", "zulu"])
    assert [row["id"] for row in ordered] == [2, 8, 4, 1, 3, 9]
    assert {id(row) for row in ordered} == {id(row) for row in entries}
    assert [row["id"] for row in entries] == [9, 4, 3, 8, 2, 1]
