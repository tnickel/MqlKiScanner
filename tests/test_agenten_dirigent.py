# -*- coding: utf-8 -*-
"""Dirigent-Tageslauf (Phase A): Lagestatus, Code-Plan, optionale
LLM-Entscheidung mit Whitelist, Lock-Respekt — alles protokolliert.

In der isolierten Test-Umgebung existiert kein GLM-Key: Der LLM-Pfad wird
als 'skipped' protokolliert, der Lauf bleibt 'ok' — genau das
Fehlverhalten-Fallback, das der Betrieb ohne Key zeigen soll.
"""
import json

from mqlkiscanner import config
from mqlkiscanner.agenten import dirigent, journal, lock


def test_tageslauf_ohne_key_vollstaendig_protokolliert():
    ergebnis = dirigent.tageslauf(quelle="test", log=lambda *_: None)
    assert ergebnis["status"] == "ok"

    lauf = journal.list_laeufe()[0]
    assert lauf["status"] == "ok"
    assert "Phase-A-Tageslauf" in lauf["zusammenfassung"]

    schritte = journal.list_schritte(limit=50)
    namen = [s["schritt"] for s in schritte]
    assert "lock" in namen and "lagestatus" in namen and "tagesplan" in namen
    # Ohne Key: LLM-Entscheidung übersprungen und BEGRÜNDET protokolliert.
    llm = next(s for s in schritte if s["schritt"] == "llm_entscheidung")
    assert llm["status"] == "skipped"
    detail = journal.schritt_lesen(llm["id"])
    assert "GLM-Key" in detail["detail"]["grund"]


def test_lagestatus_enthelt_budget_und_kalender():
    ergebnis = dirigent.tageslauf(quelle="test", log=lambda *_: None)
    lage = ergebnis["lage"]
    assert lage["tagesbudget_tokens"] == 500_000
    assert lage["monatsbudget_tokens"] == 5_000_000
    assert isinstance(lage["wochenende"], bool)
    assert "rollen_aktiv" in lage and "dirigent" in lage["rollen_aktiv"]


def test_wochenende_plant_ruhen(monkeypatch):
    import datetime as _dt

    class _Samstag(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 26, 7, 0)  # Samstag

    monkeypatch.setattr(dirigent, "datetime", _Samstag)
    ergebnis = dirigent.tageslauf(quelle="test", log=lambda *_: None)
    assert ergebnis["plan"] == ["ruhen_markt_geschlossen"]


def test_budget_erschopft_plant_pause():
    config.save_settings({**config.load_settings(),
                          "agenten_tagesbudget_tokens": 10_000})
    # Ein LLM-freier Lauf verbraucht nichts — Budget künstlich belegen:
    lauf = journal.lauf_starten("dirigent", quelle="test")
    journal.schritt_protokollieren(lauf, "dirigent", "llm_entscheidung",
                                   prompt="p", antwort="a", tokens=50_000)
    ergebnis = dirigent.tageslauf(quelle="test", log=lambda *_: None)
    assert ergebnis["plan"] == ["budget_pause"]


def test_lock_belegt_lauf_wird_uebersprungen():
    with lock.lauf_lock(config.DATA_DIR, "agenten_lauff"):
        ergebnis = dirigent.tageslauf(quelle="test", log=lambda *_: None)
    assert ergebnis["status"] == "skipped"
    lauf = journal.list_laeufe()[0]
    assert lauf["status"] == "skipped"
    assert "Lauf-Lock" in lauf["zusammenfassung"]


def test_whitelist_filter_laesst_nur_bekannte_aktionen_durch():
    antwort = json.dumps({"aktionen": ["scan_full", "boese_aktion",
                                       "markt_holen"],
                          "begruendung": "Test"})
    gefiltert = dirigent._whitelist_filter(antwort)
    assert gefiltert["aktionen"] == ["scan_full", "markt_holen"]


def test_whitelist_filter_ohne_json():
    gefiltert = dirigent._whitelist_filter("Ich lehne ab.")
    assert gefiltert["aktionen"] == []
    assert "verworfen" in gefiltert["begruendung"]
