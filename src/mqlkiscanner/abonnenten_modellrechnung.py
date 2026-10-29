"""Separate, explicit no-flow scenarios from immutable trade snapshots.

This module never updates a source, starts a terminal, downloads FX, or writes
the price cache. Its numbers are scenarios, not measured account forensics.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from itertools import groupby
import json
import math
import os
from pathlib import Path
import sqlite3

from . import config, fx_rates, parser
from .forensics import drawdown, equity_rekonstruktion
from .forensics.drawdown_core import max_drawdown_aus_kurve
from .forensics.feed_auswahl import Einzelfeed as _NurLesen, qualitaet, ausreichend
from .zahlen import endliche_zahl as _zahl, json_sicher as _json_sicher
from .symbols import alias_fuer_symbol, normalize_symbol

VERSION = 1
JAHR_SEKUNDEN = 365.25 * 86400
# Nutzer-Freigabe 29.10.2026: Kursabdeckung >80 % genügt in den Abonnenten-
# Messungen (statt der 95-%-Norm des Hauptscanners). Unter 95 % bleibt die
# Messung ausdrücklich als Vorbehalt gekennzeichnet.
MIN_ABDECKUNG_ABO = 0.80
KAPITAL_METHODEN = {
    "csv_einzahlungen_vor_handelsbeginn": "Belegt: Einzahlungen vor Handelsbeginn",
    "native_initial_deposit_usd": "Belegt: ursprüngliche Einzahlung der Quelle",
    "belegter_initial_deposit_aus_gepruefter_forensik": "Belegt: geprüfte Startkapitalbasis",
    "komplex_closing_dd_anker": "Modell: unabhängiger Closing-DD",
    "komplex_lot_pnl_regression": "Schätzung: Lots-/Gewinnverlauf",
    "grobe_lot_kalibrierung": "Grobe Schätzung: vergleichbare Lots",
    "fallback_10000": "Annahme: 10.000 USD",
}


class OfflineFx:
    """The existing ECB file, with its normal 10-day historical rule; no GET."""

    def __init__(self, path=None, *, table=None):
        self.path = Path(path) if path is not None else Path(fx_rates.csv_path())
        self.table = (fx_rates._load_file(self.path) or {}) if table is None else table
        self.belege = {}

    def usd_per(self, currency, when):
        currency = str(currency or "").upper()
        result = fx_rates.usd_per_table(currency, when, self.table)
        if result is None or currency == "USD":
            return result
        self.belege[(currency, when.isoformat())] = {
            "waehrung": currency, "ereignistag": when.isoformat(),
            "kursdatum": result["date"], "usd_je_einheit": result["rate"],
            "quelle": "lokale ECB-Referenzkursdatei", "datei": str(self.path),
        }
        return result


def _dateisignatur(path):
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


@lru_cache(maxsize=4)
def _offline_fx(path, signature):
    return fx_rates._load_file(Path(path)) or {}


class _Einzelfeed:
    """One exact terminal/server feed; bars from other feeds cannot leak in."""

    def __init__(self, cache, feed, terminal, server):
        self.cache, self.feed = cache, feed
        self.terminal_pfad, self.server = terminal, server
        self.terminal_herkunft, self.symbol_mapping = {}, {}
        self.ungueltige_bars = 0

    def hole_h1(self, symbol, von, bis, gmt_offset_s=0):
        mapping = self.cache.symbol_mapping(self.feed, self.terminal_pfad, symbol)
        if not mapping:
            return None
        actual, methode = mapping
        with self.cache.verbinden() as conn:
            rows = conn.execute(
                "SELECT epoch,open,high,low,close FROM h1_bars "
                "WHERE feed=? AND symbol=? AND zeitrahmen='H1' "
                "AND epoch BETWEEN ? AND ? AND abgeschlossen=1 ORDER BY epoch",
                (self.feed, actual, int(von)+int(gmt_offset_s), int(bis)+int(gmt_offset_s)),
            ).fetchall()
        bars = []
        for epoch, opened, high, low, close in rows:
            values = [opened, high, low, close]
            if (epoch % 3600 or any(_zahl(v) is None or v <= 0 for v in values)
                    or low > min(opened, close) or high < max(opened, close) or low > high):
                self.ungueltige_bars += 1
                continue
            bars.append(dict(zip(("time", "open", "high", "low", "close"),
                                 (epoch, opened, high, low, close))))
        if bars:
            self.terminal_herkunft[symbol] = self.terminal_pfad
            self.symbol_mapping[symbol] = {"cache_symbol": actual, "methode": methode}
        return bars or None


class OfflineH1Cache:
    """Read-only cache inventory, reusable across a complete table run.

    Only a saved JSON feed identity [terminal, server] is accepted. Neither
    request spans nor incomplete bars establish a price measurement.
    """

    def __init__(self, path=None, *, settings=None):
        self.path = Path(path) if path is not None else config.DATA_DIR / "kursdaten.db"
        self.settings = config.load_settings() if settings is None else settings
        self.feeds, self._symbols = [], {}
        if self.path.is_file():
            with self.verbinden() as conn:
                for (feed,) in conn.execute("SELECT DISTINCT feed FROM h1_bars ORDER BY feed"):
                    try:
                        identity = json.loads(feed)
                    except (ValueError, TypeError):
                        continue
                    if (isinstance(identity, list) and len(identity) == 2
                            and all(isinstance(v, str) and v.strip() for v in identity)):
                        self.feeds.append((feed, *identity))

    @contextmanager
    def verbinden(self):
        # mode=ro also prevents creation of an absent cache or schema.
        conn = sqlite3.connect(self.path.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
        try:
            yield conn
        finally:
            conn.close()

    def symbol_mapping(self, feed, terminal, symbol):
        if feed not in self._symbols:
            with self.verbinden() as conn:
                self._symbols[feed] = {r[0] for r in conn.execute(
                    "SELECT DISTINCT symbol FROM h1_bars WHERE feed=?", (feed,))}
        available = self._symbols[feed]
        suffix = str(self.settings.get("markt_symbol_suffix") or "").strip()
        normalized = normalize_symbol(symbol)
        alias = alias_fuer_symbol(symbol, terminal, self.settings.get("symbol_aliases"))
        candidates = [(symbol, "exaktes Symbol"), (symbol+suffix, "konfigurierter Suffix"),
                      (normalized, "normalisiertes Symbol"),
                      (normalized+suffix, "normalisiertes Symbol + konfigurierter Suffix"),
                      (alias, "belegter Terminalalias")]
        return next(((name, why) for name, why in candidates if name and name in available), None)

    def providers(self, entry):
        prior = (entry.get("equity") or {}).get("kursdaten_terminal")
        broker = (entry.get("quellen_stats") or {}).get("broker_server")
        def priority(item):
            _, terminal, server = item
            return (not (prior and os.path.normcase(terminal) == os.path.normcase(str(prior))),
                    not (broker and server == broker), terminal, server)
        return [_Einzelfeed(self, *item) for item in sorted(self.feeds, key=priority)]


@lru_cache(maxsize=4)
def _offline_cache(path, signature, wal_signature, settings_json):
    return OfflineH1Cache(path, settings=json.loads(settings_json))


def _standard_cache():
    path = config.DATA_DIR / "kursdaten.db"
    return _offline_cache(str(path.resolve()), _dateisignatur(path),
                          _dateisignatur(Path(str(path)+"-wal")),
                          json.dumps(config.load_settings(), sort_keys=True, default=str))


def _modell_dd(report, capital, prior_costs):
    """Retain K0 as the peak before costs preceding the first position."""
    curve = report.pop("_curve", None)
    if not curve:
        return
    points, balance = [], capital
    for when, events in groupby(sorted(prior_costs, key=lambda c: c.time), key=lambda c: c.time):
        balance += math.fsum(c.amount for c in events)
        points.append((when.isoformat()+" (Exportzeit)", balance, True, 0.0))
    points.extend((datetime.fromtimestamp(epoch, timezone.utc).isoformat(), value, True, 0.0)
                  for epoch, value, measured, _flow in curve if measured)
    dd = max_drawdown_aus_kurve(points, start=capital)
    minimum, minimum_when = capital, None
    for when, value, _measured, _flow in points:
        if value < minimum:
            minimum, minimum_when = value, when
    max_rel = dd["dd_pct_max_rel_raw"]
    report.update(equity_dd_pct_raw=max_rel, equity_dd_pct=round(max_rel, 2),
                  equity_dd_pct_max_rel=round(max_rel, 2),
                  equity_dd_pct_am_usd_max=round(dd["dd_pct_raw"], 2), equity_dd_usd=round(dd["dd_usd_raw"], 2),
                  min_equity_usd=minimum, min_equity_zeit=minimum_when,
                  modell_insolvent=minimum <= 0, modell_kurve_geprueft=True)


def _equity(parsed, capital, broker, providers, lookup):
    best, attempts = None, []
    def quality(report):
        return qualitaet(report, modus="modell", trades_n=len(parsed.trades))
    for provider in providers:
        try:
            first_trade = min(t.open_time for t in parsed.trades)
            prior_costs = [c for c in parsed.costs if c.time < first_trade]
            trading_capital = capital+math.fsum(c.amount for c in prior_costs)
            # A wrapper deliberately exposes no terminal-switch/start methods.
            report = equity_rekonstruktion.rekonstruiere(
                parsed, _NurLesen(provider), trading_capital, broker=broker,
                fx_lookup=lookup, include_curve=True, compute_dd=False,
                min_abdeckung=MIN_ABDECKUNG_ABO)
            report = dict(report)
            _modell_dd(report, capital, prior_costs)
            report["cache_feed"] = getattr(provider, "feed", None)
            report["kursdaten_terminal"] = getattr(provider, "terminal_pfad", None)
            report["symbol_mapping"] = deepcopy(getattr(provider, "symbol_mapping", {}))
            if getattr(provider, "ungueltige_bars", 0):
                report.update(status="unvollstaendig", verlaesslich=False,
                              grund="Ungültige OHLC-Bars im Cachefenster ausgelassen.",
                              ungueltige_bars=provider.ungueltige_bars)
            attempts.append({k: report.get(k) for k in
                             ("cache_feed", "kursdaten_terminal", "status", "verlaesslich",
                              "abdeckung_pct_raw", "grund", "symbol_mapping")})
            if best is None or quality(report) > quality(best):
                best = report
            if ausreichend(report, modus="modell", trades_n=len(parsed.trades)):
                break
        except (ValueError, TypeError, OSError, sqlite3.Error, ArithmeticError) as error:
            attempts.append({"cache_feed": getattr(provider, "feed", None),
                             "status": "fehler", "grund": f"{type(error).__name__}: {error}"})
    result = best or {"status": "unvollstaendig", "verlaesslich": False,
                      "grund": "Kein belegter abgeschlossener H1-Feed im lokalen Cache verfügbar."}
    result["kursquellen_versuche"] = attempts
    result["kapitalfluesse"] = "Modellszenario: alle Ein-/Auszahlungen absichtlich ignoriert."
    result["modell"] = True
    return result


def berechne_modell(entry, kapital, kurse=None):
    """Return a nested ``entry['modell']`` value; never mutate the entry.

    ``kapital`` is an auditable capital proposal, not a licence to relabel
    native money or volume. ``kurse`` may be an OfflineH1Cache, a single
    explicitly provided read-only price provider, or a list of such providers.
    The default uses only already saved H1 and ECB data.
    """
    capital_info = deepcopy(kapital or {})
    method = capital_info.get("methode") or capital_info.get("herkunft")
    capital_note = ("Kapitalbasis belegt; der Verlauf ohne Ein-/Auszahlungen bleibt ein Modellszenario."
                    if capital_info.get("basis_typ") == "belegt" else
                    "Angenommenes oder geschätztes Modellkapital; keine Aussage über tatsächliches Kontokapital. "
                    "Ein-/Auszahlungen bleiben im Szenario unberücksichtigt.")
    result = {"version": VERSION, "status": "datenluecke", "grund": "",
              "startkapital_usd": None,
              "kapital_methode": KAPITAL_METHODEN.get(method, method),
              "kapital_hinweis": capital_note,
              "kapital_details": capital_info, "annahme_kapitalfluesse": "keine",
              "ignorierte_kapitalfluesse": None, "nettogewinn_usd": None,
              "rendite_zeitraum_pct": None, "cagr_jahr_pct": None,
              "equity_dd_pct": None, "equity_dd_usd": None, "retdd_jahr": None,
              "closing_dd_pct": None, "closing_dd_usd": None, "waehrung": "USD",
              "trade_sha256": entry.get("trades_sha256"), "trade_anzahl": None,
              "zeit_von": None, "zeit_bis": None, "h1_abdeckung_pct": None,
              "equity": {}, "berechnet_am": datetime.now(timezone.utc).isoformat()}
    try:
        amount = _zahl(capital_info.get("kapital"))
        currency = str(capital_info.get("waehrung") or "").strip().upper()
        if amount is None or amount <= 0 or not currency:
            raise ValueError("Positive endliche Modellkapitalbasis mit Währungsangabe fehlt.")
        # USD proposals remain visible even if this provider has no trade file.
        if currency == "USD":
            result["startkapital_usd"] = amount
        path = Path(entry.get("trades_path") or "")
        digest = str(entry.get("trades_sha256") or "")
        if not path.is_file() or not digest:
            raise ValueError("Gesicherter Trade-Snapshot mit SHA-256 fehlt.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Trade-Snapshot stimmt nicht mit dem gespeicherten SHA-256 überein.")
        original = parser.load_export(path)
        if not original.trades:
            raise ValueError("Keine abgeschlossenen Einzeltrades im gespeicherten Export.")
        if original.archived_pnl_aggregates:
            raise ValueError("Archivierte PnL-Aggregate ohne einzelne Realisierungszeitpunkte; keine vollständige Modellkurve.")
        model = deepcopy(original)
        first = min(t.open_time for t in model.trades)
        last = max([t.close_time for t in model.trades]+[c.time for c in model.costs])
        first = min([first]+[c.time for c in model.costs])
        result.update(trade_anzahl=len(model.trades), zeit_von=first.isoformat(), zeit_bis=last.isoformat())
        fx_path = Path(fx_rates.csv_path())
        fx = OfflineFx(fx_path, table=_offline_fx(str(fx_path.resolve()), _dateisignatur(fx_path)))
        capital_rate = fx.usd_per(currency, first.date())
        if capital_rate is None:
            raise ValueError(f"Historischer lokaler ECB-Kurs für Modellkapital in {currency} fehlt.")
        amount *= capital_rate["rate"]
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Konvertierte Modellkapitalbasis ist nicht positiv und endlich.")
        result["startkapital_usd"] = amount
        currency_values = {str(v).strip().upper() for v in
                           (entry.get("trade_money_currency"), entry.get("account_currency"),
                            (entry.get("quellen_stats") or {}).get("account_currency"))
                           if v is not None and str(v).strip()}
        if len(currency_values) > 1:
            raise ValueError("Widersprüchliche Kontowährungen im gespeicherten Trade-/Quellenkontext: "
                             + ", ".join(sorted(currency_values)))
        native_currency = next(iter(currency_values), "")
        result["quellenwaehrung"] = native_currency or None
        result["ignorierte_kapitalfluesse"] = {
            "anzahl": len(model.balances), "waehrung": native_currency or None,
            "einzahlungen_nativ": math.fsum(b.amount for b in model.balances if b.amount > 0),
            "auszahlungen_nativ": math.fsum(b.amount for b in model.balances if b.amount < 0),
        }
        model.balances = []
        if "robo" in str(entry.get("quelle") or "").casefold():
            raise ValueError("Native Robo-Trade-/Volumeneinheiten sind nicht belegt; Ratingprofit ist keine Trade- oder Lotbasis.")
        if not native_currency:
            raise ValueError("Kontowährung der gespeicherten Tradebeträge ist unbekannt.")
        for trade in model.trades:
            if (_zahl(trade.volume) is None or trade.volume <= 0
                    or any(_zahl(v) is None for v in (trade.profit, trade.commission, trade.swap))):
                raise ValueError("Native Lots oder monetäre Einzeltradebeträge sind ungültig.")
            rate = fx.usd_per(native_currency, trade.close_time.date())
            if rate is None:
                raise ValueError(f"Lokaler historischer ECB-Kurs für {native_currency} am {trade.close_time.date()} fehlt.")
            trade.profit *= rate["rate"]
            trade.commission *= rate["rate"]
            trade.swap *= rate["rate"]
        for cost in model.costs:
            rate = fx.usd_per(native_currency, cost.time.date())
            if rate is None or _zahl(cost.amount) is None:
                raise ValueError(f"Historische USD-Umrechnung einer Kontokostenbuchung am {cost.time.date()} fehlt.")
            cost.amount *= rate["rate"]
        net = model.net_total
        if not math.isfinite(net):
            raise ValueError("Nettoergebnis ist nicht endlich.")
        period_return = net/amount*100
        if not math.isfinite(period_return):
            raise ValueError("Modellrendite überschreitet den endlichen Zahlenbereich.")
        result.update(nettogewinn_usd=net, rendite_zeitraum_pct=period_return)
        closing = drawdown._max_drawdown(model.realized_events(), amount)
        result.update(closing_dd_pct=closing["dd_pct_max_rel_raw"], closing_dd_usd=closing["dd_usd"])
        years = (last-first).total_seconds()/JAHR_SEKUNDEN
        annual_reason = ""
        if years <= 0 or amount+net <= 0:
            annual_reason = "CAGR/RetDD nicht definiert: kein positives Zeitfenster oder Modellendkapital ≤ 0."
        else:
            try:
                cagr = math.expm1(math.log1p(net/amount)/years)*100
                if math.isfinite(cagr):
                    result["cagr_jahr_pct"] = cagr
                else:
                    annual_reason = "Annualisierung überschreitet den endlichen Zahlenbereich."
            except (OverflowError, ValueError):
                annual_reason = "Annualisierung überschreitet den endlichen Zahlenbereich."
        result["annualisierung_hinweis"] = (
            "Geometrische Hochrechnung des Modellfensters, keine Gewinnprognose. "
            + ("Kurzes Fenster unter einem Jahr; Jahreswert stark vom Zeitraum abhängig. " if years < 1 else "")
            + annual_reason)
        providers = (kurse.providers(entry) if hasattr(kurse, "providers") else
                     list(kurse) if isinstance(kurse, (list, tuple)) else
                     [kurse] if kurse is not None else _standard_cache().providers(entry))
        report = _equity(model, amount, (entry.get("quellen_stats") or {}).get("broker_server"),
                         providers, fx.usd_per)
        result["equity"] = report
        result["fx_belege"] = list(fx.belege.values())
        result["h1_abdeckung_pct"] = _zahl(report.get("abdeckung_pct_raw", report.get("abdeckung_pct")))
        dd = _zahl(report.get("equity_dd_pct_raw", report.get("equity_dd_pct")))
        complete = (report.get("status") == "ok" and report.get("verlaesslich") is True
                    and report.get("trades_mit_kurs_und_kontrakt") == len(model.trades)
                    and not report.get("fx_luecke") and not report.get("teilmessung")
                    and dd is not None and dd >= 0 and report.get("modell_kurve_geprueft") is True)
        if complete:
            result.update(equity_dd_pct=dd, equity_dd_usd=_zahl(report.get("equity_dd_usd")))
            if dd > 0 and result["cagr_jahr_pct"] is not None:
                result["retdd_jahr"] = result["cagr_jahr_pct"]/dd
            result["status"] = "berechnet"
            result["grund"] = "Modellszenario aus gesichertem Export und getrennt geprüftem H1-Feed; keine realen Kontokennzahlen."
            if (_zahl(result.get("h1_abdeckung_pct")) is not None
                    and result["h1_abdeckung_pct"] < equity_rekonstruktion.SCHRANKE_MIN_ABDECKUNG * 100):
                result["h1_abdeckung_vorbehalt"] = True
                result["grund"] += (f" Abdeckung {result['h1_abdeckung_pct']:.1f} % unter der 95-%-Norm"
                                    f" (Nutzer-Freigabe >{MIN_ABDECKUNG_ABO:.0%} ab 29.10.2026).")
            if (dd == 0 or annual_reason or report.get("modell_insolvent")
                    or dd >= 100 or closing["dd_pct_max_rel_raw"] >= 100):
                result["status"] = "eingeschraenkt"
                result["grund"] += " " + (annual_reason or (
                    "RetDD bei DD=0 nicht definiert." if dd == 0 else
                    "Modellkurve erreicht Kapitalverlust von mindestens 100%; Margin-/Liquidationsregeln sind nicht modelliert."))
            if report.get("modell_insolvent") or dd >= 100 or closing["dd_pct_max_rel_raw"] >= 100:
                result["retdd_jahr"] = None
                result["retdd_grund"] = "Modell zwischenzeitlich insolvent; keine fortführbare Calmar-Basis ohne modellierte Liquidation."
                result["annualisierung_hinweis"] += " Zwischenzeitlich aufgebrauchtes Modellkapital; Rendite/CAGR nur arithmetische Szenariodiagnose."
            if result["retdd_jahr"] is not None and _zahl(result["retdd_jahr"]) is None:
                result.update(status="eingeschraenkt", retdd_jahr=None,
                              retdd_grund="RetDD überschreitet den endlichen Zahlenbereich.")
        else:
            result["grund"] = "H1-Modell-DD/RetDD nicht vollständig belegbar: " + str(report.get("grund") or report.get("status"))
            if annual_reason or closing["dd_pct_max_rel_raw"] >= 100:
                result["status"] = "eingeschraenkt"
                result["grund"] += " " + (annual_reason or "Modellkapital zwischenzeitlich aufgebraucht; keine Liquidationsregeln modelliert.")
        if entry.get("trade_history_complete") is False:
            result.update(status="datenluecke", grund=result["grund"]+
                          " Die Quelle meldet einen unvollständigen Export; Werte betreffen nur diesen Ausschnitt.")
        return _json_sicher(result)
    except (ValueError, TypeError, OSError, sqlite3.Error, ArithmeticError, KeyError) as error:
        result["grund"] = f"{type(error).__name__}: {error}"
        return _json_sicher(result)
