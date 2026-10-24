# -*- coding: utf-8 -*-
"""Unabhängiger Kontrollscan — grafischer PDF-Bericht (doc/25).

Eigene Rechnung aus den Roh-Trades (trade_files), eigene Bewertung nach
RetDD (Ertrag muss das Risiko bezahlen; hohe DD schließt niemanden aus,
kurze Historie wird gekennzeichnet), erst danach Gegencheck gegen die
Engine-Ampel. Projekt-Code wird nicht verändert; DB nur read-only.

Aufruf:  python scripts/kontrollscan_bericht.py
Ausgabe: data/reports/kontrollscan_<JJJJ-MM-TT>.pdf
         .tmp/kontrollscan_ergebnis.json (Transparenz-Dump)
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DB_PFAD = ROOT / "data" / "mqlkiscanner.db"
REPORT_DIR = ROOT / "data" / "reports"
TMP_DIR = ROOT / ".tmp"
JAHR_TAGE = 365.2425
MONAT_TAGE = JAHR_TAGE / 12.0
INAKTIV_TAGE = 60
MIN_HISTORIE_MONATE = 3.0
MARTINGALE_MEDIAN_SCHWELLE = 1.3
MIN_BASIS_USD = 100.0

# ---------------------------------------------------------------- Grundlagen


def lade_grundlagen() -> dict:
    settings = json.loads((ROOT / "config" / "app_settings.json").read_text(encoding="utf-8"))
    dd_schranke = float(settings.get("schranke_eq_dd_pct") or 50.0)
    min_calmar = float(settings.get("min_calmar_jahr") or 3.0)
    bekannt = json.loads((ROOT / "data" / "known_signals.json").read_text(encoding="utf-8"))
    ausgeschlossen = {int(e["id"]) for e in bekannt.get("ausgeschlossen", []) if e.get("id") is not None}

    import sqlite3
    con = sqlite3.connect(f"file:{DB_PFAD}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    files = {}
    trade_shas = {}
    for r in con.execute(
        """SELECT t.signal_ref AS ref, t.path, t.fetched_at, t.sha256 FROM trade_files t
           WHERE t.fetched_at = (SELECT MAX(t2.fetched_at) FROM trade_files t2
                                 WHERE t2.signal_ref = t.signal_ref)"""
    ):
        alt = files.get(r["ref"])
        if alt is None or r["path"] > alt[0]:
            files[r["ref"]] = (r["path"], r["fetched_at"])
            trade_shas[r["ref"]] = r["sha256"]
    ident = {}
    for r in con.execute("SELECT signal_ref AS ref, externe_id, quellen_uid FROM signal_identitaeten"):
        ident.setdefault(r["ref"], (r["externe_id"], r["quellen_uid"]))
    meta = {}
    for tabelle in ("katalog_signale", "signals"):
        for r in con.execute(
            f"""SELECT signal_ref AS ref, name, quelle, platform, url, abonnenten, wochen
                FROM {tabelle}"""
        ):
            meta.setdefault(r["ref"], dict(r))
    # Read native facts only, before the independent assessment. Stored
    # forensic results, model capital and engine ratings are not inputs.
    for r in con.execute("SELECT signal_ref AS ref, stats_json FROM signals"):
        if r["ref"] not in meta:
            continue
        raw = json.loads(r["stats_json"] or "{}")
        if not isinstance(raw, dict):
            raise ValueError(f"Ungueltige Quellenmetadaten fuer ref {r['ref']}")
        meta[r["ref"]]["quellen_stats"] = {key: raw[key] for key in (
            "account_currency", "initial_deposit_usd", "broker_server", "trade_money_currency") if key in raw}
    con.close()
    for ref, (ext, uid) in ident.items():
        if ref in meta:
            meta[ref].update(externe_id=ext, quellen_uid=uid)
    return {
        "dd_schranke": dd_schranke,
        "min_calmar": min_calmar,
        "ausgeschlossen": ausgeschlossen,
        "files": files,
        "trade_shas": trade_shas,
        "meta": meta,
    }


# ---------------------------------------------------------- eigene Rechnung


def monatsfaktoren(events: list, startkapital: float):
    """TWR-Monatsfaktoren aus chronologischen Ereignissen (trade/flow).

    Teilperioden enden an jedem Kontofluss; Monatsrendite = Produkt der
    Teilfaktoren des Monats. Rückgabe: (Faktoren je Monat, ungültige Monate).
    """
    faktoren: dict[tuple[int, int], float] = {}
    ungueltig: set[tuple[int, int]] = set()
    basis = float(startkapital)
    pnl = 0.0
    cur_key = None

    def falten(key):
        nonlocal basis, pnl
        if key is None:
            return
        if basis > 0:
            faktoren[key] = faktoren.get(key, 1.0) * (1.0 + pnl / basis)
        else:
            ungueltig.add(key)
        basis += pnl
        pnl = 0.0

    for zeit, delta, art in events:
        key = (zeit.year, zeit.month)
        if key != cur_key:
            falten(cur_key)
            cur_key = key
        if art == "flow":
            falten(cur_key)  # Teilperiode bis zum Kontofluss schließen
            basis += delta
        else:
            pnl += delta
    falten(cur_key)
    return faktoren, ungueltig


def monatsreihe(a: "datetime", b: "datetime"):
    from datetime import date

    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield (y, m)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def eigene_analyse(pe, *, stats=None, kontext=None, broker=None, calibration=None,
                   kapitalentscheidung=None) -> dict:
    """Alle eigenen Kennzahlen aus einem geparsten Export (neutrale Daten)."""
    trades = sorted(pe.trades, key=lambda t: (t.close_time, t.open_time))
    if not trades:
        raise ValueError("keine Trade-Zeilen")
    fluesse = [(b.time, float(b.amount)) for b in (pe.balances or [])]
    kosten = [(c.time, float(c.amount)) for c in (pe.costs or [])]
    erster_open = min(t.open_time for t in trades)
    letzter_close = max(t.close_time for t in trades)
    from mqlkiscanner import kapitalbasis
    decision = kapitalentscheidung if kapitalentscheidung is not None else kapitalbasis.aufloesen(
        pe, stats=stats, kontext=kontext, broker=broker, calibration=calibration)
    vorstart_flows = math.fsum(a for z, a in fluesse if z <= erster_open)
    if not math.isclose(vorstart_flows + float(decision["injektion_usd"]),
                        float(decision["kapital"]), rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("Kapitalentscheidung passt nicht zu den Vorstartbuchungen des Exports")
    startkapital = float(decision["kapital"]) + math.fsum(a for z, a in kosten if z < erster_open)
    basis_verwendbar = decision.get("gueltig") is True and startkapital > 0
    basis_bekannt = basis_verwendbar and not decision.get("modell")

    events = [(t.close_time, float(t.net), "trade") for t in trades]
    events += [(z, a, "trade") for z, a in kosten if z >= erster_open]
    events += [(z, a, "flow") for z, a in fluesse if z > erster_open]
    events.sort(key=lambda e: (e[0], 0 if e[2] == "flow" else 1))

    # Eigener DD der geschlossenen Kurve. Nutzer-Regel: Einzahlung hebt den
    # Peak, Auszahlung senkt ihn mit — nie unter den Kontostand.
    max_dd_pct = None
    max_dd_usd = None
    if basis_verwendbar:
        equity = startkapital
        peak = startkapital
        max_dd_usd = 0.0
        max_dd_pct = 0.0
        for _zeit, delta, art in events:
            if art == "flow":
                equity += delta
                peak = max(equity, peak + delta)
            else:
                equity += delta
                peak = max(peak, equity)
            if peak > 0:
                max_dd_usd = max(max_dd_usd, peak - equity)
                max_dd_pct = max(max_dd_pct, (peak - equity) / peak)

    monatsrenditen: dict[str, float] = {}
    cagr = None
    retdd_monat = None
    retdd_jahr = None
    ertrag_monat_geom_pct = None
    n_monate = None
    if basis_verwendbar:
        faktoren, ungueltig = monatsfaktoren(events, startkapital)
        alle = list(monatsreihe(erster_open, letzter_close))
        n_monate = len(alle)
        total_f = 1.0
        gueltig = True
        for key in alle:
            if key in ungueltig:
                gueltig = False
                continue
            f = faktoren.get(key, 1.0)
            monatsrenditen[f"{key[0]:04d}-{key[1]:02d}"] = f - 1.0
            total_f *= f
        if gueltig and total_f > 0 and n_monate > 0:
            span_tage = max((letzter_close - erster_open).total_seconds() / 86400.0, 1.0)
            cagr = total_f ** (JAHR_TAGE / span_tage) - 1.0
            geom_m = total_f ** (1.0 / n_monate) - 1.0
            ertrag_monat_geom_pct = geom_m * 100.0
            if max_dd_pct is not None and max_dd_pct > 0:
                retdd_monat = geom_m / max_dd_pct
                retdd_jahr = cagr / max_dd_pct

    serie = 0
    max_serie = 0
    gewinne, verluste = [], []
    for t in trades:
        if t.net < 0:
            serie += 1
            max_serie = max(max_serie, serie)
            verluste.append(t.net)
        else:
            serie = 0
            gewinne.append(t.net)
    winrate = len(gewinne) / len(trades)
    avg_gewinn = statistics.fmean(gewinne) if gewinne else None
    avg_verlust = statistics.fmean(verluste) if verluste else None

    ratios = []
    max_sprung = None
    for a, b in zip(trades, trades[1:]):
        if a.net < 0 and a.volume and b.volume:
            r = b.volume / a.volume
            ratios.append(r)
            max_sprung = r if max_sprung is None else max(max_sprung, r)
    martingale_median = statistics.median(ratios) if ratios else None
    martingale_flag = martingale_median is not None and martingale_median > MARTINGALE_MEDIAN_SCHWELLE

    punkte = []
    for t in trades:
        v = 1 if (t.direction or "").lower().startswith("b") else -1
        punkte.append((t.open_time, 1, v * t.volume))
        punkte.append((t.close_time, 0, v * t.volume))
    punkte.sort(key=lambda p: (p[0], p[1]))  # Schluss vor Eröffnung bei gleicher Zeit
    n_offen, lots_offen = 0, 0.0
    peak_pos, peak_lots, peak_abs_lots = 0, 0.0, 0.0
    for _z, art, lv in punkte:
        if art == 1:
            n_offen += 1
            lots_offen += lv
        else:
            n_offen -= 1
            lots_offen -= lv
        if n_offen > peak_pos:
            peak_pos = n_offen
            peak_lots = lots_offen
        peak_abs_lots = max(peak_abs_lots, abs(lots_offen))

    historie_monate = (letzter_close - erster_open).total_seconds() / 86400.0 / MONAT_TAGE
    netto = math.fsum([*(float(t.net) for t in trades), *(a for _, a in kosten)])
    monate_fuer_netto = n_monate if n_monate else (historie_monate if historie_monate > 0 else None)
    return {
        "n_trades": len(trades),
        "netto_gesamt": netto,
        "ertrag_monat_geom_pct": ertrag_monat_geom_pct,
        "netto_monat_usd": (netto / monate_fuer_netto) if monate_fuer_netto else None,
        "startkapital": startkapital,
        "basis_bekannt": basis_bekannt,
        "basis_verwendbar": basis_verwendbar,
        "kapitalbasis_modell": bool(decision.get("modell")),
        "kapitalbasis_quelle": decision["quelle"],
        "kapitalbasis_details": decision,
        "max_dd_pct": max_dd_pct,
        "max_dd_usd": max_dd_usd,
        "cagr": cagr,
        "retdd_monat": retdd_monat,
        "retdd_jahr": retdd_jahr,
        "n_monate": n_monate,
        "monatsrenditen": monatsrenditen,
        "max_verlustserie": max_serie,
        "winrate": winrate,
        "avg_gewinn": avg_gewinn,
        "avg_verlust": avg_verlust,
        "martingale_median": martingale_median,
        "martingale_flag": bool(martingale_flag),
        "max_lot_sprung": max_sprung,
        "peak_positionen": peak_pos,
        "peak_netto_lots": peak_lots,
        "peak_abs_lots": peak_abs_lots,
        "symbole": sorted({t.symbol for t in trades}),
        "erster_trade": erster_open.isoformat(),
        "letzter_trade": letzter_close.isoformat(),
        "historie_monate": historie_monate,
    }


# ------------------------------------------------------------- Bewertung


def bewerte(erg: dict, grund: dict, ref: int, heute: datetime) -> dict:
    """K.o.s und Kennzeichnungen — Engine bleibt außen vor."""
    kos = []
    meta = erg.get("meta") or {}
    ext = meta.get("externe_id")
    try:
        if ext is not None and int(ext) in grund["ausgeschlossen"]:
            kos.append("Ausschlussliste (known_signals.json)")
    except (TypeError, ValueError):
        pass
    if erg.get("martingale_flag"):
        med = erg.get("martingale_median")
        kos.append(f"Martingale-Signatur (Median {med:.2f})" if med is not None else "Martingale-Signatur")
    letzter = datetime.fromisoformat(erg["letzter_trade"])
    tage = (heute - letzter).days
    if tage > INAKTIV_TAGE:
        kos.append(f"inaktiv (letzter Trade {tage} Tage zurück)")
    if erg.get("basis_verwendbar") and (erg.get("startkapital") or 0) < MIN_BASIS_USD:
        kos.append(f"Mikrobasis ({erg['startkapital']:.0f} USD) — Prozent- und RetDD-Werte nicht belastbar")
    erg["ref"] = ref
    erg["ko_kriterien"] = kos
    erg["kurze_historie"] = (erg.get("historie_monate") or 0) < MIN_HISTORIE_MONATE
    erg["kleiner_dd_nenner"] = bool(
        erg.get("basis_verwendbar") and erg.get("max_dd_pct") is not None and erg["max_dd_pct"] < 0.01
    )
    # Models are measurable but remain explicitly hypothetical, never known
    # account capital. H1 availability remains a separate condition.
    # bewertbar wird erst NACH der H1-Messung entschieden (nur belastbarer
    # Max-DD inkl. offener Trades zählt, Nutzer-Regel 21.10.).
    erg["pruefbar"] = erg.get("basis_verwendbar") and not kos and erg.get("cagr") is not None
    erg["bewertbar"] = False
    return erg


# ------------------------------------------------------- Gegencheck Engine


class CacheKursDaten:
    """Offline-Kursquelle für die H1-Rekonstruktion: liest vorhandene H1-Bars
    aus data/kursdaten.db (read-only). Kein Terminal, kein Fenster, kein
    Nachladen — Symbole ohne Cache-Bars bleiben ehrlich ohne Kurse.

    Je Symbol+Fenster wird der Feed mit der besten Abdeckung gewählt; alle
    Bars eines Symbols kommen damit konsistent aus EINEM Feed (Voraussetzung
    für den Auto-GMT-Preisabgleich der Rekonstruktion).
    """

    def __init__(self):
        self._con = sqlite3.connect(f"file:{ROOT / 'data' / 'kursdaten.db'}?mode=ro", uri=True)

    def hole_h1(self, symbol, von_epoch, bis_epoch, gmt_offset_s=0):
        from mqlkiscanner.symbols import normalize_symbol

        von = int(von_epoch) + int(gmt_offset_s or 0)
        bis = int(bis_epoch) + int(gmt_offset_s or 0)
        if von > bis:
            return None
        kandidaten: list[str] = []
        for s in (symbol, normalize_symbol(symbol)):
            if s and s not in kandidaten:
                kandidaten.append(s)
        for k in kandidaten:
            row = self._con.execute(
                "SELECT feed FROM h1_bars WHERE symbol=? AND epoch BETWEEN ? AND ? "
                "GROUP BY feed ORDER BY COUNT(*) DESC, feed LIMIT 1",
                (k, von, bis),
            ).fetchone()
            if not row:
                continue
            rows = self._con.execute(
                "SELECT epoch, open, high, low, close FROM h1_bars "
                "WHERE feed=? AND symbol=? AND zeitrahmen='H1' "
                "AND epoch BETWEEN ? AND ? AND abgeschlossen=1 ORDER BY epoch",
                (row[0], k, von, bis),
            ).fetchall()
            if rows:
                return [
                    {"time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4]}
                    for r in rows
                ]
        return None


def h1_max_dd(pe, startkapital: float, provider: CacheKursDaten, *, broker=None) -> dict:
    """Max-DD inkl. offener (floating) Trades über die PRODUKTIONSfunktion
    forensics/equity_rekonstruktion.rekonstruiere — hier als eigene Rechnung
    mit eigenem Startkapital und Offline-Cache-Kursen."""
    from mqlkiscanner.forensics.equity_rekonstruktion import rekonstruiere

    try:
        r = rekonstruiere(pe, provider, startkapital, broker=broker)
    except Exception as exc:  # noqa: BLE001 — Fehler = Datenqualitätsbefund
        return {"h1_status": "fehler", "h1_grund": f"{type(exc).__name__}: {exc}"[:140]}
    return {
        "h1_status": r.get("status"),
        "h1_dd_pct_raw": r.get("equity_dd_pct_raw"),
        "h1_dd_pct": r.get("equity_dd_pct"),
        "h1_abdeckung_pct": r.get("abdeckung_pct"),
        "h1_gmt_h": r.get("gmt_offset_h"),
        "h1_grund": r.get("grund"),
    }


def engine_werte() -> dict:
    from mqlkiscanner import pipeline

    res = pipeline.results_from_db(materialize_pdfs=False)
    out = {}
    for r in res:
        kanaele = [r.trading_dd_pct, r.dd_equity_pct, r.dd_balance_pct,
                   r.monitor_trade_eq_dd_pct, r.equity_dd_rekonstruiert_pct]
        vorhandene = [v for v in kanaele if v is not None]
        out[r.signal_ref] = {
            "name": r.name,
            "ampel": r.ampel,
            "engine_calmar": r.retdd_jahr,
            "engine_calmar_vorbehalt": r.retdd_jahr_vorbehalt,
            "engine_dd_reko": r.equity_dd_rekonstruiert_pct,
            "engine_dd_max": max(vorhandene) if vorhandene else None,
            "forensik_aktualisiert": r.forensik_aktualisiert,
        }
    return out


# ----------------------------------------------------------------- Hauptlauf


def main() -> None:
    heute = datetime.now()
    grund = lade_grundlagen()
    from mqlkiscanner.parser import load_export

    roh: dict[int, dict] = {}
    fehler: dict[int, str] = {}
    provider = CacheKursDaten()
    n_h1 = 0
    for ref, (pfad, fetched) in sorted(grund["files"].items()):
        try:
            meta = grund["meta"].get(ref, {})
            native_stats = meta.get("quellen_stats") or {}
            # Actual source profiles require currency evidence; the pure
            # analysis API separately retains the generic USD-input contract.
            if str(native_stats.get("account_currency") or "").strip().upper() != "USD":
                raise ValueError("Native USD-Kontowaehrung nicht belegt; keine USD-Kontokennzahlen")
            trade_sha = sha256(Path(pfad).read_bytes()).hexdigest()
            expected_sha = grund.get("trade_shas", {}).get(ref)
            if expected_sha and trade_sha != expected_sha:
                raise ValueError("Trade-Datei passt nicht zur gespeicherten SHA-256")
            pe = load_export(pfad)
            broker = native_stats.get("broker_server")
            erg = eigene_analyse(pe, stats=native_stats, broker=broker,
                                 kontext={"signal_ref": ref, "id": meta.get("externe_id"),
                                          "quellen_uid": meta.get("quellen_uid"), "quelle": meta.get("quelle"),
                                          "trades_sha256": trade_sha})
            erg["fetched_at"] = fetched
            erg["meta"] = meta
            roh[ref] = bewerte(erg, grund, ref, heute)
            # H1-Reko auch fuer klar markierte Modelle, kein K.o.
            if roh[ref].get("pruefbar"):
                roh[ref].update(h1_max_dd(pe, roh[ref]["startkapital"], provider, broker=broker))
                if roh[ref].get("h1_status") in ("ok", "ok_teilmessung"):
                    n_h1 += 1
                    raw = roh[ref].get("h1_dd_pct_raw") or 0.0
                    # Winziger Nenner-Kennzeichnung auf dem MASSEGEBLICHEN DD
                    roh[ref]["kleiner_dd_nenner"] = 0.0 < raw < 1.0
                    if raw > 0 and roh[ref].get("cagr") is not None:
                        # Nutzer-Regel 21.10.: NUR der H1-Max-DD inkl. offener
                        # Trades ist Nenner — der Closed-DD hat keine Aussagekraft.
                        roh[ref]["retdd_jahr_h1"] = roh[ref]["cagr"] / (raw / 100.0)
                        geom = (roh[ref].get("ertrag_monat_geom_pct") or 0.0) / 100.0
                        if geom:
                            roh[ref]["retdd_monat_h1"] = geom / (raw / 100.0)
                # Bewertbar NUR mit belastbarem H1-Max-DD
                roh[ref]["bewertbar"] = (
                    roh[ref].get("retdd_jahr_h1") is not None and not roh[ref]["ko_kriterien"]
                )
        except Exception as exc:  # noqa: BLE001 — Fehler = Datenqualitätsbefund
            meldung = f"{type(exc).__name__}: {exc}"
            idx = meldung.find(".csv: ")
            if idx >= 0:
                meldung = meldung[idx + 6:]
            fehler[ref] = meldung[:200]

    engine = engine_werte()

    gruen_zweifelhaft, uebersehen, dd_abweichungen = [], [], []
    for ref, erg in roh.items():
        eng = engine.get(ref) or {}
        ampel = eng.get("ampel")
        eig_h1 = erg.get("h1_dd_pct_raw")
        eng_dd = eng.get("engine_dd_reko")
        if eig_h1 is not None and eng_dd is not None and abs(eig_h1 - eng_dd) > 10.0:
            dd_abweichungen.append((ref, eig_h1, eng_dd))
        rh1 = erg.get("retdd_jahr_h1")
        if ampel == "🟢" and (erg["ko_kriterien"]
                              or (rh1 is not None and rh1 < grund["min_calmar"])):
            gruen_zweifelhaft.append(ref)
        if ampel in ("🟡", "⚪") and erg.get("bewertbar") and rh1 is not None \
                and rh1 >= grund["min_calmar"]:
            uebersehen.append(ref)

    # Rangfolge NUR nach RetDD auf dem H1-Max-DD inkl. offener Trades
    # (Nutzer-Regel 21.10.: der Closed-DD hat als Nenner keine Aussagekraft).
    bewertbar = sorted((e for e in roh.values() if e.get("bewertbar")),
                       key=lambda e: -e["retdd_jahr_h1"])
    shortlist = bewertbar[:10]
    # Prüfbare Signale OHNE belastbare H1-Messung = Datenqualitäts-Fall
    h1_unvollstaendig = [e for e in roh.values()
                         if e.get("pruefbar") and not e.get("bewertbar")]

    # Empfehlungs-Ranking: RetDD auf dem H1-Max-DD entscheidet — der Ertrag
    # muss das Risiko bezahlen. Stufe A = RetDD über der Orientierung +
    # mindestens 3 Monate Historie; Stufe B = RetDD über der Orientierung,
    # aber kurze Historie; Stufe C = darunter (nicht gelistet).
    min_calmar = grund["min_calmar"]
    for e in bewertbar:
        if e["retdd_jahr_h1"] >= min_calmar and e.get("kapitalbasis_modell"):
            e["stufe"] = "M"
        elif e["retdd_jahr_h1"] >= min_calmar and not e["kurze_historie"]:
            e["stufe"] = "A"
        elif e["retdd_jahr_h1"] >= min_calmar:
            e["stufe"] = "B"
        else:
            e["stufe"] = "C"
    ranking = [e for e in bewertbar if e["stufe"] in ("A", "B", "M")]
    ranking.sort(key=lambda e: ({"A": 0, "B": 1, "M": 2}[e["stufe"]], -e["retdd_jahr_h1"]))
    unbewertbar_basis = [e for e in roh.values() if not e.get("basis_verwendbar")]
    kurz_liste = [e for e in roh.values() if e.get("kurze_historie") and not e["ko_kriterien"]]
    datenstand = max((e["fetched_at"] for e in roh.values()), default="—")

    def _name(r):
        return roh[r]["meta"].get("name") or f"ref {r}"

    dump = {
        "stand": heute.isoformat(timespec="seconds"),
        "datenstand": datenstand,
        "settings": {"dd_schranke": grund["dd_schranke"], "min_calmar": grund["min_calmar"]},
        "n_geprueft": len(roh) + len(fehler),
        "n_erfolgreich": len(roh),
        "n_parse_fehler": len(fehler),
        "n_h1_maxdd": n_h1,
        "shortlist": [e["meta"].get("name", str(e["ref"])) for e in shortlist],
        "ranking": [
            {"name": e["meta"].get("name", str(e["ref"])), "stufe": e["stufe"],
             "retdd_jahr_h1": e.get("retdd_jahr_h1"),
             "ertrag_monat_geom_pct": e.get("ertrag_monat_geom_pct"),
             "netto_monat_usd": e.get("netto_monat_usd"),
             "h1_dd_pct": e.get("h1_dd_pct_raw"), "h1_status": e.get("h1_status"),
             "startkapital": e.get("startkapital"),
             "kapitalbasis_modell": e.get("kapitalbasis_modell"),
             "kapitalbasis_quelle": e.get("kapitalbasis_quelle"),
             "kapitalbasis_details": e.get("kapitalbasis_details"),
             "historie_monate": e.get("historie_monate"),
             "winrate": e.get("winrate"), "quelle": (e.get("meta") or {}).get("quelle")}
            for e in ranking
        ],
        "gruen_zweifelhaft": [_name(r) for r in gruen_zweifelhaft],
        "moeglicherweise_uebersehen": [_name(r) for r in uebersehen],
        "h1_unvollstaendig": [e["meta"].get("name", str(e["ref"])) for e in h1_unvollstaendig],
        "signale": {str(k): v for k, v in roh.items()},
        "parse_fehler": fehler,
    }
    TMP_DIR.mkdir(exist_ok=True)
    (TMP_DIR / "kontrollscan_ergebnis.json").write_text(
        json.dumps(dump, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )

    from kontrollscan_pdf import baue_pdf  # noqa: PLC0415 — PDF-Teil separat wartbar

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    # Uhrzeit im Namen: niemals eine noch geöffnete (gesperrte) PDF überschreiben
    pdf_pfad = REPORT_DIR / f"kontrollscan_{heute.date().isoformat()}_{heute.strftime('%H%M')}.pdf"
    seiten = baue_pdf(
        pdf_pfad=pdf_pfad, heute=heute, datenstand=datenstand, grund=grund, roh=roh,
        fehler=fehler, engine=engine, shortlist=shortlist,
        gruen_zweifelhaft=gruen_zweifelhaft, uebersehen=uebersehen,
        dd_abweichungen=dd_abweichungen, unbewertbar_basis=unbewertbar_basis,
        kurz_liste=kurz_liste, bewertbar=bewertbar,
        h1_unvollstaendig=h1_unvollstaendig, ranking=ranking,
    )
    print(f"PDF: {pdf_pfad} ({seiten} Seiten)")
    print(
        f"Kurzbilanz: {len(roh) + len(fehler)} Signale geprüft "
        f"({len(fehler)} Daten-/Analysefehler), {len(bewertbar)} bewertbar "
        f"(nur mit belastbarem H1-Max-DD), {len(h1_unvollstaendig)} prüfbar, "
        f"aber H1-Messung unvollständig, Shortlist {len(shortlist)}, "
        f"Grün zweifelhaft {len(gruen_zweifelhaft)}, "
        f"möglicherweise übersehen {len(uebersehen)}, H1-Abweichungen >10 pp {len(dd_abweichungen)}"
    )
    for e in shortlist[:3]:
        print(
            f"  Stichprobe [eigene Rechnung]: {e['meta'].get('name')}: "
            f"Max-DD (H1 inkl. offener Trades) {e['h1_dd_pct_raw']:.2f} % "
            f"({e.get('h1_status')}), Profit/Monat {e.get('ertrag_monat_geom_pct') or 0:.2f} %, "
            f"RetDD/Jahr {e['retdd_jahr_h1']:.2f}, Startkapital {e['startkapital']:.0f} USD"
        )


if __name__ == "__main__":
    main()
