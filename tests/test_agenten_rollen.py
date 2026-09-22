# -*- coding: utf-8 -*-
"""Rollen-Registry, Settings-Defaults und Rollen-Prompts (Phase A).

Nutzer-Vorgabe 22.09.2026: GLM-5.3 (nicht Flash) ist Standard-Modell für
ALLE Rollen — dieser Vertrag wird hier festgenagelt. Die Vorlagen folgen
dem prompt_fill-Muster: Zwei-Phasen-Füllung, unver­sorgte Platzhalter sind
ein klarer Fehler.
"""
import pytest

from mqlkiscanner import config
from mqlkiscanner.agenten import rollen, rollen_prompts


def test_fuenf_rollen_mit_eindeutigen_schluesseln():
    assert [r.key for r in rollen.ROLLEN] == [
        "dirigent", "markt", "betreuer", "chef", "melder"]
    assert len({r.key for r in rollen.ROLLEN}) == 5


def test_glm_53_ist_standardmodell_aller_rollen():
    """Nutzer-Vorgabe: glm-5.3 überall — kein Flash als Default."""
    settings = config.load_settings()
    for rolle in rollen.ROLLEN:
        assert settings[f"agenten_{rolle.key}_modell"] == "glm-5.3", rolle.key
    assert rollen.STANDARD_MODELL == "glm-5.3"


def test_rollen_defaults_in_settings():
    settings = config.load_settings()
    for name, wert in rollen.rollen_defaults().items():
        assert settings[name] == wert
    assert settings["agenten_dirigent_max_tokens"] == 8192
    assert settings["agenten_chef_max_tokens"] == 16384
    assert settings["agenten_enabled"] is False  # Freigabe aus bis Start


def test_phase_aktiv_reihenfolge():
    dirigent = rollen.ROLLEN_NACH_KEY["dirigent"]
    betreuer = rollen.ROLLEN_NACH_KEY["betreuer"]
    assert rollen.phase_aktiv(dirigent, "A")
    assert not rollen.phase_aktiv(betreuer, "A")
    assert rollen.phase_aktiv(betreuer, "B")


def test_icons_nutzen_sichere_doppelpunkt_form():
    """':material/name:' — die Kurzform crasht in Dialog-Pfaden (Gedächtnis)."""
    for rolle in rollen.ROLLEN:
        assert rolle.icon.startswith(":material/") and rolle.icon.endswith(":")


# ── Vorlagen ───────────────────────────────────────────────────────

def test_sechs_vorlagen_schluessel_und_platzhalter():
    assert set(rollen_prompts.PROMPT_SCHLUESSEL) == {
        "dirigent_planung", "markt_kontext", "profil_destillation",
        "betreuer_delta", "lagebericht", "meldung"}
    vorlage = rollen_prompts.lade_vorlage("dirigent_planung")
    assert "{lagestatus_json}" in vorlage and "{zeitplan_json}" in vorlage
    # Jeder in PLATZHALTER deklarierte Slot steht auch in der Default-Vorlage.
    for key, namen in rollen_prompts.PLATZHALTER.items():
        text = rollen_prompts.DEFAULTS[key]
        for name in namen:
            assert "{" + name + "}" in text, (key, name)


def test_lade_vorlage_legt_default_datei_an():
    text = rollen_prompts.lade_vorlage("meldung")
    assert text == rollen_prompts.DEFAULTS["meldung"]
    assert rollen_prompts.prompt_datei("meldung").exists()


def test_speichern_zuruecksetzen_geaendert():
    rollen_prompts.lade_vorlage("meldung")
    rollen_prompts.speichere_vorlage("meldung", "Eigene Fassung {typ}")
    assert rollen_prompts.vorlage_geaendert("meldung")
    rollen_prompts.setze_zurueck("meldung")
    assert not rollen_prompts.vorlage_geaendert("meldung")


def test_fuellung_ersetzt_alle_platzhalter():
    ergebnis = rollen_prompts.fuellung(
        rollen_prompts.DEFAULTS["meldung"],
        {"typ": "digest", "ereignisse_json": "x=1"})
    assert "{typ}" not in ergebnis and "{ereignisse_json}" not in ergebnis
    assert "digest" in ergebnis and "x=1" in ergebnis


def test_fuellung_inhalt_wird_nicht_mitgefuellt():
    """Zwei-Phasen-Füllung: ein {typ} im eingefügten Inhalt bleibt literal."""
    ergebnis = rollen_prompts.fuellung(
        "Kopf {typ}", {"typ": "Inhalt mit {typ} innen"})
    assert ergebnis == "Kopf Inhalt mit {typ} innen"


def test_fuellung_unversorgter_platzhalter_ist_fehler():
    with pytest.raises(ValueError, match="lagestatus_json"):
        rollen_prompts.fuellung(rollen_prompts.DEFAULTS["dirigent_planung"],
                                {"zeitplan_json": "{}"})
