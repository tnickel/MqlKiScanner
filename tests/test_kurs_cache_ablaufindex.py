"""Indexed expiry cleanup keeps the global boundary and original OHLC."""
import sqlite3

from mqlkiscanner.kurs_cache import AKTUALISIERUNG_SEKUNDEN, KursCache


def test_ablaufindex_bereinigt_alle_feeds_ohne_zukunft_oder_ohlc_zu_aendern(tmp_path):
    h = 3600
    start = 1_760_832_000 // h * h
    now = start + 100 * h
    cache = KursCache(tmp_path / "kursdaten.db")
    bars = [{"time": start + i * h, "open": 1.1, "high": 1.2,
             "low": 1.0, "close": 1.15} for i in (0, 2)]
    for feed in ("feed-a", "feed-b"):
        cache.speichere(feed, "EURUSD", start, start + 2 * h, bars, now=now - 1)

    expired = [("feed-a", "ALT", "H1", start, start, now - 100, now - 1),
               ("feed-b", "ALT", "H1", start, start, now - 100, now)]
    future = [("feed-a", "ZUKUNFT", "H1", start, start, now - 10, now + 0.5),
              ("feed-b", "ZUKUNFT", "H1", start, start, now - 10, now + 60)]
    with sqlite3.connect(cache.pfad) as conn:
        conn.execute("DELETE FROM h1_abrufversuche")
        conn.executemany("INSERT INTO h1_abrufversuche VALUES (?,?,?,?,?,?,?)", expired + future)
        before_bars = conn.execute("SELECT * FROM h1_bars ORDER BY feed,symbol,epoch").fetchall()
        indices = {row[1] for row in conn.execute("PRAGMA index_list(h1_abrufversuche)")}
        assert "h1_abrufversuche_gueltig_bis" in indices
        plan = " ".join(row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN DELETE FROM h1_abrufversuche WHERE gueltig_bis <= ?", (now,)))
        assert "SEARCH" in plan.upper()
        assert "h1_abrufversuche_gueltig_bis" in plan

    # An empty interior retry triggers the normal global cleanup and day TTL.
    cache.speichere("feed-a", "EURUSD", start + h, start + h, [], now=now)

    with sqlite3.connect(cache.pfad) as conn:
        assert conn.execute("SELECT * FROM h1_bars ORDER BY feed,symbol,epoch").fetchall() == before_bars
        assert conn.execute(
            "SELECT * FROM h1_abrufversuche WHERE symbol='ZUKUNFT' ORDER BY feed").fetchall() == future
        assert conn.execute("SELECT COUNT(*) FROM h1_abrufversuche WHERE symbol='ALT'").fetchone()[0] == 0
        assert conn.execute(
            "SELECT von,bis,geladen_am,gueltig_bis FROM h1_abrufversuche "
            "WHERE feed='feed-a' AND symbol='EURUSD'").fetchall() == [
                (start + h, start + h, now, now + AKTUALISIERUNG_SEKUNDEN)]

    # Reopening remains idempotent and preserves every original bar.
    KursCache(cache.pfad)
    with sqlite3.connect(cache.pfad) as conn:
        assert conn.execute("SELECT * FROM h1_bars ORDER BY feed,symbol,epoch").fetchall() == before_bars
