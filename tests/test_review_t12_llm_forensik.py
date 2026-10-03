# -*- coding: utf-8 -*-
"""Review T1/2 29.09. (LLM-Bewertung & Risikoklassen): nachgestellte
Fehlerfälle — M2 (Kriterien-Text), M3 (pro-Call-Tokens), M4 (veraltete
Regeltexte), M5 (Budget-Reservierung), F1 (Kapitalbasis-Paar), F4
(Breakeven in der Verlustserie)."""
from __future__ import annotations

from datetime import datetime

from mqlkiscanner import pipeline, regelwerk
from mqlkiscanner.forensics import drawdown, exposure, stops
from mqlkiscanner.llm import client as llm_client
from mqlkiscanner.models import BalanceRow, Trade


# ----------------------------------------------------------------- M2 + M4

def test_kriterien_text_nennt_sl_neutral_nicht_beweispflicht():
    """M2: Der Kriterien-Text wird in alle drei Prompts injiziert und darf
    die bindende Neutral-Regel nicht im selben Prompt widersprechen."""
    text = pipeline._kriterien_text({})
    assert "neutral" in text
    assert "muss BEWIESEN" not in text
    assert "kein Abwertungsgrund" in text


def test_regelwerk_und_hilfe_beschreiben_das_aktuelle_system():
    """M4: GUI-sichtbare Texte — Vierfach-Maximum und SL-neutral statt
    vor-28.09.-Regelung."""
    md = regelwerk.regelwerk_markdown({"schranke_eq_dd_pct": 30,
                                       "min_ertrag_pct_monat": 5})
    assert "Max-DD aus Kursen" in md
    assert "muss bewiesen sein" not in md
    assert "Ohne bewiesenen Stop kein Kandidat" not in md
    assert "neutral" in md

    from mqlkiscanner import help_content
    hilfe = str(help_content.HELP_CONTENT)  # robust gegen Strukturänderung
    assert "der höchste Wert zählt" in hilfe


# ------------------------------------------------------- M3: Meta-Feld

def test_chat_meta_enthaelt_pro_call_total_tokens(monkeypatch):
    """M3: call_meta muss total_tokens DIESES Calls liefern — die Audit-
    Spalte analyses.tokens darf nicht den kumulierten Lauf-Zähler bekommen."""
    c = llm_client.GlmClient("m1", "m2", max_total_tokens=1_000_000)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"},
                                 "finish_reason": "stop"}],
                    "usage": {"total_tokens": 77, "prompt_tokens": 40,
                              "completion_tokens": 37}}

    monkeypatch.setattr(llm_client.requests, "post",
                        lambda *a, **kw: FakeResp())
    monkeypatch.setattr(llm_client.secrets_store, "get_secret",
                        lambda *_: "key")
    meta: dict = {}
    c.chat("Frage", meta_out=meta)
    assert meta["total_tokens"] == 77


# ------------------------------------------------------- M5: Budget hart

def test_budget_blockt_parallel_einen_call_noch_vor_kosten(monkeypatch):
    """M5: Zwei parallele Calls reservieren beide vor dem HTTP-Request —
    sprengt die Reservierung zusammen das Budget, blockt der zweite hart,
    OBWOHL usage.total_tokens noch 0 ist (früher buchten beide über)."""
    import threading

    budget = 20_000
    c = llm_client.GlmClient("m1", "m2", max_total_tokens=budget)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"},
                                 "finish_reason": "stop"}],
                    "usage": {"total_tokens": 1}}

    monkeypatch.setattr(llm_client.requests, "post",
                        lambda *a, **kw: FakeResp())
    monkeypatch.setattr(llm_client.secrets_store, "get_secret",
                        lambda *_: "key")

    prompt = "x" * 300  # Reservierung: max_tokens + len/3 + 1024
    with c._lock:  # erster Call "reserviert", ohne abzuschließen
        c._inflight_tokens = budget - 100
    try:
        c.chat(prompt, max_tokens=8000)
        raise AssertionError("Reservierung ueber Budget muss blocken")
    except llm_client.LlmBudgetError:
        pass
    finally:
        with c._lock:
            c._inflight_tokens = 0
    assert c.usage.total_tokens == 0, "kein Call, keine Kosten"


# ------------------------------------------------- F1: Kapitalbasis-Paar

def _trade(tag: int, profit: float = -1.0) -> Trade:
    return Trade(open_time=datetime(2026, 1, tag, 10),
                 close_time=datetime(2026, 1, tag, 11),
                 direction="Buy", volume=0.1, symbol="XAUUSD",
                 entry_price=1, exit_price=1, profit=profit)


