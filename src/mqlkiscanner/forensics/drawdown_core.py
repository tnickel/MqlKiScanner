"""Shared high-watermark calculation for already constructed account curves.

Points are ``(time, value, measured, flow_delta)`` in chronological order.
The caller owns the time basis, currency, event aggregation and completeness
of each value. Only complete measurements update the watermark. Cashflows
at missing measurements are carried to the next complete point. Only a net
withdrawal lowers the watermark; deposits raise it through the account value.

Percentage results are unrounded percentages (0..100, potentially above
100 for negative equity), never fractions. Closing diagnostics historically
use 100 percent for losses without a positive peak; H1 measurements use zero
and enforce valid capital separately. That convention is explicit, not an
alternative cashflow policy.
"""
from __future__ import annotations


def max_drawdown_aus_kurve(punkte, *, start=None, start_time=None,
                           nichtpositiver_peak_pct=0.0, verlauf=False):
    """Measure absolute/relative maxima independently, preserving first ties.

    ``start`` is an optional anchor before the supplied points. Without it,
    the first measured point anchors the curve. The optional path supplies
    the same watermarks for charting and duration diagnostics; callers do not
    need to recalculate peaks. Missing points retain a None path entry.
    """
    peak = float(start) if start is not None else None
    peak_time = start_time
    end = peak
    max_usd = pct_at_max_usd = max_pct = usd_at_max_pct = 0.0
    dd_time = dd_peak_time = rel_time = rel_peak_time = None
    pending_flow = 0.0
    path = [] if verlauf else None
    measurements = 0
    for time, value, measured, flow_delta in punkte:
        pending_flow += flow_delta or 0.0
        if not measured or value is None:
            if path is not None:
                path.append(None)
            continue
        # Apply pending withdrawals BEFORE measuring the price/trade loss.
        if pending_flow < 0 and peak is not None:
            peak = max(value, peak + pending_flow)
        pending_flow = 0.0
        if peak is None or value > peak:
            peak, peak_time = value, time
        end = value
        measurements += 1
        loss = peak - value
        relative = (loss / peak * 100.0 if peak > 0 else
                    float(nichtpositiver_peak_pct) if loss > 0 else 0.0)
        if loss > max_usd:
            max_usd, pct_at_max_usd = loss, relative
            dd_time, dd_peak_time = time, peak_time
        if relative > max_pct:
            max_pct, usd_at_max_pct = relative, loss
            rel_time, rel_peak_time = time, peak_time
        if path is not None:
            path.append({"time": time, "value": value, "peak": peak,
                         "peak_time": peak_time, "dd_usd": loss,
                         "dd_pct": relative,
                         "unterwasser_pct": (value / peak - 1.0) * 100.0 if peak > 0 else 0.0})
    result = {"dd_usd_raw": max_usd, "dd_pct_raw": pct_at_max_usd,
              "dd_pct_max_rel_raw": max_pct, "dd_usd_am_rel_max_raw": usd_at_max_pct,
              "dd_time": dd_time, "dd_peak_time": dd_peak_time,
              "dd_time_max_rel": rel_time, "dd_peak_time_max_rel": rel_peak_time,
              "end_balance_raw": end, "peak_balance_raw": peak,
              "messpunkte": measurements}
    if path is not None:
        result["verlauf"] = path
    return result
