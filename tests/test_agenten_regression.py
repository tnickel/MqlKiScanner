# -*- coding: utf-8 -*-
"""Regressionstests des Agentenbetriebs — Absicherung der Review-Findings.

Je Phase die kritischen Verträge, die bei Durchsicht Lücken zeigten:
A: Daemon-Stopp/Status ohne PID, Dirigent-LLM-Erfolgspfad, Lock-Freigabe
   bei Exception, Rollen-Isolation im Tick
B: eine Session für den ganzen Betreuer-Tageslauf, geänderte Datei ohne
   neue gefüllte Trades
C: 30-Tage-Veränderung braucht 31 Bars (lookback + 1)
E: fehlgeschlagener Scan verbraucht nicht den Monats-Anstoß
"""
from datetime import datetime
from pathlib import Path

import pytest

from mqlkiscanner import config, db
from mqlkiscanner.agenten import (betreuer, daemon, delta, dirigent, dossier,
                                  journal, lock, marktdata, rollen,
                                  scan_launcher, scheduler)


# ── Phase A: Daemon-Steuerung ohne Prozess ─────────────────────────

def test_daemon_stoppen_entzieht_freigabe_und_setzt_stoppwunsch():
    config.save_settings({**config.load_settings(), "agenten_enabled": True})
    ergebnis = daemon.stoppen()
    assert ergebnis["gestoppt"] is True
    assert config.load_settings()["agenten_enabled"] is False
    assert journal.steuerung_lesen()["stop_wunsch"] == "1"


def test_daemon_status_ohne_pid_nie_aktiv():
    """Regression: leere PID nach sauberem Stopp = nicht aktiv — der
    Herzschlag-Alleinzustand zeigte 'läuft' bis zu 2 Minuten nach Stopp."""
    journal.steuerung_setzen("pid", "")
    journal.steuerung_setzen("letzter_tick",
                             datetime.now().isoformat(sep=" ",
                                                      timespec="seconds"))
    assert daemon.status()["aktiv"] is False


def test_lock_wird_bei_exception_freigegeben(tmp_path):
    with pytest.raises(RuntimeError):
        with lock.lauf_lock(tmp_path, "ex"):
            raise RuntimeError("Zwischenfall")
    assert lock.lock_status(tmp_path, "ex")["frei"]


def test_tick_isoliert_rollenfehler(monkeypatch):
    """Eine exceptionschmeißende Rolle darf die anderen Rollen des Ticks
    nicht blockieren (Scheduler-Vertrag seit Phase E)."""
    config.save_settings({**config.load_settings(), "agenten_enabled": True})
    import mqlkiscanner.agenten.dirigent as dirigent_modul
    monkeypatch.setattr(dirigent_modul, "tageslauf",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("Krawall")))
    ergebnis = scheduler.tick(jetzt=datetime(2026, 9, 22, 7, 10),
                              log=lambda *_: None)
    je_rolle = {e["rolle"]: e for e in ergebnis["ausgefuehrt"]}
    assert je_rolle["dirigent"]["status"] == "fehler"
    # Markt läuft weiter (Terminal aus → sauberer Skip), Digest kommt an.
    assert je_rolle["markt"]["status"] == "skipped"
    assert je_rolle["melder"]["status"] == "ok"
    assert journal.meldungen_lesen(typ="digest")


# ── Phase A: Dirigent-LLM-Erfolgspfad (Fake-Client) ────────────────

class _FakeGlmClient:
    """Minimal-Client: Key vorhanden, eine whitelist-konforme Antwort."""
    aufrufe: list[str] = []

    def __init__(self, *a, **k):
        self.usage = type("U", (), {"total_tokens": 0})()
        self.last_call = {}

    @property
    def has_key(self):
        return True

    def chat(self, prompt, model=None, stufe=1, temperature=0.4,
             max_tokens=1600, meta_out=None):
        _FakeGlmClient.aufrufe.append(prompt)
        if meta_out is not None:
            meta_out.update({"model": model, "total_tokens": 1234,
                             "dauer_s": 3.2})
        return ('{"aktionen": ["scan_gelb_gruen", "unbekannt_ding"], '
                '"begruendung": "Sonntag — Wochenlauf."}')


