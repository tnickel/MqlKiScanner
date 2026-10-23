"""Dated non-ECB exposure conversion from price-checked, completed H1 bars.

CNH is never CNY. A CNH amount of USDCNH uses the inverse of that exact
instrument's reference bar. Crypto amounts use the direct USD quote from the
same proven terminal/server feed. No future close, weekend carry, cross-feed
fallback, or conversion from another trade's entry price is allowed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

from ..symbols import normalize_symbol
from .equity_rekonstruktion import GMT_KANDIDATEN_S, Zeitbasis, _epoch, ermittle_gmt_offset


class ExposureUsdUmrechnung:
    def __init__(self, parsed, kurse, resolutions):
        self.kurse = kurse
        self.resolutions = resolutions
        self.trades = parsed.trades
        self.prepared = {}
        self.used = {}
        self.failures = {}
        self.clocks = {}

    def _feed(self):
        reader = getattr(self.kurse, "_feed_identitaet", None)
        # An installation path alone is not a proven broker feed. Test doubles
        # and legacy providers without a server identity remain unsupported.
        if not callable(reader):
            return None
        return reader()[1]

    @staticmethod
    def _closes(bars):
        return {(int(b["time"]) // 3600 + 1) * 3600: b["close"] for b in bars or []}

    def _offset(self, own_trades, raw, own_bars, low, high, feed):
        offset = ermittle_gmt_offset(own_trades, {raw: own_bars})["offset_s"]
        if offset is not None:
            self.clocks[raw] = {"scope": "Instrument desselben Exports", "instruments": [raw],
                                "trade_count": len(own_trades), "offset_s": offset}
            return offset
        # A quiet currency can fit several hours even with complete bars.
        # Other price events of this same export in the same time window and
        # on the same reference feed can establish the shared clock. Missing
        # instruments do not become price evidence; CNH is still checked
        # against its own prices after adopting that common clock.
        maps = {raw: own_bars}
        probes = list(own_trades)
        groups = {}
        for trade in self.trades:
            name = trade.symbol.strip().upper()
            if name != raw and low <= _epoch(trade.open_time) <= _epoch(trade.close_time) <= high:
                groups.setdefault(name, []).append(trade)
        for name, trades in sorted(groups.items()):
            bars = self.kurse.hole_h1(name, low, high)
            if feed != self._feed():
                return None
            if bars:
                maps[name] = bars
                probes.extend(trades)
        offset = ermittle_gmt_offset(probes, maps)["offset_s"]
        self.clocks[raw] = {"scope": "Gemeinsame Ereigniszeit desselben Exports und Referenzfeeds",
            "instruments": sorted(maps), "trade_count": len(probes), "offset_s": offset}
        return offset

    def _prepare(self, symbol, quote):
        trades = [t for t in self.trades if normalize_symbol(t.symbol) == symbol]
        raw_symbols = {t.symbol.strip().upper() for t in trades}
        if not trades or len(raw_symbols) != 1:
            self.failures[symbol] = "Mehrdeutige Originalinstrumente"
            return None
        raw = next(iter(raw_symbols))
        low = min(_epoch(t.open_time) for t in trades) + min(GMT_KANDIDATEN_S) - 3600
        high = max(_epoch(t.close_time) for t in trades) + max(GMT_KANDIDATEN_S)
        result = None
        try:
            while True:
                feed = self._feed()
                bars = self.kurse.hole_h1(raw, low, high)
                if feed and feed == self._feed() and bars:
                    basis = Zeitbasis(trades, {raw: bars},
                        self._offset(trades, raw, bars, low, high, feed))
                    if basis.verlaesslich:
                        fx_symbol = raw if quote == "CNH" else quote + "USD"
                        fx_bars = bars if quote == "CNH" else self.kurse.hole_h1(fx_symbol, low, high)
                        if feed == self._feed() and fx_bars:
                            result = {"basis": basis, "trades": trades, "feed": feed,
                                "conversion_symbol": fx_symbol, "closes": self._closes(fx_bars)}
                            break
                if not (hasattr(self.kurse, "hat_weiteren_terminal")
                        and self.kurse.hat_weiteren_terminal()):
                    break
                ok, _ = self.kurse.wechsle_terminal()
                if not ok:
                    break
        finally:
            if (hasattr(self.kurse, "zurueck_zum_ersten_terminal")
                    and getattr(self.kurse, "terminal_idx", 0) != 0):
                self.kurse.zurueck_zum_ersten_terminal()
        if result is None:
            self.failures[symbol] = "Kein gemeinsamer Serverfeed mit preisbelegter Zeitbasis und Umrechnungskurs"
        return result

    def rate(self, quote, when, symbol):
        if quote not in {"CNH", "ETH", "BCH"}:
            return None
        if quote == "CNH" and symbol != "USDCNH":
            return None
        if symbol not in self.prepared:
            self.prepared[symbol] = self._prepare(symbol, quote)
        context = self.prepared[symbol]
        if not context:
            return None
        original = _epoch(when)
        basis = context["basis"]
        if not basis.periode(original)["belegt"]:
            return None
        # A price event outside its own checked bar cannot certify the rate
        # for any position that still contributes to this snapshot.
        if any(not basis._trade_sicher.get(id(t), False) for t in context["trades"]
               if t.open_time <= when <= t.close_time):
            self.failures[symbol] = "Aktiver Trade ohne passenden Open-/Close-Preisbeleg"
            return None
        point = basis.nach_referenz(original) // 3600 * 3600
        close = context["closes"].get(point)
        if (not isinstance(close, (int, float)) or isinstance(close, bool)
                or not math.isfinite(close) or close <= 0):
            self.failures[symbol] = "Abgeschlossene Vorstundenbar am Ereignis fehlt"
            return None
        value = 1.0 / close if quote == "CNH" else close
        record = {"rate": value, "date": when.date().isoformat(),
            "source": "H1-Referenzkurs; abgeschlossene Vorstundenbar",
            "bar_end_utc": datetime.fromtimestamp(point, timezone.utc).isoformat(),
            "feed": context["feed"], "conversion_symbol": context["conversion_symbol"],
            "time_basis_gmt_h": basis.periode(original)["offset_s"] / 3600}
        self.used[symbol, original] = record
        return record

    def metadata(self):
        return {"regel": "Letzter abgeschlossener H1-Close vor/am preisbelegt abgebildeten Ereignis; "
                    "Alter kleiner als eine Stunde, keine Lueckenfortschreibung, gleicher Terminal/Serverfeed",
            "verwendete_ereignisse": len(self.used),
            "feeds": sorted({v["feed"] for v in self.used.values()}),
            "instrumente": sorted({s for s, _ in self.used}),
            "zeitbelege": dict(sorted(self.clocks.items())),
            "unbelegte_instrumente": dict(sorted(self.failures.items()))}
