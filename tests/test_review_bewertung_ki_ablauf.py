# -*- coding: utf-8 -*-
"""Review 29.09. „Bewertung + KI-Ablauf": nachgestellte Fehlerfälle —
F-3 (Schranke vor Fehler), F-4 (Berichtsbasis), F-5 (Ertrag im Prompt),
F-11 (length-Retry), F-15 (Melder-Erstlauf), F-17 (score-Robustheit)."""
from __future__ import annotations

from mqlkiscanner import config, pipeline, scoring
from mqlkiscanner.llm import client as llm_client


def _result(**kw) -> pipeline.ScanResult:
    base = dict(
        id=999111, name="Muster", dd_equity_pct=45.0, trading_dd_pct=None,
        martingale_flag=False, martingale_evidenz=[], stop_evidence="none",
        ertrag_monat_pct=12.0, score=4.0, schranke_verletzt=True,
        forensik_vorhanden=True, wochen=80, abonnenten=120,
        abo_preis_usd=30.0, growth_pct=200.0, pf=1.4, dd_balance_pct=None,
    )
    base.update(kw)
    return pipeline.ScanResult(**base)


# ----------------------------------------------------------------- F-3

def test_schranke_verletzt_bleibt_rot_trotz_zusatzfehler():
    """F-3: 45 % Drawdown + beliebiger Fehler = ROT (harte Ablehnung aus
    Plattformdaten), nicht stilles Weiss."""
    ampel, urteil = pipeline.ampel_for(
        _result(fehler="Zusatzprüfung gescheitert", schranke_verletzt=True),
        {"schranke_eq_dd_pct": 30})
    assert ampel == "🔴"
    assert "Schranke" in urteil


def test_fehler_ohne_schrankenverletzt_bleibt_weiss():
    ampel, _ = pipeline.ampel_for(
        _result(fehler="Export abgebrochen", dd_equity_pct=10,
                schranke_verletzt=False),
        {"schranke_eq_dd_pct": 30})
    assert ampel == "⚪"


# ----------------------------------------------------------------- F-4

def test_berichtsbasis_ignoriert_abonnenten_und_preis():
    """F-4: +1 Abonnent (oder Abo-Preis) ist keine neue Beweislage — die
    Basis darf sich nicht aendern, sonst verschwinden KI-Berichte nach
    jedem Scan aus der Ansicht."""
    settings = {"schranke_eq_dd_pct": 30, "min_ertrag_pct_monat": 5}
    basis_a = pipeline.report_basis_for(_result(abonnenten=120), settings)
    basis_b = pipeline.report_basis_for(_result(abonnenten=121), settings)
    assert basis_a == basis_b

    basis_c = pipeline.report_basis_for(_result(abo_preis_usd=99.0), settings)
    assert basis_a == basis_c


def test_berichtsbasis_aendert_sich_bei_risikofakt():
    """Kontrolle: Ein risikorelevanter Fakt (DD) aendert die Basis weiterhin."""
    settings = {"schranke_eq_dd_pct": 30, "min_ertrag_pct_monat": 5}
    assert (pipeline.report_basis_for(_result(dd_equity_pct=45.0), settings)
            != pipeline.report_basis_for(_result(dd_equity_pct=10.0), settings))


# ----------------------------------------------------------------- F-5

def test_gesamtbericht_prompt_nennt_ertrag_beobachtung_nicht_ablehnung():
    """F-5: Der Prompt widersprach der Engine-Ampel (Ertrag < Schwelle =
    GELB 'nur Beobachtung') mit 'bedeutet Ablehnung'."""
    text = (config.ROOT / "config" / "prompts" / "gesamtbericht.md") \
        .read_text(encoding="utf-8") if hasattr(config, "ROOT") else None
    if text is None:
        from pathlib import Path
        text = Path(__file__).resolve().parents[1].joinpath(
            "config", "prompts", "gesamtbericht.md").read_text(encoding="utf-8")
    assert "Eigene geometrische Rendite unter der dort genannten Monatsschwelle bedeutet" in text
    assert "keine harte Ablehnung" in text
    assert "nur Beobachtung" in text


# ----------------------------------------------------------------- F-11

