# -*- coding: utf-8 -*-
"""Phase B: Dossiers, Trade-Delta, Profil-Destillation, Betreuer-Tageslauf.

Der Betreuer-Fluss wird ohne Netz getestet: Export-Holen und LLM-Aufruf
sind die beiden Nahtstellen — beide werden gestubbt; Delta-Berechnung und
Protokollpflicht laufen echt durch die Produktionsmodule.
"""
from datetime import datetime

import pytest

from mqlkiscanner import config, db
from mqlkiscanner.agenten import (betreuer, delta, destillation, dossier,
                                  journal, rollen)

POSITIONS_HEADER = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;"
                    "Commission;Swap;Profit\n")


def _csv(pfad, zeilen):
    pfad.write_text(POSITIONS_HEADER + "".join(zeilen), encoding="utf-8")
    return str(pfad)


def _trade_zeile(n, stunde=10, profit="10.00", volume="0.01"):
    datum = f"2026.09.{20 + n // 24:02d}"
    return (f"{datum} {stunde:02d}:15:00;Buy;{volume};XAUUSD;1900.5;{volume};"
            f"{datum} {stunde + 1:02d}:15:00;1910.5;0;0;{profit}\n")


# ── Delta (reiner Code) ────────────────────────────────────────────

def test_delta_ohne_aenderung(tmp_path):
    alt = _csv(tmp_path / "alt.csv", [_trade_zeile(1), _trade_zeile(2)])
    neu = _csv(tmp_path / "neu.csv", [_trade_zeile(1), _trade_zeile(2)])
    assert delta.neue_trades(alt, neu) == []
    assert delta.kennzahlen([]) == {"anzahl": 0}


def test_delta_mit_neuen_trades(tmp_path):
    alt = _csv(tmp_path / "alt.csv", [_trade_zeile(1)])
    neu = _csv(tmp_path / "neu.csv",
               [_trade_zeile(1), _trade_zeile(2, stunde=22, profit="-40.00"),
                _trade_zeile(3, profit="12.00")])
    neue = delta.neue_trades(alt, neu)
    assert len(neue) == 2
    kzz = delta.kennzahlen(neue)
    assert kzz["anzahl"] == 2
    assert kzz["symbole"] == ["XAUUSD"]
    assert kzz["gewinne"] == 1 and kzz["verluste"] == 1
    assert kzz["verlustsumme"] == -40.0
    assert kzz["max_verlustserie"] == 1
    assert kzz["stunden_offen"] == [10, 22]


def test_delta_ohne_altZaehlt_alles(tmp_path):
    neu = _csv(tmp_path / "neu.csv", [_trade_zeile(1), _trade_zeile(2)])
    assert len(delta.neue_trades(None, neu)) == 2


def test_datei_sha256_stabil(tmp_path):
    datei = _csv(tmp_path / "x.csv", [_trade_zeile(1)])
    assert delta.datei_sha256(datei) == delta.datei_sha256(datei)
    assert len(delta.datei_sha256(datei)) == 64


# ── Dossier-Datenbasis ─────────────────────────────────────────────

def test_profil_versioniert_nie_ueberschrieben():
    v1 = dossier.profil_speichern(1, "Profiltext A", "glm-5.3", {"a": 1})
    v2 = dossier.profil_speichern(1, "Profiltext B", "glm-5.3", {"a": 2},
                                  aenderungs_grund="Tiefenanalyse erneuert")
    assert (v1, v2) == (1, 2)
    aktuell = dossier.profil_lesen(1)
    assert aktuell["profil_text"] == "Profiltext B"
    assert aktuell["aenderungs_grund"] == "Tiefenanalyse erneuert"
    assert dossier.profil_historie(1)[0]["version"] == 2
    assert dossier.profil_lesen(999) is None


