# -*- coding: utf-8 -*-
"""Inhalt des Admin-Bereichs „Agenten" (aufgerufen aus app_pages/admin.py).

Kapselt die Rollenkarten, Budget-/Takt-Steuerung, Daemon Start/Stopp und
den Prompt-Editor der Rollen. Als eigenes Modul bleibt admin.py klein und
der Agenten-Tab unabhängig testbar (AppTest rendert die Seite inkl. Tab).

Eigene Mini-Helfer statt der admin.py-Internas (_finish/_save_group):
gleiche Semantik (Meldung + Rerun, neu laden beim Speichern), ohne die
Seiten-Interna zu teilen.
"""
from __future__ import annotations

import streamlit as st

from .. import config
from ..ui_design import action_button, info_button, section_header
from . import daemon, journal, rollen, rollen_prompts


def _geaendert(werte: dict, gespeichert: dict) -> bool:
    return any(wert != gespeichert.get(name) for name, wert in werte.items())


def _entwurfs_status(geaendert: bool) -> None:
    st.badge("Ungespeicherte Änderungen" if geaendert else "Gespeicherte Werte",
             color="orange" if geaendert else "green",
             icon=":material/edit:" if geaendert else ":material/check_circle:")


def _speichern(werte: dict, meldung: str) -> None:
    config.save_settings({**config.load_settings(), **werte})
    st.session_state["_admin_notice"] = meldung
    st.rerun()


