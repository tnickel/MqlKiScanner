# -*- coding: utf-8 -*-
"""Real station dialogs must keep filtering after the live-status timer ticks.

AppTest normally requests full app reruns. The small adapter below retains
Streamlit's fragment storage and requests the same fragment reruns a browser
sends, using the actual script, widget metadata and emitted render tree.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import pytest
from streamlit.runtime.scriptrunner_utils.script_requests import RerunData, ScriptRequests
from streamlit.runtime.forward_msg_queue import ForwardMsgQueue
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import parse_tree_from_messages
from streamlit.testing.v1.local_script_runner import LocalScriptRunner, require_widgets_deltas

from mqlkiscanner import config, downloader_sync, pipeline

ROOT = Path(__file__).resolve().parents[1]


class FragmentRuns:
    """Retain the browser session's fragments across AppTest runner instances."""

    def __init__(self, monkeypatch):
        self.runner = None
        self.requested_fragment = None
        self.rendered_messages = ForwardMsgQueue()
        original_run = LocalScriptRunner.run

        def run(runner, widget_state=None, query_params=None, timeout=3, page_hash=""):
            previous = self.runner
            fragment = self.requested_fragment
            self.requested_fragment = None
            self.runner = runner
            if fragment is None:
                tree = original_run(runner, widget_state, query_params, timeout, page_hash)
                self.rendered_messages = ForwardMsgQueue()
                for msg in runner.forward_msgs():
                    self.rendered_messages.enqueue(msg)
                return tree
            assert previous is not None
            # AppSession preserves these objects between browser interactions.
            runner._fragment_storage = previous._fragment_storage
            runner._pages_manager = previous._pages_manager
            # LocalScriptRunner seeds a full-app request in its constructor.
            # Otherwise request coalescing would turn our fragment into a full
            # rerun and silently invalidate this regression test.
            runner._requests = ScriptRequests()
            runner.request_rerun(RerunData(
                widget_states=widget_state,
                query_string=urlencode(query_params or {}, doseq=True),
                page_script_hash=page_hash,
                fragment_id=fragment,
            ))
            runner.start()
            require_widgets_deltas(runner, timeout)
            started = [data.get("fragment_ids_this_run")
                       for event, data in zip(runner.events, runner.event_data)
                       if event.name == "SCRIPT_STARTED"]
            assert started and all(started), "The adapter must run real fragments, never the full app"
            # Browser rendering keeps elements outside the rerunning fragment.
            # A callback can redirect the run before its original fragment emits
            # any deltas, so the server's outgoing queue alone is insufficient.
            for msg in runner.forward_msgs():
                self.rendered_messages.enqueue(msg)
            return parse_tree_from_messages(self.rendered_messages._queue)

        monkeypatch.setattr(LocalScriptRunner, "run", run)

    def widget_fragment(self, at, widget_id):
        fragment = at.session_state._state._new_widget_state.widget_metadata[widget_id].fragment_id
        assert fragment, "The widget must belong to a registered fragment"
        return fragment

    def rerun(self, at, fragment, widget_states=None):
        assert self.runner._fragment_storage.contains(fragment), \
            "The live-status rerun must not discard the open dialog's fragment"
        self.requested_fragment = fragment
        at._run(widget_states or at._tree.get_widget_states())
        assert not at.exception, at.exception


@pytest.fixture
def fragment_runs(monkeypatch):
    monkeypatch.setattr(downloader_sync, "verbindungs_status", lambda **kwargs: {
        "konfiguriert": False, "ok": False, "quellen": [],
    })
    config.save_settings({**config.load_settings(), "rest_api_enabled": False})
    return FragmentRuns(monkeypatch)


def _dialog(at):
    assert not at.exception, at.exception
    dialogs = at.get("dialog")
    assert len(dialogs) == 1
    return dialogs[0]


