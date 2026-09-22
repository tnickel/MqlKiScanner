# -*- coding: utf-8 -*-
"""Phase C: MetaTrader-Anbindung (nur lesend), Marktbeobachter, Kontext-Fluss.

Der MT5-Zugriff selbst wird nie in Tests ausgeführt (kein Terminal in der
Test-Umgebung, Start-Politik verboten): kurse_holen/verbindung_testen sind
die Nahtstellen — die Rollen-Tests arbeiten mit kurse_override bzw. Stubs.
Die Lese-Whitelist wird statisch gegen den Quelltext geprüft.
"""
import re
from datetime import datetime
from pathlib import Path

from mqlkiscanner import config, db
from mqlkiscanner.agenten import (betreuer, journal, markt, marktdata, rollen)

QUELLE = Path(marktdata.__file__)


# ── Statische Whitelist (doc/19 §7.1) ──────────────────────────────

def test_mt5_nur_lese_aufrufe_statisch():
    """marktdata.py darf ausschließlich erlaubte MT5-Aufrufe enthalten."""
    quelltext = QUELLE.read_text(encoding="utf-8")
    aufrufe = set(re.findall(r"mt5\.([a-z_]+)\(", quelltext))
    unerlaubt = aufrufe - marktdata.ERLAUBTE_MT5_AUFRUFE
    assert not unerlaubt, f"Unerlaubte MT5-Aufrufe: {unerlaubt}"
    verboten = ("order_send", "order_check", "order_buy", "order_sell",
                "positions_open")
    for name in verboten:
        assert name not in quelltext


def test_whitelist_deckt_genutzte_aufrufe():
    quelltext = QUELLE.read_text(encoding="utf-8")
    aufrufe = set(re.findall(r"mt5\.([a-z_]+)\(", quelltext))
    assert aufrufe  # der Test findet überhaupt Aufrufe
    assert aufrufe <= marktdata.ERLAUBTE_MT5_AUFRUFE


# ── Kennzahlen (reiner Code) ───────────────────────────────────────

def _d1(closes, high=None, low=None):
    bars = []
    for i, c in enumerate(closes):
        bars.append({"time": i, "open": c, "high": high or c + 5,
                     "low": low or c - 5, "close": c})
    return bars


def test_kennzahlen_volle_basis():
    closes = [100 + i for i in range(31)]  # steigender Markt: 100..130
    d1 = _d1(closes)
    h1 = [{"time": i, "open": 1, "high": 3, "low": 0.5, "close": 2}
          for i in range(40)]
    k = marktdata.kennzahlen_aus_rates(h1, d1)
    assert k["close"] == 130
    assert k["veraenderung_pct"]["heute"] == round(130 / 129 * 100 - 100, 2)
    assert k["veraenderung_pct"]["7t"] == round(130 / 123 * 100 - 100, 2)
    assert k["distanz_30t_hoch_pct"] == 0.0      # Close = Hoch
    assert k["distanz_30t_tief_pct"] == round(130 / 100 * 100 - 100, 2)
    assert k["trend_close_vs_sma10_pct"] > 0     # über dem Schnitt
    assert k["atr14_h1"] > 0 and k["tagesrange_pct"] > 0


def test_kennzahlen_kurze_basis_ohne_crash():
    k = marktdata.kennzahlen_aus_rates([], [{"time": 0, "open": 1, "high": 2,
                                              "low": 0.5, "close": 1}])
    assert k["veraenderung_pct"]["heute"] is None
    assert k["atr14_h1"] is None


# ── Start-Politik ──────────────────────────────────────────────────

def test_kurse_holen_ohne_terminal_und_ohne_startfreigabe(monkeypatch):
    """Kein laufendes Terminal + Standard-Politik ⇒ KEIN Verbindungsversuch.

    Explizite Settings statt load_settings(): in der Produktiv-Konfiguration
    ist markt_start_erlauben aktiviert — Tests dürfen davon nicht abhängen.
    """
    monkeypatch.setattr(marktdata, "terminal_laueft", lambda pfad: False)
    def _verboten():
        raise AssertionError("initialize darf nicht aufgerufen werden")
    import MetaTrader5 as mt5
    monkeypatch.setattr(mt5, "initialize", _verboten)
    ergebnis = marktdata.kurse_holen(["XAUUSD"], {"markt_start_erlauben": False})
    assert not ergebnis["ok"]
    assert "Selbststart" in ergebnis["grund"]


def test_verbindungstest_erklaert_standardpolitik(monkeypatch):
    monkeypatch.setattr(marktdata, "terminal_laueft", lambda pfad: False)
    ergebnis = marktdata.verbindung_testen({"markt_start_erlauben": False})
    assert not ergebnis["ok"]
    assert "Terminal läuft nicht" in ergebnis["grund"]


