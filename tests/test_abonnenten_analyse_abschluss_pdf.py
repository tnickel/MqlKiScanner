"""Final PDF disclosures must preserve uncertainty and original decisions."""
from mqlkiscanner.abonnenten_analyse_ki import abschluss_anhang


def test_existing_report_without_new_workflow_keeps_original_body():
    assert abschluss_anhang({"bericht_markdown": "Existing report"}) == ""


def test_final_appendix_exposes_native_interval_scaling_profit_and_h1_limits():
    entry = {"abo_trend": {"verified": True, "delta_7": 50, "basis_7": 100,
                            "basis_7_ts": "2026-10-17", "aktuell": 150,
                            "aktuell_ts": "2026-10-24", "messabstand_7_tage": 7.0},
             "abo_quellen_durchschnitt": 500, "abo_quellen_referenz_n": 200,
             "abo_zufluss_skaliert": .1, "equity_dd_pct": 12.5, "retdd_jahr": 3.4,
             "dauer_monate": 2.6,
             "equity": {"abdeckung_pct_raw": 96.9565, "trades_ohne_h1_floating_messpunkt": 36,
                        "trades_total": 98, "original_broker": None},
             "forensik": {"stats": {"net": 8500}}}
    text = abschluss_anhang(entry)
    assert "+50" in text and "2026-10-17" in text and "2026-10-24" in text
    assert "500 = 0.1" in text and "200 positive Anbieter" in text
    assert "gesamten Plattform" in text and "Bruttozuwanderung" in text
    assert "8500 USD" in text and "H1-Bar-Schlüssen" in text and "Intrabar" in text
    assert "2.6 Monate" in text and "kein beobachtetes Jahresergebnis" in text
    assert "96.96 %" in text and "36 von 98" in text
    assert "ursprünglichen Broker ist nicht belegt" in text and "Equity-Untergrenze" in text


def test_final_appendix_preserves_blocked_decision_and_original_report_binding():
    entry = {"ki_klaerung_gesperrt": True, "ki_pruefentscheidungen": [{
        "hinweis": {"text": "Unbelegter Kapitalfluss"}, "entscheidung": "nicht_beurteilbar",
        "auswirkung": "bewertungsgrundlage_unzureichend", "begruendung": "Zeitpunkt fehlt.",
        "beleg_refs": ["equity.flows"], "herkunft": [{"bericht_stufe": "top5", "bericht_basis": "original-sha"}]}]}
    text = abschluss_anhang(entry)
    assert "keine Freigabe" in text and "Unbelegter Kapitalfluss" in text
    assert "Zeitpunkt fehlt." in text and "equity.flows" in text and "original-sha" in text


def test_unknown_history_is_never_exported_as_zero_flow():
    text = abschluss_anhang({"abo_trend": {"verified": False, "delta_7": None}})
    assert "keine Nulländerung" in text
    assert "+0" not in text
