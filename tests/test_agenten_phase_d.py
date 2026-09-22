# -*- coding: utf-8 -*-
"""Phase D: Melder — Alerts, Ampelwechsel-Watcher, Tagesdigest, Postfach.

Abnahme aus doc/19: Ein künstlich ausgelöster Ampelwechsel erzeugt einen
Alert mit Quellverweis — plus Stilbruch-Sofort-Alert aus dem Betreuer und
die Digest-Verschiebung, solange der Betreuer läuft.
"""
from datetime import datetime

from mqlkiscanner import config, db
from mqlkiscanner.agenten import (betreuer, dossier, journal, melder, rollen)


# ── Journal: Meldungen ─────────────────────────────────────────────

def test_meldung_roundtrip_und_filter():
    melder.alert("alert", "Testwarnung", "Details", prioritaet=2,
                 quellen=["schritt#1"])
    journal.meldung_speichern("digest", "Digest", "Zusammenfassung")
    assert journal.meldungen_zaehlen() == 2
    assert journal.meldungen_zaehlen(typ="alert") == 1
    alerts = journal.meldungen_lesen(typ="alert")
    assert alerts[0]["titel"] == "Testwarnung"
    assert alerts[0]["prioritaet"] == 2
    assert alerts[0]["quellen"] == ["schritt#1"]


def test_alert_schreibt_journallauf_als_nachweis():
    meldung_id = melder.alert("alert", "X", "Y", prioritaet=3)
    lauf = journal.list_laeufe(rolle="melder")[0]
    assert lauf["quelle"] == "ereignis"
    assert lauf["status"] == "ok"
    assert "X" in lauf["zusammenfassung"]
    assert meldung_id > 0


# ── Ampelwechsel-Watcher (Abnahmekriterium) ────────────────────────

def _wechsel_schreiben(signal_id=2349227, richtung="verschlechterung"):
    db.init_db()
    return db.store_ampel_wechsel(
        signal_id, "2026-09-22 07:00:00", "daemon", "🟢", "🟡",
        farbwechsel=True, richtung=richtung,
        gruende=[{"kriterium": "dd_schranke", "alt": "grün",
                  "neu": "gelb", "berechnung": "Puffer 2 Punkte"}],
        name="Gold Spike")


def test_kuenstlicher_ampelwechsel_erzeugt_alert_mit_quellverweis():
    wechsel = _wechsel_schreiben()
    gemeldet = melder.pruefe_neue_wechsel(log=lambda *_: None)
    assert len(gemeldet) == 1
    alerts = journal.meldungen_lesen(typ="alert")
    meldung = alerts[0]
    assert "Gold Spike" in meldung["titel"]
    assert "🟢" in meldung["titel"] and "🟡" in meldung["titel"]
    assert f"ampel_wechsel#{wechsel}" in meldung["quellen"]
    assert "dd_schranke" in meldung["text"]
    assert meldung["prioritaet"] == 3  # Verschlechterung = kritisch


def test_watcher_idempotent_und_verbesserung_gelber():
    _wechsel_schreiben(richtung="verschlechterung")
    melder.pruefe_neue_wechsel(log=lambda *_: None)
    stand = journal.meldungen_zaehlen(typ="alert")
    melder.pruefe_neue_wechsel(log=lambda *_: None)  # nichts Neues
    assert journal.meldungen_zaehlen(typ="alert") == stand
    # Verbesserung bleibt Warnung (P2), nicht kritisch.
    db.store_ampel_wechsel(
        2349227, "2026-09-22 08:00:00", "daemon", "🟡", "🟢",
        farbwechsel=True, richtung="verbesserung", gruende=[], name="X")
    melder.pruefe_neue_wechsel(log=lambda *_: None)
    alerts = journal.meldungen_lesen(typ="alert", limit=1)
    assert alerts[0]["prioritaet"] == 2


# ── Tagesdigest ────────────────────────────────────────────────────

def test_digest_verschiebt_solange_betreuer_laueft():
    journal.lauf_starten("betreuer", quelle="daemon", signal_id=1)  # bleibt laeuft
    ergebnis = melder.tagesdigest(quelle="test", log=lambda *_: None)
    assert ergebnis["status"] == "skipped"
    assert "Betreuer noch aktiv" in ergebnis["grund"]
    assert journal.meldungen_zaehlen(typ="digest") == 0


