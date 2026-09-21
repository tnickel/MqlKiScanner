# -*- coding: utf-8 -*-
"""Ampel-Verlauf: Farb-Chronik je Lauf und protokollierte Wechsel (Nutzer-
Anforderung 21.09.2026: Farben immer aufzeichnen, Wechsel speziell
protokollieren — mit Kriterium-Begründungen; kein Reimport alter Läufe)."""
from datetime import datetime, timedelta

import pytest

from mqlkiscanner import ampel_verlauf, db
from mqlkiscanner.pipeline import ScanResult


class _FakeDateTime(datetime):
    """Deterministische Zeitstempel: Chronik-Schlüssel hat Sekundenauflösung."""

    _now = datetime(2026, 9, 21, 12, 0, 0)

    @classmethod
    def now(cls, tz=None):
        return cls._now


@pytest.fixture(autouse=True)
def _zeitmaschine(monkeypatch):
    monkeypatch.setattr(ampel_verlauf, "datetime", _FakeDateTime)
    yield

    _FakeDateTime._now = datetime(2026, 9, 21, 12, 0, 0)


def _tick(sekunden: int = 1) -> None:
    _FakeDateTime._now += timedelta(seconds=sekunden)


def _result(**overrides) -> ScanResult:
    basis = dict(
        id=2349227, name="Testsignal", ampel="🟡", score=4.2,
        urteil="Forensik bestanden", fehler="",
        dd_equity_pct=12.0, dd_balance_pct=14.0, trading_dd_pct=11.0,
        ertrag_monat_pct=6.0, winrate_pct=70.0, max_verlustserie=5,
        verlustserie_usd=-120.0, martingale_flag=False,
        martingale_evidenz=[], stop_evidence="direct",
        stop_nachweis="Orderbuch: 40/40 mit SL", shock_pct_max=20.0,
        shock_usd=500.0, shock_pct_peak_time="2026-01-01 10:00",
    )
    basis.update(overrides)
    return ScanResult(**basis)


SETTINGS = {"schranke_eq_dd_pct": 30.0, "min_ertrag_pct_monat": 5.0}


def test_erstfassung_schreibt_chronik_ohne_wechsel():
    ereignis = ampel_verlauf.erfasse_bewertung(_result(), SETTINGS, quelle="full")
    assert ereignis is None  # Chronik beginnt, noch kein Vorgänger
    verlauf = db.list_ampel_verlauf(2349227)
    assert len(verlauf) == 1 and verlauf[0]["ampel"] == "🟡"
    assert verlauf[0]["quelle"] == "full"
    assert db.count_ampel_wechsel() == 0


def test_gleiche_bewertung_zweiter_eintrag_kein_wechsel():
    ampel_verlauf.erfasse_bewertung(_result(), SETTINGS, quelle="full")
    _tick()
    ereignis = ampel_verlauf.erfasse_bewertung(_result(), SETTINGS, quelle="gelbgruen")
    assert ereignis is None
    assert len(db.list_ampel_verlauf(2349227)) == 2
    assert db.count_ampel_wechsel() == 0


def test_farbwechsel_wird_protokolliert_mit_richtung():
    ampel_verlauf.erfasse_bewertung(_result(ampel="🟡"), SETTINGS)
    _tick()
    ereignis = ampel_verlauf.erfasse_bewertung(
        _result(ampel="🟢", urteil="Kandidat", score=4.0), SETTINGS, quelle="gelbgruen")
    assert ereignis is not None
    assert ereignis["farbwechsel"] and ereignis["ampel_alt"] == "🟡" \
        and ereignis["ampel_neu"] == "🟢"
    assert ereignis["richtung"] == "verbesserung"
    stored = db.list_ampel_wechsel()
    assert len(stored) == 1 and stored[0]["ampel_alt"] == "🟡" \
        and stored[0]["ampel_neu"] == "🟢" and stored[0]["name"] == "Testsignal"