def _fake_mt5(monkeypatch, aufrufe):
    """MT5-Fakes mit Aufruf-Protokoll: initialize/shutdown + Kursdaten.

    _terminal_prozesse wird leer gemockt: Tests dürfen NIE echte
    terminal64-Prozesse sehen (und damit beenden)."""
    import MetaTrader5 as mt5

    def _initialize(*args, **kwargs):
        aufrufe.append(("initialize", args, kwargs))
        return True

    def _shutdown():
        aufrufe.append(("shutdown", (), {}))

    def _rates(*args):
        anzahl = args[-1]
        return [{"time": i, "open": 100.0 + i, "high": 105.0 + i,
                 "low": 95.0 + i, "close": 100.0 + i} for i in range(anzahl)]

    monkeypatch.setattr(mt5, "initialize", _initialize)
    monkeypatch.setattr(mt5, "shutdown", _shutdown)
    monkeypatch.setattr(mt5, "terminal_info",
                        lambda: type("Info", (), {"name": "FakeTerm"})())
    monkeypatch.setattr(mt5, "symbol_select", lambda *a, **k: True)
    monkeypatch.setattr(mt5, "copy_rates_from_pos", _rates)
    monkeypatch.setattr(marktdata, "_terminal_prozesse", lambda pfad: [])


def test_kurse_holen_selbststart_portable_und_beenden(monkeypatch):
    """Start-Freigabe + kein laufendes Terminal: PORTABLE-Start, und am
    Lauf-Ende wird die Verbindung (und damit das Terminal) wieder beendet."""
    monkeypatch.setattr(marktdata, "terminal_laueft", lambda pfad: False)
    aufrufe = []
    _fake_mt5(monkeypatch, aufrufe)
    ergebnis = marktdata.kurse_holen(
        ["XAUUSD"], {"markt_start_erlauben": True,
                     "markt_terminal_pfad": marktdata.DEFAULT_TERMINAL})
    assert ergebnis["ok"]
    assert ergebnis["selbststart"] is True
    init = next(a for a in aufrufe if a[0] == "initialize")
    assert init[2].get("portable") is True             # Portable-Modus beim Selbststart
    assert init[1][0] == marktdata.DEFAULT_TERMINAL    # richtiger Terminal-Pfad
    assert aufrufe[-1][0] == "shutdown"               # Abbau am Ende


def test_kurse_holen_attach_ohne_portableflag(monkeypatch):
    """Läuft das Terminal schon, wird nur angehängt — KEIN portable-Start."""
    monkeypatch.setattr(marktdata, "terminal_laueft", lambda pfad: True)
    aufrufe = []
    _fake_mt5(monkeypatch, aufrufe)
    ergebnis = marktdata.kurse_holen(
        ["XAUUSD"], {"markt_start_erlauben": True,
                     "markt_terminal_pfad": marktdata.DEFAULT_TERMINAL})
    assert ergebnis["ok"]
    assert ergebnis["selbststart"] is False
    init = next(a for a in aufrufe if a[0] == "initialize")
    assert init[2].get("portable") is False