def test_digest_ohne_llm_maschinelle_fassung(monkeypatch):
    monkeypatch.setattr(melder, "_llm_digest", lambda *a, **k: None)
    dossier.beobachtung_speichern(1, "KONFORM", "Alles im Rahmen.")
    ergebnis = melder.tagesdigest(quelle="test", log=lambda *_: None)
    assert ergebnis["status"] == "ok"
    text = journal.meldungen_lesen(typ="digest")[0]["text"]
    assert "KONFORM: 1" in text
    assert "Token-Verbrauch" in text


def test_digest_grundlage_zaehlt_laeufe_und_budget():
    journal.lauf_abschliessen(journal.lauf_starten("dirigent", quelle="test"), "ok")
    ereignisse = melder._ereignisse_heute(config.load_settings())
    assert ereignisse["laeufe_heute"]["anzahl"] >= 1
    assert ereignisse["tagesbudget"] == 500_000
    assert isinstance(ereignisse["beobachtungen"], dict)


# ── Betreuer: Stilbruch → Sofort-Alert ─────────────────────────────

def test_stilbruch_im_betreuer_loest_alert_aus(tmp_path, monkeypatch):
    db.init_db()
    db.upsert_signal(2349227, name="Test Spike")
    db.store_forensik(2349227, {"ampel": "🟢"})
    dossier.profil_speichern(2349227, "Profil", "glm-5.3", {})
    positions_header = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;"
                        "Commission;Swap;Profit\n")
    alt = tmp_path / "alt.csv"
    alt.write_text(positions_header +
                   "2026.09.20 10:15:00;Buy;0.01;XAUUSD;1900.5;0.01;"
                   "2026.09.20 11:15:00;1910.5;0;0;10.00\n", encoding="utf-8")
    db.store_trade_file(2349227, str(alt))
    neu = tmp_path / "neu.csv"
    neu.write_text((positions_header
                    + "2026.09.20 10:15:00;Buy;0.01;XAUUSD;1900.5;0.01;"
                      "2026.09.20 11:15:00;1910.5;0;0;10.00\n"
                    + "2026.09.22 03:00:00;Sell;0.50;XAUUSD;2600;0.50;"
                      "2026.09.22 04:00:00;2550;0;0;-2500.00\n"),
                   encoding="utf-8")
    monkeypatch.setattr(betreuer, "export_holen",
                        lambda session, signal, settings: (str(neu), False))
    antwort = ("EINORDNUNG: STILBRUCH\nNächtlicher Riesen-Trade mit 0,5 Lots "
               "— verletzt Merkmale 3 und 4 (Sessions, Sizing).")
    monkeypatch.setattr(betreuer, "_llm_einordnung",
                        lambda *a, **k: (antwort, 99))
    ergebnis = betreuer.signal_pruefen(
        {"id": 2349227, "name": "Test Spike", "ampel": "🟢"},
        config.load_settings(), log=lambda *_: None)
    assert ergebnis["einordnung"] == "STILBRUCH"
    alerts = journal.meldungen_lesen(typ="alert")
    assert alerts[0]["prioritaet"] == 3
    assert "STILBRUCH: Test Spike" == alerts[0]["titel"]
    assert "schritt#99" in alerts[0]["quellen"]


# ── Scheduler & Rollen ─────────────────────────────────────────────

def test_scheduler_melder_faellig_nach_40_minuten():
    from mqlkiscanner.agenten import scheduler
    settings = config.load_settings()
    assert "melder" not in scheduler.faellige_rollen(
        datetime(2026, 9, 22, 7, 9), settings)
    assert "melder" in scheduler.faellige_rollen(
        datetime(2026, 9, 22, 7, 10), settings)


def test_rollen_phase_d_erreicht():
    # Phase D ist seit Phase E nicht mehr AKTUELL, aber erreicht (Melder läuft).
    assert rollen.phase_aktiv(rollen.ROLLEN_NACH_KEY["melder"], "D")
    assert rollen.phase_aktiv(rollen.ROLLEN_NACH_KEY["melder"], "E")
