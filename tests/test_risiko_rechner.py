# -*- coding: utf-8 -*-
"""Tests für den Max-Risiko-Rechner (Import-CSV → H1-Messung → PDF).

Alles gegen synthetische Bars/Trades — kein MT5, kein Netz. Kurs-Anbieter
und Lauf-Sperre werden gestubbt; die Messung selbst läuft über die echte
Produktionsstudie (equity_studie.studie).
"""
import contextlib
import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import kursdaten
from mqlkiscanner import risiko_rechner as rr

CSV_KOPF = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def _bars(symbol, start_dt, stunden, base=2000.0, schritt=7.0, band=0.4):
    bars = []
    for i in range(stunden):
        t = start_dt + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = base + schritt * i
        bars.append({"time": epoch, "open": close - band / 2, "high": close + band / 2,
                     "low": close - band / 2, "close": close})
    return bars


def _trade(symbol, richtung, open_dt, close_dt, entry, exit_, pnl=None, lots=0.01):
    return SimpleNamespace(
        open_time=open_dt, close_time=close_dt, direction=richtung, volume=lots,
        symbol=symbol, entry_price=entry, exit_price=exit_,
        net=pnl if pnl is not None else (exit_ - entry) * 100.0 * lots)


# ------------------------------------------------------------- eigene Zahlen

def test_closed_dd_anwendung_senkt_peak():
    """Nutzer-Regel: Auszahlung senkt den Peak — kein künstlicher DD."""
    start = dt.datetime(2026, 1, 1)
    trades = [
        _trade("XAUUSD", "buy", start, start + dt.timedelta(hours=1), 2000, 2010, pnl=200),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=3),
               start + dt.timedelta(hours=4), 2010, 2000, pnl=-100),
    ]
    fluesse = [SimpleNamespace(time=start - dt.timedelta(hours=1), amount=1000.0),
               SimpleNamespace(time=start + dt.timedelta(hours=2), amount=-600.0)]
    parsed = SimpleNamespace(trades=trades, balances=fluesse, costs=[])
    # 1000 → +200 = 1200 (Peak 1200); Auszahlung → Equity 600, Peak sinkt auf
    # 600 (nie drunter); Verlust → 500: DD = 100/600 = 16,67 % — OHNE
    # Peak-Senkung wäre der DD (1200-500)/1200 = 58,3 %.
    dd = rr.closed_dd(parsed, 1000.0)
    assert dd is not None
    assert abs(dd - 100.0 / 600.0 * 100) < 1e-9


@pytest.mark.parametrize('offset, capital, expected', [(-1, 900, 0), (0, 1000, 10), (1, 1000, 10)])
def test_closed_dd_kosten_vor_am_und_nach_ersten_open(offset, capital, expected):
    start = dt.datetime(2026, 1, 1)
    parsed = SimpleNamespace(
        trades=[_trade('XAUUSD', 'buy', start, start + dt.timedelta(hours=4), 2000, 2000, pnl=0)],
        balances=[], costs=[SimpleNamespace(time=start + dt.timedelta(hours=offset), amount=-100)])
    assert rr.closed_dd(parsed, capital) == pytest.approx(expected)


def test_closed_dd_kosten_sind_verlust_und_bekannte_kapitalfluesse_bleiben_einmalig():
    start = dt.datetime(2026, 1, 1)
    parsed = SimpleNamespace(
        trades=[_trade('XAUUSD', 'buy', start, start + dt.timedelta(hours=4), 2000, 2000, pnl=72)],
        balances=[SimpleNamespace(time=start-dt.timedelta(hours=1), amount=1000),
                  SimpleNamespace(time=start+dt.timedelta(hours=1), amount=90),
                  SimpleNamespace(time=start+dt.timedelta(hours=2), amount=-180)],
        costs=[SimpleNamespace(time=start-dt.timedelta(minutes=1), amount=-100),
               SimpleNamespace(time=start, amount=-90),
               SimpleNamespace(time=start+dt.timedelta(hours=3), amount=-72)])
    # Start900 includes deposit1000 and pre-open cost100 exactly once.
    # Open cost:810/peak900; deposit:900/peak900; withdrawal:720/peak720;
    # later cost:648/peak720 => maximum loss72/720 =10%.
    assert rr.closed_dd(parsed, 900) == pytest.approx(10)


