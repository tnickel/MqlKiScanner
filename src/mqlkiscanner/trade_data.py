# -*- coding: utf-8 -*-
"""Trade-Daten-Payload fuer das LLM (Nutzer-Prinzip: "das LLM soll die
Strategie anhand der Trades ermitteln").

Die Engine berechnet ALLE Kennzahlen (AGENTS.md Design-Regel 1) und
stellt sie hier als kompaktes JSON zusammen — plus kuratierte
Beispiel-Trades (schlechteste, beste, laengste Verlustserie, groeszter
Korb), damit das LLM echtes Trade-Verhalten sieht, ohne dass tausende
Rohzeilen in den Kontext gehen. Zitieren der Zahlen erlaubt, eigene
Berechnungen nicht noetig.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from .models import ParsedExport, Trade
from .lot_format import format_lots, lot_histogram
from .symbols import fx_pip_size, normalize_symbol, symbol_class


def _distance_summary(symbol: str, distances: list[float]) -> dict:
    """Keep quote precision and units explicit, never mix instruments."""
    pip = fx_pip_size(symbol)
    decimals = (3 if pip == 0.01 else 5) if pip else (
        2 if symbol_class(symbol) in ("METAL", "INDEX") else None)

    def quote(value: float) -> float:
        rounded = round(value, decimals) if decimals is not None else 0.0
        # Preserve sub-tick input rather than turn a real loss into zero.
        return rounded or float(f"{value:.10g}")

    levels = Counter(quote(d) for d in distances).most_common(5)
    median = statistics.median(distances)
    maximum = max(distances)
    return {
        "symbol": symbol,
        "einheit": "Preiseinheiten",
        "anzahl": len(distances),
        "distanz_median": quote(median),
        "distanz_max": quote(maximum),
        "distanz_top_level": [{"punkte": level, "anzahl": count}
                              for level, count in levels],
        **({"pip_groesse": pip, "median_pips": round(median / pip, 3),
            "max_pips": round(maximum / pip, 3)} if pip else {}),
    }


def _trade_row(t: Trade) -> dict:
    return {
        "open": t.open_time.strftime("%Y-%m-%d %H:%M"),
        "close": t.close_time.strftime("%Y-%m-%d %H:%M"),
        "dir": "Buy" if t.direction == "Buy" else "Sell",
        "lots": t.volume,
        "symbol": t.symbol,
        "ep": t.entry_price,
        "xp": t.exit_price,
        "pnl": round(t.net, 2),
        "hold_h": round(t.holding_hours, 2),
        # F-9 (Review 29.09.): Anbieter-kontrollierter Freitext — gekuerzt
        # und von Steuerzeichen befreit in den Prompt (Prompt-Groesse und
        # Injection-Flaeche begrenzen; die Ampel selbst rechnet im Code).
        **({"exit": _comment_kompakt(t.comment)} if t.comment else {}),
    }


def _comment_kompakt(comment: str, max_zeichen: int = 80) -> str:
    """Anbieter-Kommentar fuer den LLM-Prompt: druckbare Zeichen, begrenzt."""
    text = "".join(ch for ch in str(comment)
                   if ch.isprintable() and ch not in "\r\n\t")
    return text[:max_zeichen]


def _rekonstruiere_koerbe(trades) -> list[dict]:
    """Positionskörbe je Symbol: zusammenhängende Overlap-Episoden.

    Ein Korb = Gruppe von Trades desselben Symbols, deren Haltezeiten
    (Open bis Close) sich überschneiden (verbundene Intervalle). Teil-
    abschlüsse und Gegenpositionen bleiben im Korb. Rein rechnerisch —
    die Deutung (Grid, Recovery, Verlustmanagement) macht die KI.
    """
    je_symbol: dict[str, list] = defaultdict(list)
    for t in trades:
        je_symbol[t.symbol].append(t)
    koerbe: list[dict] = []
    for symbol, liste in sorted(je_symbol.items()):
        liste.sort(key=lambda t: (t.open_time, t.close_time))
        aktuell: dict | None = None
        for t in liste:
            if aktuell is None or t.open_time > aktuell["ende"]:
                aktuell = {"symbol": symbol, "start": t.open_time,
                           "ende": t.close_time, "trades": [t]}
                koerbe.append(aktuell)
            else:
                aktuell["trades"].append(t)
                if t.close_time > aktuell["ende"]:
                    aktuell["ende"] = t.close_time
    return koerbe


def _verlustkorb_befund(koerbe: list[dict]) -> dict:
    """§3.1 des Tiefenanalyse-Prompts (20.10.): Verlustkörbe als CODE-Befund.

    Alle negativ abgeschlossenen Körbe mit Zusammenfassung (Median/Ø/max)
    und Tabelle der 30 schlimmsten — Grundlage für die KI-Deutung, nicht
    deren Ersatz. Zwischenzeitliches Floating ist hier NICHT enthalten
    (dafür fehlen Kurse); das benennt der Prompt ausdrücklich.
    """
    ergebnisse = [{
        "symbol": k["symbol"],
        "start": k["start"].strftime("%Y-%m-%d %H:%M"),
        "ende": k["ende"].strftime("%Y-%m-%d %H:%M"),
        "positionen": len(k["trades"]),
        "netto": round(sum(t.net for t in k["trades"]), 2),
    } for k in koerbe]
    verlierer = sorted((e for e in ergebnisse if e["netto"] < 0),
                       key=lambda e: e["netto"])
    betraege = [e["netto"] for e in verlierer]
    return {
        "zusammenfassung": {
            "koerbe_gesamt": len(ergebnisse),
            "koerbe_verlierend": len(verlierer),
            "verlust_median_usd": round(statistics.median(betraege), 2) if betraege else None,
            "verlust_avg_usd": round(statistics.mean(betraege), 2) if betraege else None,
            "verlust_max_usd": round(min(betraege), 2) if betraege else None,
            "abgrenzung": ("Overlap-Cluster je Symbol (verbundene Haltezeiten); "
                           "zwischenzeitliches Floating nicht enthalten"),
        },
        "tabelle_schlimmste_30": verlierer[:30],
    }


def _kompakt_zeile(t: Trade) -> str:
    return (f"{t.open_time:%Y-%m-%d %H:%M} {'B' if t.direction == 'Buy' else 'S'}"
            f" {t.volume:g} {t.symbol} {t.entry_price}->{t.exit_price}"
            f" {t.net:+.2f}")


def build_trade_payload(parsed: ParsedExport, max_samples: int = 12,
                         volle_liste_max_trades: int = 0) -> dict:
    """Engine-berechnetes Trade-Level-JSON fuer die LLM-Analyse.

    volle_liste_max_trades > 0: Bei kleinen Exporten (bis zur Grenze)
    wird die KOMPAKTE vollständige Trade-Liste mitgegeben (Tiefen-
    analyse, Nutzer-Wunsch 20.10.) — große Historien bleiben auf den
    Aggregaten (Kontext-/Kostengrenze; größter Cache-Export ~10 MB).
    """
    trades = parsed.trades
    if not trades:
        return {"fehler": "keine Trades"}

    by_open = sorted(trades, key=lambda t: t.open_time)
    by_close = sorted(trades, key=lambda t: t.close_time)
    wins = [t for t in trades if t.profit > 0]
    # F4-Konsistenz (Review-Handoff 29.09.): Breakeven ist kein Verlust —
    # dieselbe Definition wie stats.py/stops.py (Serie bricht ab wie bei Gewinn)
    losses = [t for t in trades if t.profit < 0]
    durs = sorted(t.holding_hours for t in trades)

    # --- Monatskurve (Netto je Close-Monat)
    monthly: dict[str, float] = defaultdict(float)
    for zeit, netto in parsed.realized_events():
        monthly[zeit.strftime("%Y-%m")] += netto

    # --- Pro Symbol
    per_symbol = []
    for sym in sorted({t.symbol for t in trades}):
        sub = [t for t in trades if t.symbol == sym]
        sw = [t for t in sub if t.profit > 0]
        per_symbol.append({
            "symbol": sym, "trades": len(sub),
            "netto": round(sum(t.net for t in sub), 2),
            "winrate_pct": round(len(sw) / len(sub) * 100, 1),
            "lots": (f"{format_lots(min(t.volume for t in sub))}-"
                     f"{format_lots(max(t.volume for t in sub))}"),
            "median_hold_h": round(statistics.median(t.holding_hours for t in sub), 2),
        })

    # --- Laengste Verlustserie (chronologisch nach Close)
    streak, best_len, best_window = 0, 0, []
    window = []
    for t in by_close:
        if t.profit < 0:  # F4: Breakeven unterbricht die Serie wie ein Gewinn
            streak += 1
            window.append(t)
            if streak > best_len:
                best_len, best_window = streak, list(window)
        else:
            streak, window = 0, []

    # --- Groeszter Korb (identischer Close-Zeitpunkt)
    by_exit: dict[str, list] = defaultdict(list)
    for t in trades:
        by_exit[t.close_time.strftime("%Y%m%d%H%M%S")].append(t)
    biggest = max(by_exit.values(), key=len, default=[])

    # --- Verlustdistanzen: getrennt je Instrument in dessen Preiseinheiten
    distances_by_symbol: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        distance = t.loss_distance()
        if distance is not None:
            distances_by_symbol[normalize_symbol(t.symbol)].append(distance)
    distance_summaries = [_distance_summary(sym, sorted(values))
                          for sym, values in sorted(distances_by_symbol.items())]
    single_distance = distance_summaries[0] if len(distance_summaries) == 1 else {}

    # --- Beispiel-Trades: schlechteste + beste + Serienfenster + erster Handelstag
    worst = sorted(trades, key=lambda t: t.profit)[:max_samples]
    best = sorted(trades, key=lambda t: -t.profit)[:max(4, max_samples // 2)]
    first_day = [t for t in by_open
                 if t.open_time.date() == by_open[0].open_time.date()][:10]

    return {
        "meta": {
            "trades": len(trades),
            "zeitraum": f"{by_open[0].open_time:%Y-%m-%d} bis {by_close[-1].close_time:%Y-%m-%d}",
            "wins": len(wins), "losses": len(losses),
            "winrate_pct": round(len(wins) / len(trades) * 100, 1),
            "netto_gesamt": round(parsed.net_total, 2),
            "kontokosten_anzahl": len(parsed.costs),
            "kontokosten_usd": round(sum(c.amount for c in parsed.costs), 2),
            "avg_win": round(statistics.mean(t.profit for t in wins), 2) if wins else None,
            "avg_loss": round(statistics.mean(t.profit for t in losses), 2) if losses else None,
            "halt_h_median": round(statistics.median(durs), 2),
            "halt_h_p90": round(durs[int(len(durs) * 0.9)], 2),
            "halt_h_max": round(durs[-1], 1),
        },
        "monatskurve": [{"monat": m, "netto": round(v, 2)} for m, v in sorted(monthly.items())],
        "pro_symbol": per_symbol,
        "lots_verteilung": lot_histogram(t.volume for t in trades),
        "einstiegsstunden_top": dict(sorted(Counter(t.open_time.hour for t in trades).items(),
                                            key=lambda kv: -kv[1])[:8]),
        "verluste": {
            "worst": round(min(t.profit for t in trades), 2),
            "median": round(statistics.median(t.profit for t in losses), 2) if losses else None,
            # Existing scalar keys remain usable for a single instrument only.
            "distanz_median": single_distance.get("distanz_median"),
            "distanz_max": single_distance.get("distanz_max"),
            "distanz_top_level": single_distance.get("distanz_top_level", []),
            "distanz_symbol": single_distance.get("symbol"),
            "distanz_pro_symbol": distance_summaries,
        },
        "verlustserie_max": {
            "laenge": best_len,
            "summe": round(sum(t.profit for t in best_window), 2),
            "zeitraum": (f"{best_window[0].open_time:%Y-%m-%d} bis "
                         f"{best_window[-1].close_time:%Y-%m-%d}") if best_window else None,
            "trades": [_trade_row(t) for t in best_window[:25]],
        },
        "groesster_korb": {
            "positionen": len(biggest),
            "netto": round(sum(t.net for t in biggest), 2),
            "legs": [_trade_row(t) for t in
                     sorted(biggest, key=lambda t: t.open_time)[:20]],
        },
        "beispiel_trades": {
            "schlechteste": [_trade_row(t) for t in worst],
            "beste": [_trade_row(t) for t in best],
            "erster_handelstag": [_trade_row(t) for t in first_day],
        },
        # Zeit-/Richtungs-Verteilung (alle Trades; Uhrzeiten wie exportiert,
        # also Brokerzeit — NICHT als deutsche Lokalzeit ausgeben)
        "zeitverteilung": {
            "wochentage_mo_bis_so": [Counter(t.open_time.weekday() for t in trades)[i]
                                     for i in range(7)],
            "stunden_top": dict(sorted(Counter(t.open_time.hour for t in trades).items(),
                                       key=lambda kv: -kv[1])[:8]),
            "long": sum(1 for t in trades if t.direction == "Buy"),
            "short": sum(1 for t in trades if t.direction != "Buy"),
            "halt_h_median": round(statistics.median(durs), 2),
        },
        # §3.1 Korb-Verlustforensik (CODE-berechnet über ALLE Körbe)
        "verlustkoerbe": _verlustkorb_befund(_rekonstruiere_koerbe(trades)),
        # Vollständige Liste NUR bei kleinen Exporten (kompakt, je Zeile
        # ~50 Zeichen); sonst bewusst weggelassen — Aggregate decken alles ab.
        **({"volle_tradeliste": [_kompakt_zeile(t) for t in by_open]}
           if volle_liste_max_trades and len(trades) <= volle_liste_max_trades
           else {"volle_tradeliste": None}),
    }