def test_dirigent_llm_entscheidung_wird_protokolliert_und_gefiltert(monkeypatch):
    _FakeGlmClient.aufrufe = []
    monkeypatch.setattr(dirigent.llm_client, "GlmClient", _FakeGlmClient)
    ergebnis = dirigent.tageslauf(quelle="test", log=lambda *_: None)
    assert ergebnis["status"] == "ok"
    assert ergebnis["entscheidung"]["aktionen"] == ["scan_gelb_gruen"]
    schritt = next(s for s in journal.list_schritte(limit=20)
                   if s["schritt"] == "llm_entscheidung")
    voll = journal.schritt_lesen(schritt["id"])
    assert '"tokens_heute"' in voll["prompt"]   # gefüllter Lagestatus vollständig
    assert "Sonntag" in (voll["antwort"] or "")  # Antwort vollständig
    assert voll["tokens"] == 1234
    assert voll["detail"]["filter"]["aktionen"] == ["scan_gelb_gruen"]


# ── Phase B: Session- und Delta-Verträge ───────────────────────────

POSITIONS_HEADER = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;"
                    "Commission;Swap;Profit\n")
_ZEILE_A = ("2026.09.20 10:15:00;Buy;0.01;XAUUSD;1900.5;0.01;"
            "2026.09.20 11:15:00;1910.5;0;0;10.00\n")
_ZEILE_B = ("2026.09.21 21:10:00;Buy;0.01;XAUUSD;1915.0;0.01;"
            "2026.09.21 22:00:00;1922.0;0;0;7.00\n")


def _signal_vorbereitet(tmp_path, export_pfad, monkeypatch, signal_id=2349227,
                        name="Test Spike"):
    db.init_db()
    db.upsert_signal(signal_id, name=name)
    db.store_forensik(signal_id, {"ampel": "🟢"})
    dossier.profil_speichern(signal_id, "Profil", "glm-5.3", {})
    alt = tmp_path / f"alt_{signal_id}.csv"
    alt.write_text(POSITIONS_HEADER + _ZEILE_A, encoding="utf-8")
    db.store_trade_file(signal_id, str(alt))
    monkeypatch.setattr(betreuer, "export_holen",
                        lambda session, signal, settings: (export_pfad, False))
    return {"id": signal_id, "name": name, "ampel": "🟢"}


def test_geaenderte_datei_ohne_neue_trades(tmp_path, monkeypatch):
    """Reihenfolge gedreht: neuer SHA, gleiche Trades → KEINE_NEUEN_TRADES,
    kein Modellaufruf (Delta wird trotzdem protokolliert)."""
    signal = _signal_vorbereitet(tmp_path, "", monkeypatch)
    sid = signal["id"]
    # Snapshot mit BEIDEN Zeilen, Export mit beiden in umgekehrter Reihenfolge.
    with db._connect() as conn:
        snapshot_pfad = conn.execute(
            "SELECT path FROM trade_files WHERE signal_id=?", (sid,)
        ).fetchone()["path"]
    Path(snapshot_pfad).write_text(
        POSITIONS_HEADER + _ZEILE_A + _ZEILE_B, encoding="utf-8")
    neu = tmp_path / "neu.csv"
    neu.write_text(POSITIONS_HEADER + _ZEILE_B + _ZEILE_A, encoding="utf-8")
    monkeypatch.setattr(betreuer, "export_holen",
                        lambda session, signal, settings: (str(neu), False))
    llm_aufrufe = []
    monkeypatch.setattr(betreuer, "_llm_einordnung",
                        lambda *a, **k: llm_aufrufe.append(1))
    ergebnis = betreuer.signal_pruefen(signal, config.load_settings(),
                                       log=lambda *_: None)
    assert ergebnis["einordnung"] == "KEINE_NEUEN_TRADES"
    assert llm_aufrufe == []
    assert dossier.deltas_lesen(sid)[0]["neue_trades"] == 0


def test_tageslauf_nutzt_eine_session_fuer_alle_signale(tmp_path, monkeypatch):
    """Rate-Limiter-Vertrag: EINE Mql5Session je Tageslauf, nicht je Signal."""
    erstellte = []
    class _FakeSession:
        def __init__(self, settings=None):
            erstellte.append(self)

    exports = {}
    for sid in (100, 200):
        f = tmp_path / f"e_{sid}.csv"
        f.write_text(POSITIONS_HEADER + _ZEILE_A, encoding="utf-8")
        db.init_db()
        db.upsert_signal(sid, name=f"S{sid}")
        db.store_forensik(sid, {"ampel": "🟡"})
        dossier.profil_speichern(sid, "Profil", "glm-5.3", {})
        db.store_trade_file(sid, str(f))
        exports[sid] = str(f)
    monkeypatch.setattr(betreuer, "Mql5Session", _FakeSession)
    monkeypatch.setattr(betreuer, "export_holen",
                        lambda session, signal, settings:
                        (exports[signal["id"]], True))
    monkeypatch.setattr(betreuer, "kandidaten",
                        lambda settings=None: [
                            {"id": 100, "name": "S100", "ampel": "🟡"},
                            {"id": 200, "name": "S200", "ampel": "🟡"}])
    betreuer.tageslauf(quelle="test", log=lambda *_: None)
    assert len(erstellte) == 1, "Tageslauf muss genau EINE Session bauen"