def test_einzahlung_plus_auszahlung_vor_start_gleiches_startkapital():
    """F1: +100/-200 vor dem ersten Trade (netto -100) — Exposure und
    Drawdown müssen dasselbe startkapital/quelle-Paar liefern, nicht mehr
    eines mit und eines ohne externe Kapitalbasis."""
    trades = [_trade(1), _trade(2), _trade(3)]

    class Parsed:
        pass

    p = Parsed()
    p.trades = trades
    p.balances = [
        BalanceRow(time=datetime(2026, 1, 1, 8), amount=100.0),
        BalanceRow(time=datetime(2026, 1, 1, 9), amount=-200.0),
    ]
    p.meta = {}

    dd = drawdown.run(p, kapitalbasis_usd=1000.0, kapitalbasis_quelle="web")
    # Beide Module: positive Einzahlung VOR Start existiert → KEINE Injektion
    assert dd["startkapital_quelle"] == "csv_einzahlungen"
    exp = exposure.run(p, stress_move=None, kapitalbasis_usd=1000.0,
                       kapitalbasis_quelle="web")
    assert exp["startkapital_quelle"] == "csv_einzahlungen"


def test_ohne_jede_einzahlung_injizieren_beide():
    """Kontrolle: Der Normalfall (keine Einzahlung im Export) injiziert in
    BEIDEN Modulen die externe Kapitalbasis."""
    trades = [_trade(1), _trade(2), _trade(3)]

    class Parsed:
        pass

    p = Parsed()
    p.trades = trades
    p.balances = [BalanceRow(time=datetime(2026, 1, 1, 9), amount=-200.0)]
    p.meta = {}

    dd = drawdown.run(p, kapitalbasis_usd=1000.0, kapitalbasis_quelle="web")
    assert dd["startkapital_quelle"] == "web"
    exp = exposure.run(p, stress_move=None, kapitalbasis_usd=1000.0,
                       kapitalbasis_quelle="web")
    assert exp["startkapital_quelle"] == "web"


# ------------------------------------------------- F4: Breakeven-Serie

def test_breakeven_unterbricht_verlustserie():
    """F4: profit == 0 ist kein Verlust — die Serie wird wie von einem
    Gewinn unterbrochen (zählte vorher als Verlust)."""
    trades = [_trade(1, -1.0), _trade(2, -1.0), _trade(3, 0.0),
              _trade(4, -1.0)]

    class Parsed:
        pass

    p = Parsed()
    p.trades = trades
    p.balances = []
    p.meta = {}
    p.has_orderbook = False

    # Serie über stats.compute (Berichts-Kennzahl): 2 Verluste, Breakeven,
    # 1 Verlust → längste Serie 2 (vorher zählte Breakeven mit: 3)
    from mqlkiscanner.parser import ParsedExport
    from mqlkiscanner import stats
    kennzahlen = stats.compute(ParsedExport("x", "positions", trades=trades))
    assert kennzahlen["max_consecutive_losses"] == 2
    assert kennzahlen["losses"] == 3

    # ... und dieselbe Definition in der Stops-Ribbon-Statistik:
    from mqlkiscanner.forensics import stops as stops_mod
    ribbon = stops_mod._ribbon_statistics(trades)
    assert ribbon["max_loss_streak"] == 2


# ------------------------- Review-Handoff 29.09.: offene Befunde L4/L5/L6/L9/L14/L15

def test_martingale_zero_volume_vorgaenger_kein_false_positive():
    """L5: Ein Vorgänger-Trade mit volume == 0 (Export-Artefakt) erzeugte
    ratio ~1e7 → Phantom-Median > 1,3 → falsche harte rote Ampel."""
    from mqlkiscanner.forensics import martingale as mg
    from mqlkiscanner.models import Trade

    def T(d, vol, profit, kommission=0.0):
        return Trade(open_time=datetime(2026, 1, d, 10),
                     close_time=datetime(2026, 1, d, 11),
                     direction="Buy", volume=vol, symbol="XAUUSD",
                     entry_price=1, exit_price=1, profit=profit,
                     commission=kommission)

    class P:
        trades = [T(1, 0.0, -5.0), T(2, 0.01, 3.0),
                  T(3, 0.0, -5.0), T(4, 0.01, 3.0),
                  T(5, 0.0, -5.0), T(6, 0.01, 3.0)]
    ergebnis = mg.run(P())
    assert ergebnis["flag"] is False
    assert ergebnis["n_after_loss"] == 0  # alle Paare hatten Zero-Volumen


def test_martingale_zaehlt_nach_kommission_als_verlust():
    """L9: profit +2 brutto, net -3 (Verlust nach Kommission) — die Ratio
    gehört in die Nach-Verlust-Menge (gleiches Mass wie Kurven)."""
    from mqlkiscanner.forensics import martingale as mg
    from mqlkiscanner.models import Trade

    # profit +2.0 brutto, Kommission -5.0 -> netto -3.0 (Verlust)
    a1 = Trade(open_time=datetime(2026, 1, 1, 10), close_time=datetime(2026, 1, 1, 11),
               direction="Buy", volume=0.01, symbol="XAUUSD",
               entry_price=1, exit_price=1, profit=2.0, commission=-5.0)
    b1 = Trade(open_time=datetime(2026, 1, 2, 10), close_time=datetime(2026, 1, 2, 11),
               direction="Buy", volume=0.02, symbol="XAUUSD",
               entry_price=1, exit_price=1, profit=1.0)

    class P:
        trades = [a1, b1]
    ergebnis = mg.run(P())
    assert ergebnis["n_after_loss"] == 1
    assert ergebnis["median_ratio_after_loss"] == 2.0


