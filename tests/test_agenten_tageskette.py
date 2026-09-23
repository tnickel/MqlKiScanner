# -*- coding: utf-8 -*-
"""Komplettlauf der Tageskette (Ein-Knopf-Workflow, tageskette.py):

Die Kette trägt die Daemon-Reihenfolge in einen Aufruf — ohne Takt-Prüfung,
mit Lock-Disziplin und dokumentierten Sprüngen statt stiller Doppel-Läufe.
Alle Rollen-Einstiegspunkte werden hier gefaket (kein Netz, kein LLM)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner.agenten import journal, lock, tageskette
from mqlkiscanner import config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def protokoll(monkeypatch):
    """Faket alle fünf Einstiegspunkte und zeichnet die Aufrufe auf."""
    from mqlkiscanner.agenten import betreuer, dirigent, markt, melder
    aufrufe: list[str] = []

    monkeypatch.setattr(
        melder, "pruefe_neue_wechsel",
        lambda log=print: aufrufe.append("watcher") or [])
    monkeypatch.setattr(
        dirigent, "tageslauf",
        lambda quelle="daemon", log=print, **k: (
            aufrufe.append(f"dirigent:{quelle}")
            or {"status": "ok", "resultat": "Regelbetrieb freigegeben"}))
    monkeypatch.setattr(
        markt, "tageslauf",
        lambda quelle="daemon", log=print, settings=None, **k: (
            aufrufe.append(f"markt:{quelle}")
            or {"status": "ok", "resultat": "12 Symbole analysiert"}))
    monkeypatch.setattr(
        betreuer, "tageslauf",
        lambda quelle="daemon", log=print, settings=None, **k: (
            aufrufe.append("betreuer")
            or {"resultat": "3 Signale unverändert"}))
    monkeypatch.setattr(
        melder, "tagesdigest",
        lambda quelle="daemon", log=print, settings=None, **k: (
            aufrufe.append("melder")
            or {"status": "ok", "meldung_id": 42}))
    return aufrufe


def test_kette_laeuft_in_daemon_reihenfolge(protokoll):
    ergebnis = tageskette.tageskette(quelle="gui", log=lambda m: None)
    assert protokoll == ["watcher", "dirigent:gui", "markt:gui", "betreuer",
                         "melder"]
    assert ergebnis["status"] == "ok"
    je_rolle = {e["rolle"]: e for e in ergebnis["ergebnisse"]
                if not e.get("schritt")}
    assert set(je_rolle) == set(tageskette.KETTEN_ROLLEN)
    assert all(e["status"] == "ok" for e in je_rolle.values())
    assert "Meldung #42 im Postfach" in je_rolle["melder"]["info"]
    # Der Wechsel-Watcher steht zuerst und zählt nicht als Rollenlauf.
    watcher = ergebnis["ergebnisse"][0]
    assert watcher["schritt"] == "wechsel_watcher"
    assert watcher["info"] == "keine neuen Ampelwechsel"


def test_deaktivierte_rolle_wird_uebersprungen(protokoll, monkeypatch):
    settings = {"agenten_markt_aktiv": False}
    ergebnis = tageskette.tageskette(quelle="gui", log=lambda m: None,
                                     settings=settings)
    assert "markt:gui" not in protokoll
    markt_eintrag = next(e for e in ergebnis["ergebnisse"]
                         if e["rolle"] == "markt")
    assert markt_eintrag["status"] == "skipped"
    assert "deaktiviert" in markt_eintrag["grund"]
    assert ergebnis["status"] == "ok"  # kein Fehler, bewusste Konfiguration


def test_lock_besetzt_dokumentierter_skip_statt_doppellauf(protokoll):
    journal.init_journal()
    with lock.lauf_lock(config.DATA_DIR):
        ergebnis = tageskette.tageskette(quelle="gui", log=lambda m: None)
    # Dirigent (Fake, ohne eigenes Lock) lief; die gesperrten Rollen wurden
    # sauber übersprungen und im Journal begründet.
    assert "dirigent:gui" in protokoll
    assert "markt:gui" not in protokoll and "melder" not in protokoll
    for rolle in ("markt", "betreuer", "melder"):
        eintrag = next(e for e in ergebnis["ergebnisse"]
                       if e["rolle"] == rolle and not e.get("schritt"))
        assert eintrag["status"] == "skipped"
        lauf = journal.list_laeufe(limit=5, rolle=rolle)[0]
        assert lauf["status"] == "skipped"
        assert lauf["quelle"] == "gui"
        assert "Komplettlauf" in lauf["aktion"]
        assert "Kollisionsschutz" in lauf["resultat"]


def test_fehler_einer_rolle_haelt_die_kette_nicht_auf(protokoll, monkeypatch):
    from mqlkiscanner.agenten import markt
    def _bock(quelle="daemon", log=print, settings=None, **k):
        raise RuntimeError("MT5 nicht erreichbar")
    monkeypatch.setattr(markt, "tageslauf", _bock)

    ergebnis = tageskette.tageskette(quelle="cli", log=lambda m: None)
    assert "betreuer" in protokoll and "melder" in protokoll
    markt_eintrag = next(e for e in ergebnis["ergebnisse"]
                         if e["rolle"] == "markt")
    assert markt_eintrag["status"] == "fehler"
    assert "MT5 nicht erreichbar" in markt_eintrag["grund"]
    assert ergebnis["status"] == "teilerfolg"
    assert "3 Rolle(n) ok" in ergebnis["zusammenfassung"]


def test_watcher_fehler_blockiert_die_kette_nicht(protokoll, monkeypatch):
    from mqlkiscanner.agenten import melder
    def _bock(log=print):
        raise RuntimeError("DB gesperrt")
    monkeypatch.setattr(melder, "pruefe_neue_wechsel", _bock)

    ergebnis = tageskette.tageskette(quelle="gui", log=lambda m: None)
    assert "dirigent:gui" in protokoll and "melder" in protokoll
    watcher = ergebnis["ergebnisse"][0]
    assert watcher["schritt"] == "wechsel_watcher"
    assert watcher["status"] == "fehler"
    assert ergebnis["status"] == "ok"


def test_meldung_callback_liefert_fortschritt(protokoll):
    meldungen: list[tuple[str, str]] = []

    def _meldung(rolle_key, text, stand):
        meldungen.append((rolle_key, stand))

    tageskette.tageskette(quelle="gui", log=lambda m: None, meldung=_meldung)
    # Je Rolle erst 'laeuft', dann ein Abschluss-Stand — in Kettenreihenfolge.
    stands = [s for _, s in meldungen]
    assert stands.count("laeuft") == len(tageskette.KETTEN_ROLLEN) + 1
    assert set(stands) <= {"laeuft", "ok"}
    assert stands[0] == "laeuft" and stands[1] == "ok"  # Watcher startet zuerst


def test_alle_rollen_gesperrt_oder_aus_ergibt_skipped(protokoll):
    settings = {f"agenten_{r}_aktiv": False
                for r in tageskette.KETTEN_ROLLEN}
    ergebnis = tageskette.tageskette(quelle="gui", log=lambda m: None,
                                     settings=settings)
    assert ergebnis["status"] == "skipped"
    assert not any(e.get("schritt") is None and e["status"] == "ok"
                   for e in ergebnis["ergebnisse"])


# ── UI: Button und Zusammenfassung auf der Agenten-Seite ────────────────────

def test_agenten_seite_zeigt_komplettlauf_button():
    at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                           default_timeout=60).run()
    assert not at.exception
    buttons = [b.label for b in at.button
               if "Agenten-Workflow jetzt ausführen" in (b.label or "")]
    assert buttons, "Komplettlauf-Button fehlt auf der Live-Ansicht"
    from mqlkiscanner.ui_design import help_topics
    assert "agenten_komplett_start" in help_topics()


_KETTEN_ERGEBNIS = {
    "status": "ok",
    "ergebnisse": [
        {"rolle": "melder", "schritt": "wechsel_watcher", "status": "ok",
         "info": "keine neuen Ampelwechsel"},
        {"rolle": "dirigent", "status": "ok",
         "info": "Regelbetrieb freigegeben"},
        {"rolle": "markt", "status": "skipped",
         "grund": "MT5-Terminal nicht aktiv"},
    ],
    "zusammenfassung": "Komplettlauf: 1 Rolle(n) ok",
}


def test_komplettlauf_flag_loest_ausfuehrung_aus(monkeypatch):
    """Gesetzter Start-Flag führt die Kette aus (Hook in rendere_agenten_baum)
    und verbraucht sich. Der Button-Klick selbst setzt nur diesen Flag —
    Klick+Rerun wird wie bei den übrigen Start-Buttons nicht durchgetestet
    (AppTest re-injiziert testseitig gesetzten Session-State über interne
    Reruns, das gäbe eine Endlosschleife; im Browser ist das Muster Standard)."""
    from mqlkiscanner.agenten import ui_tree
    aufrufe: list[bool] = []
    monkeypatch.setattr(ui_tree, "agenten_komplett_ausfuehren",
                        lambda **k: aufrufe.append(True))

    at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                           default_timeout=60).run()
    assert not at.exception
    assert aufrufe == []
    at.session_state["agenten_komplett_lauf"] = True
    at.run()
    assert aufrufe == [True]  # Flag wurde genau einmal verbraucht


def test_komplettlauf_flag_lichtet_die_ganze_kette_im_baum(monkeypatch):
    """Sobald der Komplettlauf-Flag steht, rendert der Baum die GANZE
    Tageskette als aktiv (wie beim Einzelstart-Button) — der Nutzer sieht
    sofort, dass gearbeitet wird, obwohl die Kette erst am Seitenende
    startet (Regression: Baum blieb im Ruhe-Zustand stehen)."""
    from mqlkiscanner.agenten import ui_tree
    aufgerufen: list[set] = []
    echt = ui_tree._rendere_topologie_html

    def _mitschneiden(aktive_rollen=None):
        aufgerufen.append(set(aktive_rollen or set()))
        return echt(aktive_rollen=aktive_rollen)

    monkeypatch.setattr(ui_tree, "_rendere_topologie_html", _mitschneiden)
    monkeypatch.setattr(ui_tree, "agenten_komplett_ausfuehren",
                        lambda **k: None)

    at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                           default_timeout=60).run()
    assert not at.exception
    assert aufgerufen[-1] == set()  # Ruhe-Zustand ohne Lauf
    at.session_state["agenten_komplett_lauf"] = True
    at.run()
    assert set(tageskette.KETTEN_ROLLEN) <= aufgerufen[-1]
    # Das Baum-HTML unterscheidet Arbeits- und Standby-Zustand wirklich.
    assert "ARBEITET GERADE" in echt(aktive_rollen={"dirigent"})
    assert "SYSTEM RUHIG" in echt(aktive_rollen=set())


def test_kette_ergebnis_wird_angezeigt_und_nur_einmal(monkeypatch):
    """Die Zusammenfassung erscheint aus dem Session-State (einmalig)."""
    at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                           default_timeout=60)
    at.session_state["_agenten_kette_ergebnis"] = dict(_KETTEN_ERGEBNIS)
    at.run()
    assert not at.exception
    texte = " ".join(c.value for c in at.caption)
    assert "Dirigent: Regelbetrieb freigegeben" in texte
    assert "Marktbeobachter" in texte  # Skip wird mit Name genannt
    assert "Wechsel-Watcher" in texte
    assert "_agenten_kette_ergebnis" not in at.session_state
    at.run()  # nächster Interaktions-Rerun: Anzeige ist weg
    texte = " ".join(c.value for c in at.caption)
    assert "Dirigent: Regelbetrieb freigegeben" not in texte


def test_komplettlauf_button_gesperrt_waehrend_eines_laufs():
    """Solange ein Agentenlauf aktiv ist (DB-'laeuft' oder gesetzter Start-
    Flag), ist der Button gesperrt — gepufferte Doppelklicks dürfen keine
    zweite Kette anstoßen (passierte am 23.09. live: Klick während des
    blockierten Skripts feuerte eine Sekunde nach Kettenende erneut)."""
    from mqlkiscanner.agenten import journal
    at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                           default_timeout=60).run()
    assert not at.exception
    assert not at.button(key="agenten_komplett_start").disabled
    lauf_id = journal.lauf_starten("betreuer", quelle="gui")
    try:
        at.run()
        assert at.button(key="agenten_komplett_start").disabled
        texte = " ".join(c.value for c in at.caption)
        assert "Agentenlauf ist aktiv" in texte
    finally:
        journal.lauf_abschliessen(lauf_id, "ok", "Testlauf beendet")
    at.run()
    assert not at.button(key="agenten_komplett_start").disabled