# ── Phase C: Kennzahlen-Grenzfälle ─────────────────────────────────

def _bars(closes):
    return [{"time": i, "open": c, "high": c + 1, "low": c - 1, "close": c}
            for i, c in enumerate(closes)]


def test_veraenderung_30t_braucht_31_closes():
    closes = [100 + i for i in range(31)]
    k = marktdata.kennzahlen_aus_rates(_bars(closes[:30] + closes[:1]),
                                       _bars(closes))
    assert k["veraenderung_pct"]["30t"] is not None  # 31 Bars reichen
    k_kurz = marktdata.kennzahlen_aus_rates(_bars(closes[:29]),
                                            _bars(closes[:30]))
    assert k_kurz["veraenderung_pct"]["30t"] is None  # 30 Bars nicht


def test_kurse_holen_nach_31_bars_verlangt():
    """Der Abruf fordert lookback+1 D1-Bars an (Regression zum +1-Fix)."""
    import MetaTrader5 as mt5
    angefragt = {}
    def _fake_copy(symbol, timeframe, start, count):
        angefragt.setdefault(timeframe, []).append(count)
        n = max(2, count)
        return [{"time": i, "open": 1, "high": 2, "low": 0.5, "close": 1 + i}
                for i in range(n)]
    monkey = pytest.MonkeyPatch()
    monkey.setattr(mt5, "initialize", lambda *a, **k: True)
    monkey.setattr(mt5, "shutdown", lambda: None)
    monkey.setattr(mt5, "terminal_info", lambda: type("T", (), {"name": "T"})())
    monkey.setattr(mt5, "symbol_select", lambda s, f: True)
    monkey.setattr(mt5, "copy_rates_from_pos", _fake_copy)
    monkey.setattr(marktdata, "terminal_laueft", lambda pfad: True)
    try:
        ergebnis = marktdata.kurse_holen(
            ["XAUUSD"], {**config.load_settings(), "markt_lookback_tage": 30})
        assert ergebnis["ok"], ergebnis
        assert max(angefragt[mt5.TIMEFRAME_D1]) == 31  # lookback + 1
    finally:
        monkey.undo()


# ── Phase E: Scan-Merker im Fehlerfall ─────────────────────────────

def test_fehlgeschlagener_scan_verbraucht_monat_nicht(monkeypatch):
    """Tages-Merker ja (kein 30-s-Retry-Loop), Monats-Merker nein — der
    Full-Scan wiederholt sich am nächsten Tag im 1.-Werktag-Fenster."""
    def _kaputt(*a, **k):
        raise RuntimeError("MQL5-Krawall")
    monkeypatch.setattr(scan_launcher, "_scan_innerhalb", _kaputt)
    ergebnis = scan_launcher.starte_scan("full", quelle="test",
                                         log=lambda *_: None)
    assert ergebnis["status"] == "fehler"
    assert scan_launcher.scan_heute_gestartet("full") is True
    assert scan_launcher.scan_monat_gestartet("full") is False
    # Und die Fehlermeldung steht im Postfach (P2).
    meldung = journal.meldungen_lesen(typ="scan")[0]
    assert "FEHLGESCHLAGEN" in meldung["titel"] and meldung["prioritaet"] == 2


def test_dirigent_llm_entscheidung_ist_informativ_nicht_exekutiv():
    """Vertrag: Der Code-Plan entscheidet — die LLM-Aktionen werden nur
    protokolliert, nirgends ausgeführt (Whitelist-Empfehlung)."""
    assert dirigent.ERLAUBTE_AKTIONEN == frozenset((
        "delta_laufen_lassen", "delta_ueberspringen", "markt_holen",
        "markt_ueberspringen", "scan_gelb_gruen", "scan_full",
        "meldung_schicken"))
    quelltext = (config.SRC / "mqlkiscanner" / "agenten" / "scheduler.py"
                 ).read_text(encoding="utf-8")
    assert "ERLAUBTE_AKTIONEN" not in quelltext  # Scheduler plant selbst