def test_martingale_json_nennt_per_symbol_max():
    """L15(a): flag ist per-Symbol-OR, median global — das Max-Feld zeigt
    dem LLM das treibernde Symbol, ohne das Verhalten zu ändern."""
    from mqlkiscanner.forensics import martingale as mg
    from mqlkiscanner.models import Trade

    def T(d, vol, profit, symbol):
        return Trade(open_time=datetime(2026, 1, d, 10),
                     close_time=datetime(2026, 1, d, 11),
                     direction="Buy", volume=vol, symbol=symbol,
                     entry_price=1, exit_price=1, profit=profit)

    # XAU: Verlust mit 0.01, Nachfolger 0.02 -> Ratio 2.0 (Martingale-Treiber)
    xau = [T(d, 0.01 if d % 2 else 0.02, -1.0 if d % 2 else 2.0, "XAUUSD")
           for d in range(1, 7)]
    # EUR: konstant 0.01 -> Ratio 1.0
    eur = [T(d, 0.01, -1.0 if d % 2 else 2.0, "EURUSD") for d in range(7, 15)]

    class P:
        trades = xau + eur
    ergebnis = mg.run(P())
    assert "median_ratio_after_loss_per_symbol_max" in ergebnis
    # Das L15-Szenario im Vollzug: globales Median 1.0 (kein Martingale),
    # flag true (XAU treibt), Max-Feld 2.0 zeigt das treibernde Symbol.
    assert ergebnis["median_ratio_after_loss"] == 1.0
    assert ergebnis["flag"] is True
    assert ergebnis["median_ratio_after_loss_per_symbol_max"] == 2.0


def _probe_trade(symbol: str):
    class T:
        pass
    t = T()
    t.open_time = datetime(2026, 1, 5, 14, 30)
    t.close_time = datetime(2026, 1, 5, 15, 30)
    t.entry_price = 2400.0
    t.exit_price = 2401.0
    t.symbol = symbol
    return t


def _bar(stunde_epoch: int, tief: float, hoch: float) -> dict:
    return {"time": stunde_epoch, "open": 2400.0, "high": hoch,
            "low": tief, "close": 2400.5, "tick_volume": 10}


def test_equity_reko_gmt_mixed_case_symbol():
    """L4: GMT-Probe mit gemischter Symbol-Schreibweise (xauusd.sc) muss
    denselben Offset finden wie mit UPPERCASE — vorher idx=None → Skip.
    Enge Baender je Stunde, damit NUR Shift 0 volle Trefferquote erreicht
    (kein Plateau-Skip)."""
    from mqlkiscanner.forensics import equity_rekonstruktion as eq

    t = _probe_trade("xauusd.sc")
    o = int(datetime(2026, 1, 5, 14, 0).replace(
        tzinfo=__import__("datetime").timezone.utc).timestamp())
    bars = [_bar(o, 2380.0, 2420.0), _bar(o + 3600, 2440.0, 2460.0)]
    t.exit_price = 2450.0  # nur in der 15:00-Bar, nicht in der 14:00-Bar
    ergebnis = eq.ermittle_gmt_offset([t], {"XAUUSD.SC": bars})
    assert ergebnis["offset_s"] == 0
    assert ergebnis["trefferquote"] == 1.0


def test_gmt_probe_nimmt_nicht_die_vorherige_bar():
    """L6: Fehlt die exakte Stunde (Wochenende), darf die GMT-Probe NICHT
    die vorherige Bar als Kurs behandeln — kein Treffer statt Treffer."""
    from mqlkiscanner.forensics import equity_rekonstruktion as eq

    t = _probe_trade("XAUUSD")
    t.exit_price = 2430.0  # ausserhalb JEDES existierenden Bandes
    o = int(datetime(2026, 1, 5, 14, 0).replace(
        tzinfo=__import__("datetime").timezone.utc).timestamp())
    bars = [_bar(o, 2390.0, 2410.0)]  # KEINE 15:00-Bar
    ergebnis = eq.ermittle_gmt_offset([t], {"XAUUSD": bars})
    # Alt (bisect-1): 2430 gegen die geliehene 14:00-Bar -> Miss -> 0.5
    # -> kein Offset. Exakter Lookup: keine 15:00-Bar -> nicht geprueft
    # -> Quote 1.0 aus dem legitimen Open-Check, Offset eindeutig 0.
    assert ergebnis["offset_s"] == 0
    assert ergebnis["trefferquote"] == 1.0
