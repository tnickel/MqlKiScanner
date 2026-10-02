"""Offline contracts for SL evidence instructions and real prompt builders.

These tests check the instructions actually delivered, reset/default parity
and preservation of supplied figures. They make no claim that a model obeys
the instructions; no model or external service is called.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mqlkiscanner import pipeline
from mqlkiscanner.llm import prompt_fill, prompts


ROOT = Path(__file__).resolve().parents[1]
KINDS = tuple(prompts.DEFAULTS)


def _assert_evidence_contract(text: str) -> None:
    flat = " ".join(text.split())
    # Distinguish direct SL evidence from TP-only or provider claims.
    assert "dokumentierter S/L-Wert im Orderbuch" in flat
    assert "`[sl]`-Exit ist Entlastung fuer die belegten Positionen" in flat
    assert "kombinierte SL/TP-Anzahl" in flat
    assert "beweist keinen Verluststopp" in flat
    # Repeat loss-only closure events support plausibility, never direct proof.
    assert "Wiederholte homogene, zeitlich synchronisierte Schliessungen" in flat
    assert "jede beteiligte Position NETTO im Verlust" in flat
    assert "Selbst als begruendet/plausibel eingestufte Signaturen sind kein bewiesener SL" in flat
    assert "`plausibel` = plausible Schutzdisziplin" in flat
    assert "`hinweis` = begrenztes Indiz" in flat
    assert "`nicht_beobachtet` = neutral, kein Negativbeweis" in flat
    assert "Hinweis nicht zum plausiblen oder bewiesenen Schutz auf" in flat
    assert "Grid-Reset, Margin-Stop-Out oder manueller Eingriff" in flat
    assert "tilgen weder Grid-/Martingale-Risiko noch gemessenen Drawdown" in flat
    assert "Gewinn- oder gemischte Schliessungsgruppen und ein einzelnes Ereignis" in flat
    assert "sind KEIN Nachweis fuer internen Stop-Schutz" in flat
    # Low measured equity DD and absent signatures cannot become SL proof/malus.
    assert "Floating ist stuetzende Historie" in flat
    assert "kein SL-Beweis und keine Garantie" in flat
    assert "NEUTRAL und darf weder Urteil noch Auswahl oder Gewichtung abwerten" in flat
    assert "fehlende Verlustgruppen sind kein Negativbeweis" in flat
    # Keep a static exposure scenario separate from realized or capped losses.
    assert "Stop-Ausloesung und Korbschliessung werden nicht dynamisch modelliert" in flat
    assert "rechne den Schock NICHT neu" in flat
    assert "ziehe keinen angenommenen SL-Abzug ab" in flat
    assert "kein sicher beobachteter ungebremster Verlust" in flat
    assert "keine Verlustobergrenze" in flat
    assert "Gold Spike" not in text


@pytest.mark.parametrize("kind", KINDS)
def test_sl_contract_survives_missing_file_and_reset(kind):
    """A reset or missing file must not resurrect inconsistent SL rules."""
    repository = (ROOT / "config/prompts" / f"{kind}.md").read_text(encoding="utf-8")
    assert not prompts.PROMPT_FILES[kind].exists()  # fixture uses temp storage
    assert prompts.load_prompt(kind) == repository == prompts.DEFAULTS[kind]
    prompts.save_prompt(kind, "temporary custom prompt")
    prompts.reset_prompt(kind)
    restored = prompts.load_prompt(kind)
    assert restored == repository
    _assert_evidence_contract(restored)


def test_real_builders_deliver_evidence_contract_and_preserve_code_figures():
    result = pipeline.ScanResult(
        id=987654, name="Generische Strategie", platform="MT5",
        forensik_vorhanden=True, trading_dd_pct=7.25,
        stop_evidence="partial", stop_nachweis="Orderbuch: 2/7 mit SL",
        stop_befund={"positions_with_sl": 2, "positions_total": 7,
                     "schutzsignatur": {"status": "hinweis",
                                         "qualifizierte_verlustgruppen": 2}},
        peak_positionen=7, peak_netto_lots=0.12,
        shock_usd=600.0, shock_pct_max=23.456,
        shock_pct_peak_account=2557.99795, shock_pct_peak_usd=600.0,
        equity_dd_rekonstruiert_pct=8.5,
    )
    trades = json.dumps({"meta": {"trades": 7}, "loss_groups": []})
    facts = pipeline._forensik_json(result)
    entries = json.dumps([{"kandidat": json.loads(pipeline._kandidat_json(result)),
                           "forensik": json.loads(facts)}], ensure_ascii=False)
    generated = {
        "trade_analyse": prompt_fill.build_trade_prompt(result, trades),
        "risiko_analyse": prompt_fill.build_risk_prompt(result, "Kriterien"),
        "gesamtbericht": prompt_fill.build_gesamtbericht_prompt(
            result, "Kriterien", "Trade-Befund", "Risiko-Befund"),
        "portfolio": prompt_fill.build_portfolio_prompt(entries, "Kriterien"),
        "tiefenanalyse": prompt_fill.build_tiefenanalyse_prompt(result, trades),
    }
    for kind, text in generated.items():
        _assert_evidence_contract(text)
        assert "\x00PROMPT_SLOT_" not in text, kind
        for slot in prompt_fill.KNOWN_PLACEHOLDERS:
            assert slot not in text, (kind, slot)
        assert facts in text, kind
        assert '"shock_pct_peak_usd": 600.0' in text
        assert '"shock_pct_max": 23.456' in text
        assert '"stop_evidence": "partial"' in text
        assert '"schutzsignatur": {"status": "hinweis"' in text
        assert '"qualifizierte_verlustgruppen": 2' in text
    assert trades in generated["trade_analyse"]
    assert trades in generated["tiefenanalyse"]


def test_user_trade_template_without_new_forensics_slot_remains_supported():
    """Existing saved templates need no forced rewrite to stay usable."""
    prompts.save_prompt("trade_analyse", "Kandidat: {kandidat_json}\nTrades: {trades_json}")
    result = pipeline.ScanResult(id=123, name="Alte Vorlage")
    text = prompt_fill.build_trade_prompt(result, '{"meta": {"trades": 2}}')
    assert '"name": "Alte Vorlage"' in text
    assert '{"meta": {"trades": 2}}' in text
    assert "{forensik_json}" not in text
