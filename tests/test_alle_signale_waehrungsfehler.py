"""Historische Währungsfehler dürfen Ziel-USD und aktuellen Beleg nicht vermischen."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import alle_signale_ui as ui
from mqlkiscanner import db, katalog, pipeline, scan_worker


def _fehler(signal_id=123, name="Historisches Signal", currency="unbekannt/uneindeutig"):
    return (f"#{signal_id} {name}: ValueError: Kontowährung {currency}: "
            "USD-Forensik gesperrt — keine belegte Umrechnung von Export "
            "und Kontobasis in USD.")


def _result(signal_id=123, currency=None, quelle="mql5"):
    return SimpleNamespace(id=signal_id, account_currency=currency, quelle=quelle,
                           platform="MT5", url=f"https://example.invalid/signals/{signal_id}")


@pytest.mark.parametrize("currency", ["", "unknown", "UNKNOWN", "unbekannt",
                                      "uneindeutig", "unbekannt/uneindeutig"])
def test_unbekannte_kontowaehrung_bleibt_trotz_usd_ziel_unbekannt(currency):
    rows = ui.studien_batch_unbekannte_waehrungen([_fehler(currency=currency)], [_result()])
    assert len(rows) == 1
    row = rows[0]
    assert row["Signal-ID"] == "123"
    assert row["Kontowährung im Batch"] == "unbekannt / nicht belegt"
    assert row["Aktueller Nachweis"] == "weiterhin nicht belegt"
    assert row["Quelle"] == "mql5" and row["Plattform"] == "MT5"
    assert row["Signal öffnen"] == "https://example.invalid/signals/123"


@pytest.mark.parametrize("currency,expected", [("USD", "USD"), ("EUR", "EUR"),
                                             ("USC", "USC"), (None, "weiterhin nicht belegt"),
                                             ("unknown", "weiterhin nicht belegt")])
def test_aktueller_nachweis_aendert_den_historischen_batchfehler_nicht(currency, expected):
    row = ui.studien_batch_unbekannte_waehrungen([_fehler()], [_result(currency=currency)])[0]
    assert row["Kontowährung im Batch"] == "unbekannt / nicht belegt"
    assert row["Aktueller Nachweis"] == expected


def test_verschwundenes_signal_bleibt_ohne_fremde_quellenzuordnung_sichtbar():
    row = ui.studien_batch_unbekannte_waehrungen(
        [_fehler(name="Nicht mehr im Katalog")], [_result(signal_id=456, currency="USD")])[0]
    assert row["Signal"] == "Nicht mehr im Katalog"
    assert row["Signal-ID"] == "123"
    assert row["Aktueller Nachweis"] == "Signal nicht mehr in der Übersicht"
    assert row["Quelle"] == "nicht zugeordnet" and row["Plattform"] == "—"
    assert row["Signal öffnen"] is None


def test_mehrdeutige_signal_id_verwendet_keine_der_quellen_oder_waehrungen():
    rows = ui.studien_batch_unbekannte_waehrungen([_fehler()], [
        _result(currency="USD", quelle="mql5"), _result(currency="EUR", quelle="robo")])
    assert len(rows) == 1
    assert rows[0]["Aktueller Nachweis"] == "Signal-ID mehrdeutig"
    assert rows[0]["Quelle"] == "nicht zugeordnet"
    assert rows[0]["Plattform"] == "—" and rows[0]["Signal öffnen"] is None


def test_doppelte_meldungen_werden_einmal_in_erster_reihenfolge_angezeigt():
    first, second = _fehler(), _fehler(456, "Weiteres Signal")
    rows = ui.studien_batch_unbekannte_waehrungen(
        [first, first, second, first, second], [_result(), _result(signal_id=456)])
    assert [row["Signal-ID"] for row in rows] == ["123", "456"]


@pytest.mark.parametrize("error", [
    _fehler(currency="USD"), _fehler(currency="EUR"), _fehler(currency="USC"),
    "#123 Historisches Signal: ValueError: ungültiges Volumen oder Handelszeitraum",
    "#123 Historisches Signal: RuntimeError: Kursdaten nicht verfügbar",
    "Batch abgebrochen: RuntimeError: Terminal nicht verfügbar",
    "#123 Historisches Signal: RuntimeError: " + _fehler().split("ValueError: ", 1)[1],
])
def test_andere_batchfehler_und_bekannte_kontowaehrungen_werden_ignoriert(error):
    assert ui.studien_batch_unbekannte_waehrungen([error], [_result()]) == []


def _waehrungstabellen(at):
    return [item.value for item in at.dataframe if "Kontowährung im Batch" in item.value.columns]


def test_seite_zeigt_und_versteckt_historische_fehler_mit_aktuellem_nachweis(monkeypatch):
    from streamlit.testing.v1 import AppTest

    db.init_db()
    recovered = pipeline.ScanResult(id=123, name="Jetzt belegt", quelle="mql5",
                                    platform="MT5", account_currency="USD")
    unknown = pipeline.ScanResult(id=456, name="Weiter offen", quelle="mql5", platform="MT5")
    errors = [_fehler(name="Alter Name"), _fehler(456, "Weiter offen")]
    original_errors = list(errors)
    run = SimpleNamespace(workflow={"typ": "studien_batch"}, thread=None,
                          control={"fertig": True, "gerechnet": 0, "fehler": errors,
                                   "summary": "0 gerechnet · 0 übersprungen · 2 Fehler"})
    monkeypatch.setattr(scan_worker, "active_run", lambda: run)
    monkeypatch.setattr(scan_worker, "start", lambda *a, **kw: pytest.fail("Kein neuer Batch"))
    monkeypatch.setattr(db, "katalog_sync_status", lambda: {
        "mql5": {"gelaufen_am": "2026-10-17", "anzahl": 2, "fehler": None}})
    monkeypatch.setattr(pipeline, "results_from_db", lambda **kw: [recovered, unknown])
    monkeypatch.setattr(katalog, "katalog_resultate", lambda **kw: ([], {}))
    monkeypatch.setattr(katalog, "lade_signal_daten", lambda *a, **kw: pytest.fail("Kein Nachladen"))

    page = Path(__file__).resolve().parents[1] / "app_pages" / "alle_signale.py"
    at = AppTest.from_file(str(page), default_timeout=30).run()
    assert not at.exception, at.exception
    assert not _waehrungstabellen(at)
    assert "anzeigen (2)" in at.button(key="alle_signale_batch_waehrungen").label

    # Die Fehlerliste umfasst auch Signale, die der lokale Suchfilter ausblendet.
    at.text_input(key="alle_signale_suche").set_value("Weiter offen").run()
    at.button(key="alle_signale_batch_waehrungen").click().run()
    assert not at.exception, at.exception
    table, = _waehrungstabellen(at)
    by_id = table.set_index("Signal-ID")
    assert list(table["Signal-ID"]) == ["123", "456"]
    assert by_id.loc["123", "Signal"] == "Alter Name"
    assert by_id.loc["123", "Aktueller Nachweis"] == "USD"
    assert by_id.loc["456", "Aktueller Nachweis"] == "weiterhin nicht belegt"
    assert set(table["Kontowährung im Batch"]) == {"unbekannt / nicht belegt"}
    assert any("durch die Seitenfilter ausgeblendete Signale" in caption.value for caption in at.caption)

    at.run()
    assert "ausblenden (2)" in at.button(key="alle_signale_batch_waehrungen").label
    at.button(key="alle_signale_batch_waehrungen").click().run()
    assert not at.exception, at.exception
    assert not _waehrungstabellen(at)
    assert run.control["fehler"] == original_errors