def test_kriterium_kippt_ohne_farbwechsel_fruehindikator():
    ampel_verlauf.erfasse_bewertung(_result(dd_balance_pct=14.0), SETTINGS)
    _tick()
    # DD steigt auf 28 %: Farbe bleibt 🟡, aber die DD-Schranke kippt
    # grün -> gelb (Puffer nur noch 2 Punkte) — Frühindikator.
    ereignis = ampel_verlauf.erfasse_bewertung(_result(dd_balance_pct=28.0), SETTINGS)
    assert ereignis is not None
    assert not ereignis["farbwechsel"]
    assert ereignis["richtung"] == "hinweis"
    kriterien = {g["kriterium"]: g for g in ereignis["gruende"]}
    assert "dd_schranke" in kriterien
    dd = kriterien["dd_schranke"]
    assert dd["ampel_alt"] == "🟢" and dd["ampel_neu"] == "🟡"
    assert "Puffer" in (dd["kurz_neu"] or "")
    assert dd["detail"]


def test_grund_enthaelt_exakte_berechnung():
    ampel_verlauf.erfasse_bewertung(_result(stop_evidence="partial"), SETTINGS)
    _tick()
    ereignis = ampel_verlauf.erfasse_bewertung(_result(stop_evidence="direct"), SETTINGS)
    gruende = {g["kriterium"]: g for g in ereignis["gruende"]}
    assert gruende["stop"]["ampel_alt"] == "🟡" and gruende["stop"]["ampel_neu"] == "🟢"
    assert "Orderbuch" in gruende["stop"]["detail"]


def test_fehlerhafter_lauf_schreibt_nichts():
    ampel_verlauf.erfasse_bewertung(_result(), SETTINGS)
    _tick()
    ereignis = ampel_verlauf.erfasse_bewertung(
        _result(ampel="⚪", fehler="ValueError: Export abgebrochen"), SETTINGS)
    assert ereignis is None
    assert len(db.list_ampel_verlauf(2349227)) == 1  # alter Stand bleibt
    assert db.count_ampel_wechsel() == 0


@pytest.mark.parametrize("alt,neu,erwartet", [
    ("🟡", "🟢", "verbesserung"),
    ("🟢", "🟡", "verschlechterung"),
    ("🟢", "🔴", "verschlechterung"),
    ("🔴", "🟡", "verbesserung"),
    ("⚪", "🟢", "verbesserung"),
    ("⚪", "🔴", "verschlechterung"),
    ("⚪", "🟡", "hinweis"),
    ("🟢", "⚪", "verschlechterung"),
    ("🟡", "🟡", "hinweis"),
])
def test_richtung_einordnung(alt, neu, erwartet):
    assert ampel_verlauf._richtung(alt, neu) == erwartet


def test_wechselliste_filter_und_reihenfolge():
    ampel_verlauf.erfasse_bewertung(_result(id=1, ampel="🟡"), SETTINGS)
    _tick()
    ampel_verlauf.erfasse_bewertung(_result(id=1, ampel="🟢"), SETTINGS)
    _tick()
    ampel_verlauf.erfasse_bewertung(_result(id=2, ampel="🟡"), SETTINGS)
    _tick()
    # Kriterium kippt ohne Farbwechsel (Frühindikator-Eintrag)
    ampel_verlauf.erfasse_bewertung(_result(id=2, dd_balance_pct=28.0), SETTINGS)
    alle = db.list_ampel_wechsel()
    assert len(alle) == 2
    assert alle[0]["signal_id"] == 2  # neueste zuerst
    assert len(db.list_ampel_wechsel(nur_farbwechsel=True)) == 1
    assert len(db.list_ampel_wechsel(signal_id=1)) == 1
    assert db.count_ampel_wechsel() == 2


def test_wechsel_kurztext_nennt_kriterium():
    ampel_verlauf.erfasse_bewertung(_result(), SETTINGS)
    _tick()
    ereignis = ampel_verlauf.erfasse_bewertung(_result(dd_balance_pct=28.0), SETTINGS)
    text = ampel_verlauf.wechsel_kurztext(ereignis)
    assert "#2349227" in text and "Drawdown-Schranke" in text