def _open_station_from_stepper(at, fragment_runs, station):
    """Send the real CCv2 event within the stepper's live-status fragment."""
    stepper = next(item for item in at.get("bidi_component")
                   if item.key == "scan_station_stepper")
    live_fragment = fragment_runs.widget_fragment(at, stepper.proto.id)
    states = at._tree.get_widget_states()
    state = states.widgets.add()
    state.id = stepper.proto.id
    state.json_value = "{}"
    trigger = states.widgets.add()
    trigger.id = f"$$STREAMLIT_INTERNAL_KEY_{stepper.proto.id}__events"
    trigger.json_trigger_value = json.dumps([{"event": "station", "value": station}])
    fragment_runs.rerun(at, live_fragment, states)
    _dialog(at)
    # Reproduce the timer that previously evicted the nested dialog fragment.
    stepper = next(item for item in at.get("bidi_component")
                   if item.key == "scan_station_stepper")
    fragment_runs.rerun(at, fragment_runs.widget_fragment(at, stepper.proto.id))
    _dialog(at)


def _change_filter(at, fragment_runs, kind, key, value):
    widget = next(item for item in _dialog(at).get(kind) if item.key == key)
    fragment = fragment_runs.widget_fragment(at, widget.id)
    widget.set_value(value)
    fragment_runs.rerun(at, fragment)
    tables = _dialog(at).get("dataframe")
    assert len(tables) == 1, "Filtering must replace the table within the open dialog"
    return tables[0].value


def test_station3_filtert_nach_stepper_klick_und_live_tick(fragment_runs):
    rows = [
        {"id": 1001, "name": "Gold geprüft", "quelle": "mql5",
         "status": "AUSGEWAEHLT", "grund": "Rang 1"},
        {"id": 1002, "name": "Gold offen", "quelle": "mql5",
         "status": "OHNE_SLOT", "grund": "Kein Slot"},
        {"id": 2001, "name": "Pelican geprüft", "quelle": "pelik",
         "status": "AUSGEWAEHLT", "grund": "Rang 1"},
        {"id": 2002, "name": "Pelican offen", "quelle": "pelik",
         "status": "NICHT_IM_SCOPE", "grund": "Nicht im Teilscan"},
    ]
    (config.DATA_DIR / "auswahl_begruendung.json").write_text(json.dumps({
        "zeitstempel": "2026-10-02 12:00:00", "modus": "Teilscan", "eintraege": rows,
    }), encoding="utf-8")
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.session_state["scan_results"] = [
        pipeline.ScanResult(id=1001, name="Gold geprüft", quelle="mql5",
                            forensik_vorhanden=True, ampel="🟢"),
        pipeline.ScanResult(id=2001, name="Pelican geprüft", quelle="pelik",
                            forensik_vorhanden=True, ampel="🟡"),
    ]
    at.run()
    _open_station_from_stepper(at, fragment_runs, "forensik")
    table = _dialog(at).get("dataframe")[0].value
    assert set(table["ID"]) == {1001, 1002, 2001, 2002}
    assert "_gewaehlt" not in table.columns

    table = _change_filter(at, fragment_runs, "button_group", "_flt_anzeige_forensik", "Nur geprüft")
    assert set(table["ID"]) == {1001, 2001}
    assert set(table["Geprüft"]) == {"✓ ja"}
    table = _change_filter(at, fragment_runs, "button_group", "_flt_anzeige_forensik", "Nur nicht geprüft")
    assert set(table["ID"]) == {1002, 2002}
    assert set(table["Geprüft"]) == {"— nein"}
    table = _change_filter(at, fragment_runs, "button_group", "_flt_anzeige_forensik", "Alle")
    assert set(table["ID"]) == {1001, 1002, 2001, 2002}

    table = _change_filter(at, fragment_runs, "multiselect", "_flt_quelle_forensik", ["pelik"])
    assert set(table["ID"]) == {2001, 2002}
    table = _change_filter(at, fragment_runs, "text_input", "_flt_suche_forensik", "geprüft")
    assert list(table["ID"]) == [2001]
    table = _change_filter(at, fragment_runs, "text_input", "_flt_suche_forensik", "2002")
    assert list(table["ID"]) == [2002]
    table = _change_filter(at, fragment_runs, "text_input", "_flt_suche_forensik", "kein Treffer")
    assert table.empty
    table = _change_filter(at, fragment_runs, "text_input", "_flt_suche_forensik", "")
    assert set(table["ID"]) == {2001, 2002}
    table = _change_filter(at, fragment_runs, "multiselect", "_flt_quelle_forensik", [])
    assert table.empty, "Deselecting every source must show no signals"
    table = _change_filter(at, fragment_runs, "multiselect", "_flt_quelle_forensik", ["mql5", "pelik"])
    assert set(table["ID"]) == {1001, 1002, 2001, 2002}
