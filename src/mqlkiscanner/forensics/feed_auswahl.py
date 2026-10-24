"""Shared feed mechanics with explicit account/model acceptance policies.

Missing-symbol supplementation and whole-feed comparison answer different
questions. They use the same bounded terminal traversal, but never merge bars
of a symbol or silently replace their different completeness requirements.
This module never starts or closes a terminal itself; lifecycle operations
remain methods of the caller's provider.
"""
from __future__ import annotations

from ..zahlen import endliche_zahl, ist_endliche_zahl


class Einzelfeed:
    """Expose prices and provenance, never terminal switches/start/stop."""

    def __init__(self, anbieter):
        self.anbieter = anbieter
        self.provider = anbieter  # Compatibility with the offline-model adapter.

    @property
    def terminal_pfad(self):
        return getattr(self.anbieter, "terminal_pfad", None)

    @property
    def terminal_herkunft(self):
        return getattr(self.anbieter, "terminal_herkunft", {})

    def hole_h1(self, *args, **kwargs):
        return self.anbieter.hole_h1(*args, **kwargs)


def qualitaet(report, *, modus="konto", trades_n=None):
    """Return the established ordering for the explicitly selected policy.

    Account studies accept a reliable, finite DD and prefer raw coverage,
    complete FX and finally larger DD on a tie. Offline no-flow models require
    all exported trades, no partial measurement and 100% coverage before they
    stop searching. Their ranking deliberately remains coverage/trade count.
    """
    if modus == "konto":
        dd = report.get("equity_dd_pct_raw", report.get("equity_dd_pct"))
        measurable = ist_endliche_zahl(dd) and dd >= 0
        coverage = report.get("abdeckung_pct_raw", report.get("abdeckung_pct"))
        if not ist_endliche_zahl(coverage) or coverage < 0:
            coverage = 0
        return (report.get("verlaesslich") is True and measurable, measurable,
                coverage, not bool(report.get("fx_luecke")), dd if measurable else 0)
    if modus == "modell":
        if not isinstance(trades_n, int) or isinstance(trades_n, bool) or trades_n < 0:
            raise ValueError("Modell-Feedvergleich benötigt die Anzahl exportierter Trades")
        complete = (report.get("status") == "ok" and report.get("verlaesslich") is True
                    and report.get("trades_mit_kurs_und_kontrakt") == trades_n
                    and not report.get("fx_luecke") and not report.get("teilmessung"))
        return (complete, endliche_zahl(report.get("abdeckung_pct_raw")) or 0,
                endliche_zahl(report.get("trades_mit_kurs_und_kontrakt")) or 0)
    raise ValueError(f"Unbekannte Feed-Auswahlregel: {modus}")


def ausreichend(report, *, modus="konto", trades_n=None):
    """Whether this policy has enough evidence to stop checking later feeds."""
    result = qualitaet(report, modus=modus, trades_n=trades_n)
    return bool(result[0] and (modus != "modell" or result[1] >= 100))


def feed_identitaet(anbieter):
    return (getattr(anbieter, "terminal_idx", None),
            getattr(anbieter, "terminal_pfad", None))


def _melde(anbieter, meldung, status, grund):
    if meldung is not None:
        meldung({"terminal": getattr(anbieter, "terminal_pfad", None),
                 "status": status, "grund": grund})


def reset_feed(anbieter, *, meldung=None, fehler=None):
    """Return a switched provider to its first feed, retaining caller policy.

    Batch callers collect reset failures through callbacks. Direct kernels
    retain their old behavior: a negative return is tolerated, exceptions are
    propagated. No lifecycle method is invented for a standalone provider.
    """
    if (getattr(anbieter, "terminal_idx", 0) == 0
            or not hasattr(anbieter, "zurueck_zum_ersten_terminal")):
        return
    try:
        ok, reason = anbieter.zurueck_zum_ersten_terminal()
        if not ok:
            _melde(anbieter, meldung, "reset_fehlgeschlagen", reason)
    except Exception as error:
        if fehler is None:
            raise
        fehler(error, "reset_fehlgeschlagen")


def iteriere_weitere_feeds(anbieter, *, weiter_nach_verbindungsfehler=False,
                         meldung=None, fehler=None):
    """Yield each successfully connected later feed once, in native order.

    A failed switch ends symbol supplementation. Whole-feed batch comparison
    explicitly continues past a failed connection that advanced the provider.
    An unchanged/cyclic feed identity always ends traversal.
    """
    visited = {feed_identitaet(anbieter)}
    while hasattr(anbieter, "hat_weiteren_terminal") and anbieter.hat_weiteren_terminal():
        try:
            ok, reason = anbieter.wechsle_terminal()
        except Exception as error:
            if fehler is None:
                raise
            fehler(error, "verbindung_fehlgeschlagen")
            ok, reason = False, None
        identity = feed_identitaet(anbieter)
        if identity in visited:
            _melde(anbieter, meldung, "kein_feed_fortschritt",
                   "Terminalwechsel hat keine neue Quelle erreicht")
            break
        visited.add(identity)
        if not ok:
            if reason is not None:
                _melde(anbieter, meldung, "verbindung_fehlgeschlagen", reason)
            if weiter_nach_verbindungsfehler:
                continue
            break
        yield anbieter


def ergaenze_fehlende_symbole(anbieter, bars_je_symbol, fehlende_symbole, lade_symbol):
    """Fill only absent symbol series, keeping every symbol on one feed.

    Existing series are never extended or overwritten. A reset also happens
    if a price read raises after switching, so the next signal cannot inherit
    the failed signal's terminal. The original read error remains primary.
    """
    missing = list(fehlende_symbole)
    try:
        if missing:
            for _ in iteriere_weitere_feeds(anbieter):
                remaining = []
                for symbol in missing:
                    bars = lade_symbol(symbol)
                    if bars:
                        bars_je_symbol[symbol] = bars
                    else:
                        remaining.append(symbol)
                missing = remaining
                if not missing:
                    break
    except BaseException:
        # Cleanup failure must not replace the original loading exception.
        try:
            reset_feed(anbieter)
        except Exception:
            pass
        raise
    else:
        reset_feed(anbieter)
    return missing
