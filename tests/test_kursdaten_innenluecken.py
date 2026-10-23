"""Bounded H1 gap batching with a real temporary SQLite cache and a fake SDK."""
import sqlite3
from types import SimpleNamespace

from mqlkiscanner import kursdaten
from mqlkiscanner.kurs_cache import KursCache

H = 3600
START = 1_735_776_000


def _bar(i, close=1.1):
    return {"time": START + i * H, "open": 1., "high": 2., "low": .5, "close": close}


def _setup(monkeypatch, *, end=24, gaps=(2, 5, 10), answer="full"):
    clock = [START + 2000 * H]
    kd = kursdaten.KursDaten({"markt_terminal_pfad": "broker-a"})
    kd._aktiv = True
    calls = []

    def load(symbol, timeframe, von, bis):
        a, b = int(von.timestamp()), int(bis.timestamp())
        calls.append((symbol, a, b))
        if answer == "empty":
            return None
        if answer == "partial":
            return [_bar(5, 1.5)] if a <= START + 5 * H <= b else []
        return [_bar((t - START) // H, 1.5)
                for t in range(a, b + 1, H)]

    kd._mt5 = SimpleNamespace(
        account_info=lambda: SimpleNamespace(server="Broker-A"),
        symbol_select=lambda s, _: s == "EURUSD", copy_rates_range=load, TIMEFRAME_H1=1)
    monkeypatch.setattr(kursdaten.time, "time", lambda: clock[0])
    monkeypatch.setattr(kursdaten.time, "sleep", lambda _: None)
    cache = kd._kurs_cache = KursCache()
    feed = kd._feed_identitaet()[1]
    original = [_bar(i) for i in range(end + 1) if i not in gaps]
    cache.speichere(feed, "EURUSD", START, START + end * H, original,
                    now=clock[0] - 86401)
    return kd, cache, feed, calls, clock, original


def _ranges(calls):
    return [(a, b) for _, a, b in calls]


def test_multiple_internal_gaps_use_one_sdk_query_without_overwriting_bridge(monkeypatch):
    kd, cache, feed, calls, clock, original = _setup(monkeypatch)
    result = kd.hole_h1("EURUSD", START, START + 24 * H)
    assert _ranges(calls) == [(START + 2 * H, START + 10 * H)]
    actual = {b["time"]: b for b in result}
    for bar in original:
        assert actual[bar["time"]] == bar  # SDK returned different bridge OHLC.
    assert actual[START + 5 * H]["close"] == 1.5
    assert cache.lese(feed, "EURUSD", START, START + 24 * H, now=clock[0]) == result
    assert cache.fehlende_bereiche(feed, "EURUSD", START, START + 24 * H,
                                  now=clock[0] + 86401) == []


def test_combined_query_windows_stay_within_31_days(monkeypatch):
    kd, _, _, calls, _, _ = _setup(monkeypatch, end=1100, gaps=(2, 400, 800, 1000))
    assert len(kd.hole_h1("EURUSD", START, START + 1100 * H)) == 1101
    assert _ranges(calls) == [(START + 2 * H, START + 400 * H),
                              (START + 800 * H, START + 1000 * H)]
    assert all(b - a <= 31 * 86400 for a, b in _ranges(calls))


def test_empty_response_preserves_original_ttl_and_does_not_invent_coverage(monkeypatch):
    kd, cache, feed, calls, clock, original = _setup(monkeypatch, answer="empty")
    assert kd.hole_h1("EURUSD", START - 2 * H, START + 26 * H) == original
    # Empty SDK responses retain the original retry policy, once per query window.
    assert len(calls) == 12
    assert sorted(set(_ranges(calls))) == [
        (START - 2 * H, START - H), (START + 2 * H, START + 10 * H),
        (START + 25 * H, START + 26 * H)]
    with sqlite3.connect(cache.pfad) as conn:
        attempts = conn.execute("SELECT von,bis,gueltig_bis FROM h1_abrufversuche "
                                "ORDER BY von").fetchall()
    assert attempts == [
        (START - 2 * H, START - H, clock[0] + 60),
        (START + 2 * H, START + 2 * H, clock[0] + 86400),
        (START + 5 * H, START + 5 * H, clock[0] + 86400),
        (START + 10 * H, START + 10 * H, clock[0] + 86400),
        (START + 25 * H, START + 26 * H, clock[0] + 60)]
    assert cache.fehlende_bereiche(feed, "EURUSD", START - 2 * H, START + 26 * H,
                                  now=clock[0] + 60) == [
        (START - 2 * H, START - H), (START + 25 * H, START + 26 * H)]
    assert cache.fehlende_bereiche(feed, "EURUSD", START, START + 24 * H,
                                  now=clock[0] + 86400) == [
        (START + i * H, START + i * H) for i in (2, 5, 10)]
    assert cache.lese(feed, "EURUSD", START, START + 24 * H, now=clock[0]) == original


def test_partial_reply_fills_only_actual_bars_and_retries_remaining_gaps_after_ttl(monkeypatch):
    kd, cache, feed, calls, clock, original = _setup(monkeypatch, answer="partial")
    result = kd.hole_h1("EURUSD", START, START + 24 * H)
    assert len(result) == len(original) + 1
    assert _ranges(calls) == [(START + 2 * H, START + 10 * H)]
    assert cache.fehlende_bereiche(feed, "EURUSD", START, START + 24 * H,
                                  now=clock[0] + 86400) == [
        (START + i * H, START + i * H) for i in (2, 10)]


def test_old_provisional_bar_remains_a_separate_request(monkeypatch):
    kd, cache, feed, calls, clock, _ = _setup(monkeypatch)
    cache.speichere(feed, "EURUSD", START + 5 * H, START + 5 * H, [_bar(5)],
                    now=START + 6 * H - 1)
    assert cache.vorlaeufige_barzeiten(feed, "EURUSD", START, START + 24 * H) == {START + 5 * H}
    assert kd.hole_h1("EURUSD", START, START + 24 * H)
    assert _ranges(calls) == [(START + i * H, START + i * H) for i in (2, 5, 10)]
    assert cache.vorlaeufige_barzeiten(feed, "EURUSD", START, START + 24 * H) == set()


def test_open_tail_and_internal_gaps_keep_different_refresh_intervals(monkeypatch):
    kd, cache, feed, calls, clock, _ = _setup(monkeypatch)
    clock[0] = START + 48 * H + 100
    cache.speichere(feed, "EURUSD", START + 48 * H, START + 48 * H, [_bar(48)],
                    now=clock[0] - 61)
    with sqlite3.connect(cache.pfad) as conn:
        conn.execute("DELETE FROM h1_abrufversuche")
    assert kd.hole_h1("EURUSD", START, START + 48 * H)
    assert _ranges(calls) == [(START + 2 * H, START + 10 * H),
                              (START + 25 * H, START + 48 * H)]
    # Newly read open bar must refresh after 60 s, even with the historical batch.
    assert cache.fehlende_bereiche(feed, "EURUSD", START, START + 48 * H,
                                  now=clock[0] + 60) == [(START + 48 * H, START + 48 * H)]


def test_other_feed_cannot_supply_batch_boundaries_or_cached_bars(monkeypatch):
    kd, cache, feed, calls, clock, original = _setup(monkeypatch)
    kd._mt5.account_info = lambda: SimpleNamespace(server="Broker-B")
    result = kd.hole_h1("EURUSD", START, START + 24 * H)
    assert _ranges(calls) == [(START, START + 24 * H)]
    assert all(b["close"] == 1.5 for b in result)
    assert cache.lese(feed, "EURUSD", START, START + 24 * H, now=clock[0]) == original


def test_provisional_lookup_is_exactly_scoped_to_feed_symbol_and_window(monkeypatch):
    _, cache, feed, _, clock, _ = _setup(monkeypatch)
    cache.speichere(feed, "EURUSD", START + 5 * H, START + 5 * H, [_bar(5)],
                    now=START + 6 * H - 1)
    assert cache.vorlaeufige_barzeiten(feed + "other", "EURUSD", START, START + 24 * H) == set()
    assert cache.vorlaeufige_barzeiten(feed, "EURUSD+", START, START + 24 * H) == set()
    assert cache.vorlaeufige_barzeiten(feed, "eurusd", START, START + 24 * H) == set()
    assert cache.vorlaeufige_barzeiten(feed, "EURUSD", START + 6 * H, START + 24 * H) == set()


def test_query_with_no_two_final_boundaries_does_not_batch():
    ranges = [(START, START), (START + 2 * H, START + 2 * H)]
    assert kursdaten._buendle_innenluecken(ranges, [_bar(1)], START + 10 * H, set()) == [
        [ranges[0]], [ranges[1]]]


def test_unaligned_bar_timestamps_cannot_establish_h1_batch_boundaries():
    ranges = [(START + H, START + H), (START + 3 * H, START + 3 * H)]
    bars = [_bar(0), _bar(4)]
    bars[0]["time"] += 1
    assert kursdaten._buendle_innenluecken(ranges, bars, START + 10 * H, set()) == [
        [ranges[0]], [ranges[1]]]
