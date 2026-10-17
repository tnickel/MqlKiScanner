"""Kursanbieter mit echter Temp-SQLite und Fake-MT5; keine Live-Terminals."""
from types import SimpleNamespace

import pytest

from mqlkiscanner import kursdaten


START = 1_735_776_000  # historischer H1-Baranfang


def _anbieter(monkeypatch, *, server="Broker-A", terminal="broker-a"):
    kd = kursdaten.KursDaten({"markt_terminal_pfad": terminal})
    kd._aktiv = True
    abrufe = []
    zugelassen = {"EURUSD", "EURUSD+"}
    konto = SimpleNamespace(server=server)

    def laden(symbol, timeframe, von, bis):
        a, b = int(von.timestamp()), int(bis.timestamp())
        abrufe.append((symbol, a, b))
        return [{"time": t, "open": 1., "high": 2., "low": .5,
                 "close": 1.1 if konto.server == "Broker-A" else 1.2}
                for t in range(((a + 3599) // 3600) * 3600, b + 1, 3600)]

    kd._mt5 = SimpleNamespace(
        account_info=lambda: konto,
        symbol_select=lambda s, _: s in zugelassen,
        copy_rates_range=laden, TIMEFRAME_H1=1,
        shutdown=lambda: None)
    monkeypatch.setattr(kursdaten.time, "sleep", lambda _: None)
    return kd, abrufe, konto, zugelassen


def test_enthaltenes_fenster_und_neue_anbieterinstanz_ohne_erneutes_laden(monkeypatch):
    kd, abrufe, _, _ = _anbieter(monkeypatch)
    kd.hole_h1("EURUSD", START, START + 9 * 3600)
    assert len(abrufe) == 1
    innen = kd.hole_h1("EURUSD", START + 2 * 3600, START + 4 * 3600)
    assert [b["time"] for b in innen] == [START + i * 3600 for i in range(2, 5)]
    assert len(abrufe) == 1
    neu, neue_abrufe, _, _ = _anbieter(monkeypatch)
    assert neu.hole_h1("EURUSD", START, START + 9 * 3600)
    assert neue_abrufe == []


def test_erweiterung_laesst_vorhandenen_innenbereich_aus(monkeypatch):
    kd, abrufe, _, _ = _anbieter(monkeypatch)
    kd.hole_h1("EURUSD", START + 2 * 3600, START + 4 * 3600)
    abrufe.clear()
    bars = kd.hole_h1("EURUSD", START, START + 6 * 3600)
    assert len(bars) == 7
    assert len(abrufe) == 2
    assert all(b < START + 2 * 3600 or a > START + 4 * 3600
               for _, a, b in abrufe)


def test_serverwechsel_im_selben_terminal_verwendet_keine_alten_kurse(monkeypatch):
    kd, abrufe, konto, _ = _anbieter(monkeypatch)
    assert kd.hole_h1("EURUSD", START, START + 3600)[0]["close"] == 1.1
    konto.server = "Broker-B"
    assert kd.hole_h1("EURUSD", START, START + 3600)[0]["close"] == 1.2
    assert len(abrufe) == 2


def test_verlorener_servernachweis_springt_nicht_auf_alten_unbelegten_feed_zurueck(monkeypatch):
    kd, abrufe, konto, _ = _anbieter(monkeypatch, server="")
    preise = iter([1.1, 1.2, 1.3])

    def laden(*args):
        abrufe.append(args)
        return [{"time": START, "open": 1., "high": 2., "low": .5,
                 "close": next(preise)}]

    kd._mt5.copy_rates_range = laden
    assert kd.hole_h1("EURUSD", START, START)[0]["close"] == 1.1
    konto.server = "Broker-B"
    assert kd.hole_h1("EURUSD", START, START)[0]["close"] == 1.2
    konto.server = ""
    assert kd.hole_h1("EURUSD", START, START)[0]["close"] == 1.3
    assert len(abrufe) == 3


def test_unbelegter_feed_nach_trennen_nicht_als_aktuelle_verbindung_wiederverwenden(monkeypatch):
    kd, abrufe, _, _ = _anbieter(monkeypatch, server="")
    sdk = kd._mt5
    del sdk.account_info  # Alte SDK-Doppel ohne Serverlesung: nur Laufcache.
    assert kd.hole_h1("EURUSD", START, START)
    kd._trennen()
    kd._mt5, kd._aktiv = sdk, True
    assert kd.hole_h1("EURUSD", START, START)
    assert len(abrufe) == 2


def test_alias_wird_nach_echtem_terminalsymbol_wiederverwendet(monkeypatch):
    kd, abrufe, _, erlaubt = _anbieter(monkeypatch)
    erlaubt.remove("EURUSD+")
    assert kd.hole_h1("EURUSD+", START, START + 3600)
    assert kd.suffix_annahmen["EURUSD+"] == "EURUSD"
    assert kd.hole_h1("EURUSD", START, START + 3600)
    assert len(abrufe) == 1
    assert kd.terminal_herkunft["EURUSD"] == "broker-a"


def test_bekannter_feed_cache_funktioniert_ohne_aktive_sdk_verbindung(monkeypatch):
    kd, abrufe, _, _ = _anbieter(monkeypatch)
    kd.hole_h1("EURUSD", START, START + 9 * 3600)
    kd._trennen()
    bars = kd.hole_h1("EURUSD", START + 3600, START + 2 * 3600)
    assert len(bars) == 2
    assert len(abrufe) == 1


def test_defekte_cachedatei_verhindert_kursabruf_nicht(monkeypatch):
    from mqlkiscanner import config
    (config.DATA_DIR / "kursdaten.db").write_bytes(b"keine SQLite-Datenbank")
    kd, abrufe, _, _ = _anbieter(monkeypatch)
    assert kd.hole_h1("EURUSD", START, START + 3600)
    assert abrufe and kd._cache_defekt


def test_fehlender_servernachweis_schreibt_keine_persistenten_kurse(monkeypatch):
    from mqlkiscanner import config
    kd, abrufe, _, _ = _anbieter(monkeypatch, server="")
    assert kd.hole_h1("EURUSD", START, START + 3600)
    neu, neue_abrufe, _, _ = _anbieter(monkeypatch, server="")
    assert neu.hole_h1("EURUSD", START, START + 3600)
    assert abrufe and neue_abrufe
    assert not (config.DATA_DIR / "kursdaten.db").exists()


def test_gmt_fenster_und_exakte_inklusive_grenzen(monkeypatch):
    kd, abrufe, _, _ = _anbieter(monkeypatch)
    bars = kd.hole_h1("EURUSD", START + 1, START + 7200, gmt_offset_s=3600)
    assert [b["time"] for b in bars] == [START + 7200, START + 10800]
    assert len(abrufe) == 1


@pytest.mark.parametrize("luecke", [False, True])
def test_cache_aendert_weder_drawdown_noch_belastbarkeit_einer_rekonstruktion(
        monkeypatch, luecke):
    import datetime as dt
    from mqlkiscanner.forensics import equity_rekonstruktion as er

    start_dt = dt.datetime.fromtimestamp(START, tz=dt.timezone.utc).replace(tzinfo=None)
    trade = SimpleNamespace(
        symbol="EURUSD", direction="buy", volume=.01, entry_price=1., exit_price=1.,
        open_time=start_dt + dt.timedelta(minutes=10),
        close_time=start_dt + dt.timedelta(hours=6), net=0.)
    parsed = SimpleNamespace(trades=[trade], balances=[], pendings=[])
    monkeypatch.setattr(er, "_resolve_symbol", lambda *a, **kw: {
        "factor": 100_000., "quote": "USD"})
    werte = [1., .95, .90, .85, .95, 1., 1.]
    bars = [{"time": START + i * 3600, "open": v, "high": v, "low": v, "close": v}
            for i, v in enumerate(werte) if not (luecke and i in (2, 3))]
    referenz = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"EURUSD": bars}),
                              10_000., gmt_offset_h=0)
    erste, calls, _, _ = _anbieter(monkeypatch)
    erste._mt5.copy_rates_range = lambda *a: calls.append(a) or bars
    erg = er.rekonstruiere(parsed, erste, 10_000., gmt_offset_h=0)
    neu, neue_calls, _, _ = _anbieter(monkeypatch)
    wieder = er.rekonstruiere(parsed, neu, 10_000., gmt_offset_h=0)
    assert calls and not neue_calls
    for feld in ("status", "verlaesslich", "abdeckung_pct", "equity_dd_pct_raw",
                 "equity_dd_usd"):
        assert erg.get(feld) == referenz.get(feld) == wieder.get(feld)
    assert wieder["verlaesslich"] is (not luecke)