def test_beobachtung_nur_bekannte_einordnung():
    with pytest.raises(AssertionError):
        dossier.beobachtung_speichern(1, "SUPER", "text")
    dossier.beobachtung_speichern(1, "KONFORM", "Alles im Rahmen.")
    e = dossier.beobachtungen_lesen(1)[0]
    assert e["einordnung"] == "KONFORM"
    assert "Alles im Rahmen" in dossier.letzte_beobachtungen(1)


def test_delta_speichern_und_lesen():
    d = dossier.delta_speichern(1, None, "abc", 3, {"anzahl": 3})
    eintraege = dossier.deltas_lesen(1)
    assert eintraege[0]["id"] == d
    assert eintraege[0]["neue_trades"] == 3
    assert eintraege[0]["delta"]["anzahl"] == 3


# ── Betreuer-Fluss (Export + LLM gestubbt) ────────────────────────

@pytest.fixture
def signal_mit_snapshot(tmp_path, monkeypatch):
    """Ein 🟢-Signal mit Profil, Snapshot in trade_files und gestubbtem Export."""
    db.init_db()
    db.upsert_signal(2349227, name="Test Spike", stats={"ampel": "🟢"})
    db.store_forensik(2349227, {"ampel": "🟢", "vollstaendig": True})
    db.store_analysis(2349227, "tiefenanalyse", "glm-5.3", 10,
                      "Langer Tiefenanalysetext über den Ausbruchs-Scanner.")
    dossier.profil_speichern(2349227, "Profil: Ausbruchs-Scanner, 21:10 Uhr.",
                             "glm-5.3", {})
    alt_pfad = _csv(tmp_path / "alt.csv", [_trade_zeile(1)])
    db.store_trade_file(2349227, alt_pfad)
    export_pfad = _csv(tmp_path / "neu.csv",
                       [_trade_zeile(1), _trade_zeile(2, profit="15.00")])
    monkeypatch.setattr(betreuer, "export_holen",
                        lambda session, signal, settings: (export_pfad, False))
    # Kandidatenliste auf das Testsignal zurechtstutzen (Ampel kommt aus
    # results_from_db — Stub greift am Moduleinstieg vorbei).
    monkeypatch.setattr(betreuer, "kandidaten",
                        lambda settings=None: [{"id": 2349227, "name": "Test Spike",
                                                "platform": "", "ampel": "🟢"}])
    return {"id": 2349227, "name": "Test Spike", "ampel": "🟢"}


def test_betreuter_lauf_mit_neuen_trades(signal_mit_snapshot, monkeypatch):
    antwort = ("EINORDNUNG: KONFORM\nZwei neue Trades um 10:15 Uhr im "
               "dokumentierten Fenster — Lot konstant.")
    monkeypatch.setattr(betreuer, "_llm_einordnung",
                        lambda *a, **k: (antwort, 42))
    ergebnis = betreuer.signal_pruefen(signal_mit_snapshot,
                                       config.load_settings(), log=lambda *_: None)
    assert ergebnis["status"] == "ok"
    assert ergebnis["einordnung"] == "KONFORM"
    beob = dossier.beobachtungen_lesen(2349227)[0]
    assert beob["einordnung"] == "KONFORM"
    assert beob["schritt_ref"] == 42
    assert dossier.deltas_lesen(2349227)[0]["neue_trades"] == 1
    schritte = [s["schritt"] for s in journal.list_schritte(limit=20)]
    # Geänderter Pfad: Export- und Delta-Schritt; der sha_vergleich-Schritt
    # gehört zum 'unverändert'-Pfad.
    assert "export" in schritte and "delta" in schritte
    assert "sha_vergleich" not in schritte


def test_betreuter_lauf_ohne_neue_trades(signal_mit_snapshot, monkeypatch):
    snapshot_pfad = _snapshot_pfad()
    # Export identisch zum Snapshot: kein LLM, Beobachtung KEINE_NEUEN_TRADES.
    monkeypatch.setattr(betreuer, "export_holen",
                        lambda session, signal, settings: (snapshot_pfad, True))
    calls = []
    monkeypatch.setattr(betreuer, "_llm_einordnung",
                        lambda *a, **k: calls.append(1))
    ergebnis = betreuer.signal_pruefen(signal_mit_snapshot,
                                       config.load_settings(), log=lambda *_: None)
    assert ergebnis["einordnung"] == "KEINE_NEUEN_TRADES"
    assert calls == []  # kein Modellaufruf
    assert dossier.beobachtungen_lesen(2349227)[0]["einordnung"] == \
        "KEINE_NEUEN_TRADES"


