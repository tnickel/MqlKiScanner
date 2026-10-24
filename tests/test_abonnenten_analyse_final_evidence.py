"""New selection measurements must be available as actual model evidence."""
from mqlkiscanner import abonnenten_analyse_ki as ki
from mqlkiscanner.abonnenten_analyse_klaerung import allowed_evidence


def test_native_trend_and_source_normalisation_share_adjudication_register():
    entry = {"signal_ref": 7, "trades": 50,
             "abo_trend": {"verified": True, "delta_7": 5, "basis_7_ts": "2026-10-17",
                           "aktuell_ts": "2026-10-24"},
             "abo_quellen_durchschnitt": 50, "abo_quellen_referenz_n": 200,
             "abo_zufluss_skaliert": .1, "abo_zufluss_perzentil": 50}
    facts, candidate = ki.evidence_inputs(entry)
    assert facts["abonnenten_trend"]["delta_7"] == 5
    assert candidate["abo_quellen_durchschnitt"] == 50
    allowed = allowed_evidence(entry)
    assert "abonnenten_trend.delta_7" in allowed
    assert "kandidat.abo_zufluss_skaliert" in allowed
    assert ki._evidence_register(facts, candidate).keys() <= allowed


def test_finalist_comparison_allows_supplied_flow_and_profit_not_invented_fields():
    comparison = [{"signal_ref": 7, "abo_zufluss_skaliert": .1,
                   "abo_quellen_durchschnitt": 50, "abo_delta_7": 5, "profit_usd": 100}]
    allowed = ki._comparison_refs(comparison)
    assert "vergleich[0].abo_delta_7" in allowed
    assert "vergleich[0].profit_usd" in allowed
    assert "vergleich[0].invented_profit" not in allowed