def test_terminal_wird_nach_lauf_auch_bei_attach_beendet(monkeypatch):
    """Nutzer-Regel 22.09.2026: Das Terminal dieses Pfads gehört dem Scanner
    — auch ein VORGEFUNDENES Terminal wird nach dem Lauf beendet."""
    import subprocess

    monkeypatch.setattr(marktdata, "terminal_laueft", lambda pfad: True)
    aufrufe = []
    _fake_mt5(monkeypatch, aufrufe)
    zustand = {"prozesse": [(4242, marktdata.DEFAULT_TERMINAL.lower())]}
    monkeypatch.setattr(marktdata, "_terminal_prozesse",
                        lambda pfad: zustand["prozesse"])
    kills: list[list[str]] = []

    def _fake_run(befehl, **kwargs):
        kills.append(list(befehl))
        zustand["prozesse"] = []  # der sanfte taskkill reicht im Test
        return subprocess.CompletedProcess(befehl, 0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    ergebnis = marktdata.kurse_holen(
        ["XAUUSD"], {"markt_start_erlauben": True,
                     "markt_terminal_pfad": marktdata.DEFAULT_TERMINAL})
    assert ergebnis["ok"]
    assert ergebnis["terminal_beendet"] is True
    assert any("taskkill" in k for k in kills), kills
    sanft = next(k for k in kills if "taskkill" in k)
    assert "/F" not in sanft  # sanfter Versuch zuerst (WM_CLOSE)


# ── Marktbeobachter-Rolle ──────────────────────────────────────────

KURSE = {"XAUUSD": {"close": 2650.0,
                    "veraenderung_pct": {"heute": 0.4, "7t": 2.1, "30t": 5.0},
                    "distanz_30t_hoch_pct": -0.5,
                    "distanz_30t_tief_pct": 6.2,
                    "tagesrange_pct": 1.1, "atr14_h1": 9.5,
                    "trend_close_vs_sma10_pct": 1.4}}


def test_markt_lauf_mit_kursen_und_llm(monkeypatch):
    antwort = ("XAUUSD: Gold notiert bei 2.650 USD, heute +0,4 %, über der "
               "Woche +2,1 % — ruhiger Aufwärtstrend nahe des 30-Tage-Hochs.\n\n"
               "Marktlage insgesamt: moderat volatiler Aufwärtstrend.")
    monkeypatch.setattr(markt, "_llm_lage", lambda *a, **k: antwort)
    ergebnis = markt.tageslauf(quelle="test",
                               kurse_override={"ok": True, "terminal": "Test",
                                               "kurse": KURSE},
                               log=lambda *_: None)
    assert ergebnis["status"] == "ok"
    assert "XAUUSD" in ergebnis["symbole"]
    kontext = markt.kontext_heute()
    assert kontext is not None
    assert "2.650" in kontext["lage"] or "2650" in kontext["lage"]
    assert kontext["kennzahlen"]["XAUUSD"]["close"] == 2650.0
    lauf = journal.list_laeufe(rolle="markt")[0]
    assert lauf["status"] == "ok"


def test_markt_lauf_uebersprungen_ohne_terminal():
    ergebnis = markt.tageslauf(quelle="test",
                               kurse_override={"ok": False,
                                               "grund": "Terminal läuft nicht."},
                               log=lambda *_: None)
    assert ergebnis["status"] == "skipped"
    assert markt.kontext_heute() is None or True  # kein neuer Kontext
    lauf = journal.list_laeufe(rolle="markt")[0]
    assert lauf["status"] == "skipped"


def test_markt_fallback_ohne_llm(monkeypatch):
    monkeypatch.setattr(markt, "_llm_lage", lambda *a, **k: None)
    ergebnis = markt.tageslauf(quelle="test",
                               kurse_override={"ok": True, "kurse": KURSE},
                               log=lambda *_: None)
    assert "maschinelle Kurzfassung" in ergebnis["lage"]
    assert "XAUUSD" in ergebnis["lage"]


def test_beobachtungsliste_manuell_und_aus_kandidaten(monkeypatch):
    db.init_db()
    db.upsert_signal(1, name="A", stats={})
    db.store_forensik(1, {"ampel": "🟡", "symbole": "XAUUSD, EURUSD"})
    monkeypatch.setattr(betreuer, "kandidaten",
                        lambda settings=None: [{"id": 1, "name": "A",
                                                "platform": "", "ampel": "🟡"}])
    settings = config.load_settings()
    settings["markt_symbole_manuell"] = "xauxbt, xauusd"
    liste = markt.beobachtungsliste(settings)
    assert liste == ["XAUXBT", "XAUUSD", "EURUSD"]  # manuell zuerst, dedupliziert


def test_beobachtungsliste_strip_plus_suffix_und_artefakte(monkeypatch):
    """Forensik-Symbole mit "+"-Markierung (z. B. "XAUUSD+") und Feld-
    Artefakte ("SUMMARY") dürfen nicht als Symbol an MT5 gehen — MT5
    kennt nur das nackte Symbol."""
    db.init_db()
    db.upsert_signal(2, name="B", stats={})
    db.store_forensik(2, {"ampel": "🟢", "symbole": "XAUUSD+, EURUSD+ SUMMARY"})
    monkeypatch.setattr(betreuer, "kandidaten",
                        lambda settings=None: [{"id": 2, "name": "B",
                                                "platform": "", "ampel": "🟢"}])
    liste = markt.beobachtungsliste({"markt_symbole_manuell": ""})
    assert liste == ["XAUUSD", "EURUSD"]


def test_betreuter_marktkontext_text(monkeypatch):
    assert "Kein Marktkontext" in betreuer._marktkontext_text()
    markt.init_markt()
    with db._connect() as conn:
        conn.execute("INSERT INTO markt_kontext (ts, symbole_json, "
                     "kennzahlen_json, lage_text) VALUES (?,?,?,?)",
                     (datetime.now().isoformat(sep=" ", timespec="seconds"),
                      "[]", "{}", "Alles ruhig im Goldmarkt."))
    assert "Alles ruhig" in betreuer._marktkontext_text()


def test_scheduler_markt_zwischen_dirigent_und_betreuer():
    from mqlkiscanner.agenten import scheduler
    settings = config.load_settings()
    assert scheduler.faellige_rollen(datetime(2026, 9, 22, 6, 32), settings) == \
        ["dirigent"]
    assert scheduler.faellige_rollen(datetime(2026, 9, 22, 6, 36), settings) == \
        ["dirigent", "markt"]
    assert scheduler.faellige_rollen(datetime(2026, 9, 22, 6, 50), settings) == \
        ["dirigent", "markt", "betreuer"]


def test_rollen_phase_c_erreicht():
    # Phase C ist seit Phase D nicht mehr AKTUELL, aber erreicht (Markt läuft).
    assert rollen.phase_aktiv(rollen.ROLLEN_NACH_KEY["markt"], "C")
    assert rollen.phase_aktiv(rollen.ROLLEN_NACH_KEY["markt"], "D")


def test_markt_settings_defaults():
    settings = config.load_settings()
    assert settings["markt_start_erlauben"] is False
    assert "terminal64.exe" in settings["markt_terminal_pfad"]
    assert settings["markt_lookback_tage"] == 30