def _snapshot_pfad() -> str:
    with db._connect() as conn:
        row = conn.execute("SELECT path FROM trade_files WHERE signal_id=2349227"
                           ).fetchone()
    return row["path"]


def test_einordnung_parsen():
    ein, text = betreuer._einordnung_parsen("EINORDNUNG: STILBRUCH\nNächtliche Trades.")
    assert (ein, text) == ("STILBRUCH", "Nächtliche Trades.")
    ein, text = betreuer._einordnung_parsen("EINORDNUNG: KEINE_NEUEN_TRADES")
    assert ein == "KEINE_NEUEN_TRADES" and text.startswith("(keine")
    ein, text = betreuer._einordnung_parsen("Ohne Markierung.")
    assert ein == "AUFFAELLIG" and "Ohne Markierung." in text


def test_destillation_ohne_grundlage_und_mit_vorhandenem_profil(tmp_path):
    db.init_db()
    db.upsert_signal(111, name="Ohne Analyse")
    lauf = journal.lauf_starten("betreuer", quelle="test")
    ergebnis = destillation.profil_erstellen(111, "Ohne Analyse", "https://x",
                                             config.load_settings(),
                                             lauf_id=lauf, log=lambda *_: None)
    assert not ergebnis["erstellt"]
    assert "kein Profil ohne Belegbasis" in ergebnis["grund"]
    dossier.profil_speichern(222, "Profil", "glm-5.3", {})
    ergebnis = destillation.profil_erstellen(222, "Vorhanden", "https://x",
                                             config.load_settings(),
                                             lauf_id=lauf, log=lambda *_: None)
    assert not ergebnis["erstellt"] and "vorhanden" in ergebnis["grund"]


def test_scheduler_betreuer_faellig_nach_15_minuten():
    from mqlkiscanner.agenten import scheduler
    settings = config.load_settings()
    # 06:34 — nur der Dirigent (Markt ab 06:35, Betreuer ab 06:45).
    assert scheduler.faellige_rollen(datetime(2026, 9, 22, 6, 34), settings) == \
        ["dirigent"]
    # 06:45 — alle drei fällig.
    assert scheduler.faellige_rollen(datetime(2026, 9, 22, 6, 45), settings) == \
        ["dirigent", "markt", "betreuer"]


def test_rollen_phase_b_erreicht():
    # Phase B ist seit Phase C nicht mehr AKTUELL, aber erreicht (Betreuer läuft).
    assert rollen.phase_aktiv(rollen.ROLLEN_NACH_KEY["betreuer"], "B")
    assert rollen.phase_aktiv(rollen.ROLLEN_NACH_KEY["betreuer"], "C")


def test_stilbruch_historie_nur_stilbrueche_neueste_zuerst():
    """Die dauerhafte Signal-Verknüpfung: nur STILBRUCH-Beobachtungen,
    neueste zuerst — KONFORM/andere Einordnungen bleiben außen vor."""
    from mqlkiscanner.agenten import dossier as dossier_db

    dossier_db.init_dossier()
    dossier_db.beobachtung_speichern(999001, "KONFORM", "alles normal")
    dossier_db.beobachtung_speichern(999001, "STILBRUCH", "Martingale erkannt")
    dossier_db.beobachtung_speichern(999001, "STILBRUCH", "SL entfernt")
    dossier_db.beobachtung_speichern(999002, "STILBRUCH", "anderes Signal")
    hist = dossier_db.stilbruch_historie(999001)
    assert [h["text"] for h in hist] == ["SL entfernt", "Martingale erkannt"]
    assert dossier_db.stilbruch_historie(999003) == []