def test_client_holt_length_abbruch_mit_doppeltem_limit(monkeypatch):
    """F-11: finish_reason=length ist bezahlt — ein EINMALIGER Retry mit
    doppeltem Limit rettet den Bericht statt ihn zu verwerfen."""
    aufrufe = {"n": 0}

    class FakeResp:
        status_code = 200

        def json(self):
            aufrufe["n"] += 1
            if aufrufe["n"] == 1:
                return {"choices": [{"message": {"content": "abgebrochen"},
                                     "finish_reason": "length"}],
                        "usage": {"total_tokens": 100, "prompt_tokens": 50,
                                  "completion_tokens": 50}}
            return {"choices": [{"message": {"content": "voller Bericht"},
                                 "finish_reason": "stop"}],
                    "usage": {"total_tokens": 130, "prompt_tokens": 50,
                              "completion_tokens": 80}}

    monkeypatch.setattr(llm_client.requests, "post",
                        lambda *a, **kw: FakeResp())
    monkeypatch.setattr(llm_client.secrets_store, "get_secret",
                        lambda *_: "key")
    c = llm_client.GlmClient("m1", "m2", max_total_tokens=1_000_000)
    meta: dict = {}
    assert c.chat("Bericht bitte", max_tokens=1000, meta_out=meta) == "voller Bericht"
    assert aufrufe["n"] == 2
    assert c.usage.total_tokens == 230  # beide Antworten bezahlt und gezaehlt
    assert c._inflight_tokens == 0      # Reservierung sauber aufgeloest


def test_client_length_ohne_budget_fuer_retry_bleibt_fehler(monkeypatch):
    """F-11-Rand: Reicht das Budget fuer den Retry nicht, bleibt es beim
    klaren Incomplete-Fehler (keine stillen Ueberbuchungen)."""
    aufrufe = {"n": 0}

    class FakeResp:
        status_code = 200

        def json(self):
            aufrufe["n"] += 1
            return {"choices": [{"message": {"content": "x"},
                                 "finish_reason": "length"}],
                    "usage": {"total_tokens": 50, "prompt_tokens": 20,
                              "completion_tokens": 30}}

    monkeypatch.setattr(llm_client.requests, "post",
                        lambda *a, **kw: FakeResp())
    monkeypatch.setattr(llm_client.secrets_store, "get_secret",
                        lambda *_: "key")
    # Budget reicht fuer den ERSTEN Call (800+5+1024), nicht fuer den
    # Retry mit doppeltem Limit (1600+5+1024)
    c = llm_client.GlmClient("m1", "m2", max_total_tokens=1900)
    try:
        c.chat("Bericht", max_tokens=800)
        raise AssertionError("Retry ohne Budget muss fehlschlagen")
    except llm_client.LlmIncompleteResponseError:
        pass
    assert c._inflight_tokens == 0


# ----------------------------------------------------------------- F-15

def test_melder_erstlauf_macht_historie_nicht_zur_alarmflut(monkeypatch):
    """F-15: Beim ersten Lauf (letzte_id=0) mit langer Historie gibt es EINE
    zusammenfassende Info statt bis zu 100 Einzel-P3-Alerts."""
    from mqlkiscanner.agenten import journal, melder

    wechsel = [{"id": i, "signal_id": 1, "name": f"S{i}", "ampel_alt": "🟢",
                "ampel_neu": "🔴", "richtung": "verschlechterung", "gruende": []}
               for i in range(1, 11)]
    monkeypatch.setattr(melder.db, "list_ampel_wechsel", lambda limit=100: wechsel)
    monkeypatch.setattr(melder.journal, "stuerung_lesen",
                        journal.steuerung_lesen, raising=False)
    melder.pruefe_neue_wechsel(log=lambda *_: None)
    alerts = [m for m in journal.meldungen_lesen(limit=50)
              if m["typ"] == "alert"]
    infos = [m for m in journal.meldungen_lesen(limit=50)
             if m["typ"] == "info" and "Historie" in m.get("titel", "")]
    assert alerts == [], "keine Alarmflut aus alter Historie"
    assert len(infos) == 1
    # Marker steht auf dem neuesten Stand:
    assert int(journal.steuerung_lesen()[melder.STEUERUNG_WECHSEL_KEY]) == 10


# ----------------------------------------------------------------- F-17

def test_score_ignoriert_fremde_gewichts_keys():
    """F-17: Fehlerhafte/Fremd-Keys in den Gewichten dürfen den Lauf nicht
    mit KeyError abbrechen."""
    dims = {"drawdown": 2.0, "struktur": 3.0, "verlust": 2.0,
            "konsistenz": 3.0, "kopie": 3.0}
    wert = scoring.score(dims, weights={"drawdown": 0.4, "kaputt": 9.9})
    assert 1.0 <= wert <= 10.0