def test_statistik_liefert_netto_serie_winrate():
    start = dt.datetime(2026, 1, 1)
    trades = [
        _trade("XAUUSD", "buy", start, start + dt.timedelta(hours=1), 2000, 2010, pnl=100),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=2),
               start + dt.timedelta(hours=3), 2010, 2000, pnl=-50),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=4),
               start + dt.timedelta(hours=5), 2010, 1990, pnl=-30),
    ]
    st = rr.statistik(SimpleNamespace(trades=trades, balances=[], costs=[]))
    assert st["n_trades"] == 3
    assert st["netto_gesamt"] == 20.0
    assert st["winrate"] == 1 / 3
    assert st["max_verlustserie"] == 2
    assert st["monats_netto"] == {"2026-01": 20.0}
    assert st["symbole"] == ["XAUUSD"]


# ------------------------------------------------------------- Berechnung

class _FakeAnbieter:
    def __init__(self, bars):
        self._bars = bars

    def starten(self):
        return True, "fake"

    def beenden(self):
        pass

    def hole_h1(self, symbol, von, bis, gmt_offset_s=0):
        return self._bars.get(symbol)


@pytest.mark.parametrize('capital', [1000.0, 1000.12345678])
def test_berechne_csv_mit_fake_kursen(tmp_path, monkeypatch, capital):
    from mqlkiscanner import equity_studie as es

    monkeypatch.setattr(es, "ermittle_gmt_je_symbol",
                        lambda *_: {"offsets": {"XAUUSD": 0}, "befunde": []})
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start - dt.timedelta(hours=16), 48)
    monkeypatch.setattr(kursdaten, "KursDaten", lambda _s: _FakeAnbieter({"XAUUSD": bars}))
    import mqlkiscanner.agenten.lock as lock_mod

    monkeypatch.setattr(lock_mod, "lauf_lock", lambda *_a, **_k: contextlib.nullcontext())

    csv = tmp_path / "trades.csv"
    csv.write_text(
        CSV_KOPF
        + "2026.01.01 00:01:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.01 05:01:00;2010;0;0;100\n"
        + "2026.01.01 06:01:00;Buy;0.01;XAUUSD;2010;0.01;2026.01.01 09:01:00;1990;0;0;-200\n",
        encoding="utf-8")
    meldungen = []

    def progress(a, t):
        meldungen.append(t)

    daten = rr.berechne_csv(csv, startkapital_manuell=capital, name="Testimport",
                            progress=progress)
    assert daten["status"] == "ok"
    k = daten["kennzahlen"]
    assert k["equity_dd_usd"] >= 0
    assert k["startkapital"] == round(capital, 2)
    assert daten['punkte'][0]['equity'] == capital
    assert daten["meta"]["name"] == "Testimport"
    assert daten["meta"]["startkapital_quelle"] == "manuell_eingabe"
    assert len(daten["meta"]["datei_sha256"]) == 64
    assert daten["statistik"]["n_trades"] == 2
    assert daten["statistik"]["netto_gesamt"] == -100.0
    assert daten['closed_dd_pct'] == pytest.approx(200 / (capital + 100) * 100, rel=1e-12)
    assert daten['closed_dd_unit'] == 'percent'
    assert daten['closed_dd_version'] == rr.CLOSED_DD_VERSION
    assert meldungen  # Fortschritt wurde gemeldet


def test_berechne_csv_ohne_kapitalbasis_verwendet_gekennzeichnetes_modell(tmp_path, monkeypatch):
    import mqlkiscanner.agenten.lock as lock_mod
    from mqlkiscanner import equity_studie as es

    monkeypatch.setattr(lock_mod, "lauf_lock", lambda *_a, **_k: contextlib.nullcontext())
    monkeypatch.setattr(es, "ermittle_gmt_je_symbol", lambda *_: {"offsets": {"XAUUSD": 0}, "befunde": []})
    bars = _bars("XAUUSD", dt.datetime(2025, 12, 31), 72)
    monkeypatch.setattr(kursdaten, "KursDaten", lambda _s: _FakeAnbieter({"XAUUSD": bars}))
    csv = tmp_path / "trades.csv"
    csv.write_text(
        CSV_KOPF
        + "2026.01.01 00:01:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.01 05:01:00;2010;0;0;100\n",
        encoding="utf-8")
    daten = rr.berechne_csv(csv)
    assert daten["kennzahlen"]["startkapital"] == 10000
    assert daten["meta"]["startkapital_quelle"] == "modell_fallback_10000"
    assert daten["kapitalbasis_modell"] is True
    assert daten["meta"]["kapitalbasis_details"]["unsicherheit"]


