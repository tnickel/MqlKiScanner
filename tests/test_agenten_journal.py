# -*- coding: utf-8 -*-
"""Agenten-Journal: Läufe, Schritte (das Protokoll), Budget, Steuerung.

Phase A des Agentenbetriebs (doc/19_agentenbetrieb-bauplan.md, Abschnitt 6):
append-only Chroniken — kein UPDATE auf Inhalte, kein DELETE. LLM-Schritte
speichern den vollständigen Prompt und die vollständige Antwort.
"""
from mqlkiscanner.agenten import journal


def test_init_zweimal_idempotent():
    journal.init_journal()
    journal.init_journal()  # darf nicht fehlschlagen
    assert journal.list_laeufe() == []


def test_lauf_lebenszyklus():
    lauf_id = journal.lauf_starten("dirigent", quelle="test")
    assert journal.lauf_ist_aktiv(lauf_id)
    journal.lauf_abschliessen(lauf_id, "ok", "Testlauf")
    assert not journal.lauf_ist_aktiv(lauf_id)

    laeufe = journal.list_laeufe()
    assert len(laeufe) == 1
    assert laeufe[0]["rolle"] == "dirigent"
    assert laeufe[0]["quelle"] == "test"
    assert laeufe[0]["status"] == "ok"
    assert laeufe[0]["zusammenfassung"] == "Testlauf"
    assert laeufe[0]["ende"]  # Abschluss schreibt Endzeit


def test_abschluss_nur_aus_laeuft():
    """Ein abgeschlossener Lauf wird durch erneuten Aufruf nicht geändert."""
    lauf_id = journal.lauf_starten("melder", quelle="test")
    journal.lauf_abschliessen(lauf_id, "ok", "erste")
    journal.lauf_abschliessen(lauf_id, "fehler", "zweite")  # ignoriert
    lauf = journal.list_laeufe(rolle="melder")[0]
    assert lauf["status"] == "ok"
    assert lauf["zusammenfassung"] == "erste"


def test_schritt_mit_vollstaendigem_prompt_und_antwort():
    lauf_id = journal.lauf_starten("dirigent", quelle="test")
    schritt_id = journal.schritt_protokollieren(
        lauf_id, "dirigent", "llm_entscheidung",
        prompt="## Lagestatus\n{...}", antwort='{"aktionen": []}',
        modell="glm-5.3", tokens=1234, dauer_s=2.5,
        detail={"filter": {"aktionen": []}})
    detail = journal.schritt_lesen(schritt_id)
    assert detail["prompt"].startswith("## Lagestatus")
    assert detail["antwort"] == '{"aktionen": []}'
    assert detail["modell"] == "glm-5.3"
    assert detail["tokens"] == 1234
    assert detail["detail"]["filter"] == {"aktionen": []}


def test_list_schritte_filter_rolle_und_tag():
    lauf = journal.lauf_starten("dirigent", quelle="test")
    journal.schritt_protokollieren(lauf, "dirigent", "lagestatus")
    journal.schritt_protokollieren(lauf, "melder", "digest")
    nur_dirigent = journal.list_schritte(rolle="dirigent")
    assert [s["schritt"] for s in nur_dirigent] == ["lagestatus"]
    heute = journal.list_schritte(tag=nur_dirigent[0]["ts"][:10])
    assert len(heute) == 2  # Tag-Filter ohne Rollen-Filter
    assert journal.list_schritte(tag="1999-01-01") == []


def test_tokens_heute_und_monat_zaehlen_nur_llm_schritte():
    lauf = journal.lauf_starten("dirigent", quelle="test")
    journal.schritt_protokollieren(lauf, "dirigent", "lagestatus")  # Code: 0
    journal.schritt_protokollieren(lauf, "dirigent", "llm_entscheidung",
                                   prompt="p", antwort="a", tokens=500)
    assert journal.tokens_heute() == 500
    assert journal.tokens_monat() == 500


def test_lauf_heute_erfolgreich_quellenbezogen():
    lauf = journal.lauf_starten("dirigent", quelle="daemon")
    assert not journal.lauf_heute_erfolgreich("dirigent", "daemon")
    journal.lauf_abschliessen(lauf, "ok")
    assert journal.lauf_heute_erfolgreich("dirigent", "daemon")
    assert not journal.lauf_heute_erfolgreich("dirigent", "cli")


def test_steuerung_roundtrip():
    journal.steuerung_setzen("pid", "4711")
    journal.steuerung_setzen("stop_wunsch", "1")
    assert journal.steuerung_lesen() == {"pid": "4711", "stop_wunsch": "1"}
    journal.steuerung_setzen("stop_wunsch", "0")
    assert journal.steuerung_lesen()["stop_wunsch"] == "0"


def test_letzter_lauf_rolle_und_leer():
    assert journal.letzter_lauf() is None
    journal.lauf_abschliessen(journal.lauf_starten("chef", quelle="test"), "ok")
    assert journal.letzter_lauf(rolle="chef")["rolle"] == "chef"
    assert journal.letzter_lauf(rolle="melder") is None


def test_aktive_rollen_ignoriert_verwaiste_laeufe():
    """Anzeige-Schwelle: ein 'laeuft'-Eintrag mit altem Start gilt als
    verwaist (Crash-Rest) — die Rolle darf nicht dauerhaft leuchten."""
    from mqlkiscanner import db

    lauf_id = journal.lauf_starten("betreuer", quelle="test")
    assert "betreuer" in journal.aktive_rollen()
    with db._connect() as conn:
        conn.execute("UPDATE agenten_laeufe SET start=? WHERE id=?",
                     ("2020-01-01 00:00:00", lauf_id))
    assert "betreuer" not in journal.aktive_rollen()