def rendern(settings: dict) -> None:
    """Gesamter Tab-Inhalt — aufrufend ist `with agenten_tab:` in admin.py."""
    with st.container(border=True):
        section_header(
            "Agenten & LLMs — autonomer Betrieb",
            "Fünf LLM-Rollen übernehmen die Dauerbeobachtung (Bauplan doc/19). "
            f"Phase {rollen.AKTUELLE_PHASE} ist aktiv: Dirigent-Tageslauf mit "
            "lückenlosem Protokoll und Betreuer-Trade-Delta gegen die "
            "Dossiers; die weiteren Rollen werden in den Phasen C–E "
            "zugeschaltet.",
            help_key="settings_agenten",
        )
        st.info(
            "**Grundregeln des Agentenbetriebs:** Die Engine rechnet und bewertet — "
            "Agenten beobachten, ordnen ein und melden. Jeder LLM-Schritt wird mit "
            "vollständigem Prompt und vollständiger Antwort protokolliert "
            "(Seite „Agenten“). Standard-Modell je Rolle ist GLM-5.3.",
            icon=":material/tune:",
        )

        daemon_status = daemon.status()
        with st.container(horizontal=True, vertical_alignment="center", wrap=True):
            if daemon_status["aktiv"]:
                st.badge("Daemon läuft", color="green", icon=":material/play_arrow:")
                st.caption(f"PID {daemon_status['pid']} · Tick vor "
                           f"{daemon_status['alter_s']} s")
            else:
                st.badge("Daemon gestoppt", color="gray",
                         icon=":material/stop_circle:")
                if daemon_status["letzter_tick"]:
                    st.caption(f"letzter Tick: {daemon_status['letzter_tick']}")
            st.badge("Freigabe erteilt" if settings.get("agenten_enabled")
                     else "Freigabe aus",
                     color="green" if settings.get("agenten_enabled") else "orange",
                     icon=":material/lock:")

        start_spalte, stopp_spalte = st.columns(2)
        with start_spalte:
            if action_button("Agentenbetrieb starten", key="admin_agenten_start",
                             type="primary", help_key="settings_agenten_start",
                             icon=":material/play_arrow:"):
                ergebnis = daemon.starten(settings)
                st.session_state["_admin_notice"] = (
                    f"Agenten-Daemon gestartet (PID {ergebnis['pid']}) — Protokoll "
                    "auf der Seite „Agenten“." if ergebnis["gestartet"]
                    else f"Start nicht nötig: {ergebnis['grund']}")
                st.rerun()
        with stopp_spalte:
            if action_button("Agentenbetrieb stoppen", key="admin_agenten_stop",
                             help_key="settings_agenten_stop",
                             icon=":material/stop_circle:"):
                daemon.stoppen(settings)
                st.session_state["_admin_notice"] = (
                    "Stopp angefordert — der Daemon beendet sich beim nächsten "
                    "Tick (max. ~30 s).")
                st.rerun()

    with st.container(border=True):
        section_header(
            "Budget und Takt",
            "Token-Deckel des Agentenbetriebs; reguläre Scan-Läufe zählen auf "
            "ihr eigenes Lauf-Budget.",
            help_key="settings_agenten_budget")
        tokens_tag = journal.tokens_heute()
        tokens_monat = journal.tokens_monat()
        budget_tag = st.number_input(
            "Tagesbudget (Token)", min_value=10_000, max_value=50_000_000,
            value=int(settings.get("agenten_tagesbudget_tokens", 500_000)),
            step=10_000, key="admin_agenten_budget_tag")
        budget_monat = st.number_input(
            "Monatsbudget (Token)", min_value=100_000, max_value=500_000_000,
            value=int(settings.get("agenten_monatsbudget_tokens", 5_000_000)),
            step=100_000, key="admin_agenten_budget_monat")
        start_zeit = st.text_input(
            "Tägliche Startzeit (HH:MM)",
            value=str(settings.get("agenten_start_zeit", "06:30")),
            key="admin_agenten_start_zeit")
        dirigent_llm = st.toggle(
            "Dirigent darf LLM-Randentscheidungen treffen",
            value=bool(settings.get("agenten_dirigent_llm", True)),
            key="admin_agenten_dirigent_llm")
        st.progress(min(1.0, tokens_tag / max(1, int(budget_tag))),
                    text=f"Heute verbraucht: {tokens_tag:,} von "
                         f"{int(budget_tag):,} Token".replace(",", "."))
        st.caption(f"Monat verbraucht: {tokens_monat:,} von "
                   f"{int(budget_monat):,} Token".replace(",", "."))
        werte = {
            "agenten_tagesbudget_tokens": int(budget_tag),
            "agenten_monatsbudget_tokens": int(budget_monat),
            "agenten_start_zeit": start_zeit.strip() or "06:30",
            "agenten_dirigent_llm": dirigent_llm,
        }
        _entwurfs_status(_geaendert(werte, settings))
        if action_button("Budget und Takt speichern",
                         key="admin_agenten_budget_save",
                         help_key="settings_agenten_budget_save",
                         icon=":material/save:"):
            _speichern(werte, "Agenten-Budget und Takt gespeichert.")

    with st.container(border=True):
        section_header(
            "Marktdaten (MetaTrader)",
            "Kursdaten über das offizielle MetaTrader5-Paket — ausschließlich "
            "lesend, mit Start-Politik und automatischer Symbol-Beobachtungsliste.",
            help_key="settings_markt")
        from . import marktdata
        terminal_pfad = st.text_input(
            "Terminal-Pfad (austauschbar)",
            value=str(settings.get("markt_terminal_pfad")
                      or marktdata.DEFAULT_TERMINAL),
            key="admin_markt_terminal")
        start_erlauben = st.toggle(
            "Terminal selbst starten, falls es nicht läuft (Live-Terminal!)",
            value=bool(settings.get("markt_start_erlauben", False)),
            help="Standard AUS: Der Scanner startet dein Terminal nie "
                 "unerwünscht — läuft es nicht, wartet der Marktbeobachter "
                 "bis zum nächsten Intervall.",
            key="admin_markt_start")
        symbole_manuell = st.text_input(
            "Zusätzliche Symbole (Komma oder Leerzeichen)",
            value=str(settings.get("markt_symbole_manuell") or ""),
            placeholder="z. B. XAUUSD, EURUSD",
            key="admin_markt_symbole")
        lookback = st.number_input(
            "Kurs-Historie (Tage)", min_value=7, max_value=250,
            value=int(settings.get("markt_lookback_tage", 30)),
            key="admin_markt_lookback")
        markt_werte = {"markt_terminal_pfad": terminal_pfad.strip(),
                       "markt_start_erlauben": start_erlauben,
                       "markt_symbole_manuell": symbole_manuell.strip(),
                       "markt_lookback_tage": int(lookback)}
        _entwurfs_status(_geaendert(markt_werte, settings))
        test_spalte, speicher_spalte = st.columns(2)
        with test_spalte:
            if action_button("Verbindung testen", key="admin_markt_test",
                             help_key="settings_markt_test",
                             icon=":material/network_check:"):
                ergebnis = marktdata.verbindung_testen(
                    {**settings, **markt_werte})
                if ergebnis["ok"]:
                    st.success(ergebnis["grund"], icon=":material/check_circle:")
                else:
                    st.info(ergebnis["grund"], icon=":material/info:")
        with speicher_spalte:
            if action_button("Marktdaten speichern", key="admin_markt_save",
                             help_key="settings_markt_save",
                             icon=":material/save:"):
                _speichern(markt_werte, "Marktdaten-Einstellungen gespeichert.")

    with st.container(border=True):
        section_header(
            "Rollen konfigurieren",
            "Modell, Ausgabelimit und Aktivstatus je Rolle — GLM-5.3 ist Standard.",
            help_key="settings_agenten_rollen")
        rollen_werte: dict = {}
        for rolle in rollen.ROLLEN:
            geplant = not rollen.phase_aktiv(rolle, rollen.AKTUELLE_PHASE)
            with st.expander(f"{rolle.name} · {rolle.takt}",
                             expanded=rolle.key == "dirigent", icon=rolle.icon):
                st.caption(rolle.beschreibung)
                with st.container(horizontal=True, vertical_alignment="center",
                                  wrap=True):
                    if geplant:
                        st.badge(f"aktiv ab Phase {rolle.phase} (geplant)",
                                 color="orange", icon=":material/history:")
                    else:
                        st.badge(f"Phase {rolle.phase} — aktiv", color="green",
                                 icon=":material/check_circle:")
                aktiv = st.toggle(
                    "Rolle aktiv", key=f"agenten_{rolle.key}_aktiv_ui",
                    value=bool(settings.get(f"agenten_{rolle.key}_aktiv", True)))
                modell_aktuell = str(settings.get(
                    f"agenten_{rolle.key}_modell", rollen.STANDARD_MODELL))
                optionen = list(dict.fromkeys(
                    [modell_aktuell, *rollen.MODELL_AUSWAHL, "Anderes Modell …"]))
                auswahl = st.selectbox(
                    "Modell", optionen,
                    index=optionen.index(modell_aktuell),
                    key=f"agenten_{rolle.key}_modell_ui")
                if auswahl == "Anderes Modell …":
                    modell = st.text_input(
                        "Eigenes Modell (OpenAI-kompatibel)",
                        value="" if modell_aktuell in rollen.MODELL_AUSWAHL
                        else modell_aktuell,
                        key=f"agenten_{rolle.key}_modell_frei").strip()
                else:
                    modell = auswahl
                limit = st.number_input(
                    "Max. Tokens je Aufruf", min_value=512, max_value=131_072,
                    step=512,
                    value=int(settings.get(f"agenten_{rolle.key}_max_tokens",
                                           rolle.max_tokens)),
                    key=f"agenten_{rolle.key}_max_tokens_ui")
                rollen_werte[f"agenten_{rolle.key}_aktiv"] = aktiv
                rollen_werte[f"agenten_{rolle.key}_modell"] = (
                    modell or rollen.STANDARD_MODELL)
                rollen_werte[f"agenten_{rolle.key}_max_tokens"] = int(limit)
        _entwurfs_status(_geaendert(rollen_werte, settings))
        if action_button("Rollen speichern", key="admin_agenten_rollen_save",
                         help_key="settings_agenten_rollen_save",
                         icon=":material/save:"):
            _speichern(rollen_werte, "Agenten-Rollen gespeichert.")

    with st.container(border=True):
        section_header(
            "Rollen-Prompts",
            "Sechs Vorlagen für die fünf Rollen — einsehbar, editierbar und auf "
            "Standard zurücksetzbar.",
            help_key="settings_agenten_prompts")
        vorlage_key = st.segmented_control(
            "Vorlage auswählen", list(rollen_prompts.PROMPT_SCHLUESSEL),
            default="dirigent_planung", key="admin_agenten_prompt_choice")
        if vorlage_key:
            aktuell = rollen_prompts.lade_vorlage(vorlage_key)
            st.caption("Gespeichert: " + ("eigene Vorlage"
                        if rollen_prompts.vorlage_geaendert(vorlage_key)
                        else "Standardvorlage"))
            pflicht = ["{" + name + "}"
                       for name in rollen_prompts.PLATZHALTER[vorlage_key]]
            st.caption("Pflicht-Platzhalter: " + ", ".join(f"`{p}`" for p in pflicht))
            bearbeitet = st.text_area(
                "Vorlage bearbeiten", value=aktuell, height=360,
                key=f"agenten_prompt_{vorlage_key}")
            fehlen = [p for p in pflicht if p not in bearbeitet]
            if fehlen:
                st.warning("Fehlende Pflicht-Platzhalter: " + ", ".join(fehlen))
            speicher_spalte, reset_spalte = st.columns(2)
            with speicher_spalte:
                if action_button("Vorlage speichern",
                                 key="admin_agenten_prompt_save", type="primary",
                                 help_key="settings_agenten_prompt_save",
                                 icon=":material/save:"):
                    if not bearbeitet.strip() or fehlen:
                        st.error("Vorlage nicht gespeichert: Text und alle "
                                 "Pflicht-Platzhalter sind erforderlich.")
                    else:
                        rollen_prompts.speichere_vorlage(vorlage_key, bearbeitet)
                        st.session_state["_admin_notice"] = \
                            "Ausgewählte Agenten-Vorlage gespeichert."
                        st.rerun()
            with reset_spalte:
                if action_button("Standard wiederherstellen",
                                 key="admin_agenten_prompt_reset",
                                 help_key="settings_agenten_prompt_reset",
                                 icon=":material/restore:"):
                    rollen_prompts.setze_zurueck(vorlage_key)
                    st.session_state["_admin_notice"] = (
                        "Standardvorlage gespeichert und im Editor "
                        "wiederhergestellt.")
                    st.session_state[f"agenten_prompt_{vorlage_key}"] = \
                        rollen_prompts.DEFAULTS[vorlage_key]
                    st.rerun()
            with st.expander("Standardvorlage ansehen",
                             icon=":material/visibility:"):
                st.markdown(rollen_prompts.DEFAULTS[vorlage_key])