@pytest.mark.parametrize('manual', [0, -1, float('nan'), float('inf'), True])
def test_explizit_ungueltiges_startkapital_wird_nicht_als_modell_eingesetzt(tmp_path, monkeypatch, manual):
    import mqlkiscanner.agenten.lock as lock_mod
    monkeypatch.setattr(lock_mod, 'lauf_lock', lambda *_a, **_k: contextlib.nullcontext())
    monkeypatch.setattr(kursdaten, 'KursDaten', lambda _: pytest.fail('Invalid capital must stop before terminal access'))
    csv = tmp_path / 'manual.csv'
    csv.write_text(CSV_KOPF +
        '2026.01.01 00:01:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.01 05:01:00;2010;0;0;100\n',
        encoding='utf8')
    with pytest.raises(ValueError, match='manuelle.*positiv|manuelles.*positiv'):
        rr.berechne_csv(csv, startkapital_manuell=manual)


# ------------------------------------------------------------------- PDF

def _minimal_daten():
    return {
        "status": "ok",
        "punkte": [
            {"t": 1767225600, "equity": 1050.0, "realisiert": 1000.0,
             "floating": 50.0, "messpunkt": True, "flow_delta": 0},
            {"t": 1767229200, "equity": 900.0, "realisiert": 1000.0,
             "floating": -100.0, "messpunkt": True, "flow_delta": 0},
        ],
        "symbole": [{"symbol": "XAUUSD", "gmt_h": 0, "trefferquote": 100,
                     "status": "belegt", "hinweis": ""}],
        "kennzahlen": {"startkapital": 1000.0, "equity_dd_usd": 150.0,
                       "equity_dd_pct": 15.0, "abdeckung_pct": 99.0,
                       "verlaesslich": True, "floating_min_usd": -100.0,
                       "floating_min_t": 1767229200,
                       "dd_von": 1767225600, "dd_bis": 1767229200,
                       "dd_pct_max_rel": 15.0, "floating_max_usd": 50.0,
                       "unterwasser_tage_max": 0.5},
        "meta": {"name": "Testsignal", "quelle": "import", "trades_pfad": "x.csv",
                 "datei_sha256": "ab" * 32, "startkapital_quelle": "manuell_eingabe"},
        "statistik": {"n_trades": 2, "netto_gesamt": 50.0, "spanne_monate": 1.2,
                      "winrate": 0.5, "max_verlustserie": 1,
                      "monats_netto": {"2026-01": 50.0}, "symbole": ["XAUUSD"],
                      "erster_trade": "2026-01-01T00:00:00",
                      "letzter_trade": "2026-01-02T00:00:00"},
        "closed_dd_pct": 0.02,
    }


def test_pdf_entsteht_mit_warnhinweis(tmp_path):
    ziel = tmp_path / "bericht.pdf"
    pfad, seiten = rr.baue_pdf(_minimal_daten(), ziel)
    assert pfad == ziel and ziel.exists()
    assert seiten >= 3
    assert ziel.stat().st_size > 10_000
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    text = "".join((p.extract_text() or "") for p in PdfReader(str(ziel)).pages)
    assert "unterschätzt das Risiko massiv" in text  # Closed 2 % vs Max-DD 15 %
    assert "15,00 %" in text.replace(" 15,00 %", " 15,00 %") or "15,0" in text


def test_pdf_kennzeichnet_modellkapital_herkunft_unsicherheit_und_beleg(tmp_path):
    from pypdf import PdfReader
    daten = _minimal_daten()
    daten['meta'].update(startkapital_quelle='modell_lot_pnl', kapitalbasis_details={
        'quelle': 'modell_lot_pnl', 'modell': True, 'kapital': 1000,
        'unsicherheit': 'Begrenzte Volumenhistorie',
        'beleg': {'trades_sha256': 'ab'*32, 'spaetere_flows_bleiben_erhalten': True}})
    path, _ = rr.baue_pdf(daten, tmp_path / 'model.pdf')
    text = '\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
    normal = ' '.join(text.split())
    assert 'Virtuelle Modellstudie' in normal and 'keine nachgewiesenen Kontokennzahlen' in normal
    assert 'Lot-/PnL-Regression' in normal and 'Begrenzte Volumenhistorie' in normal
    assert 'ab'*32 in text.replace('\n', '')


def test_seite_rendered_app():
    from streamlit.testing.v1 import AppTest

    pfad = Path(__file__).resolve().parents[1] / "app_pages" / "risiko_rechner.py"
    at = AppTest.from_file(str(pfad), default_timeout=90)
    at.run()
    assert not at.exception
    assert any('Bei geschätztem Startkapital sind Drawdown und Renditen Modellwerte' in item.value
               and 'Methode und Unsicherheit stehen im Ergebnis' in item.value for item in at.markdown)
