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
    assert "Reko-EQ-DD" in md
    assert "muss bewiesen sein" not in md
    assert "Ohne bewiesenen Stop kein Kandidat" not in md
    assert "neutral" in md

    from mqlkiscanner import help_content
    hilfe = str(help_content.HELP_CONTENT)  # robust gegen Strukturänderung
    assert "der höchste der vier zählt" in hilfe


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
