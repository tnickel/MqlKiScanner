# -*- coding: utf-8 -*-
"""Einstellungen mit klaren Speicherbereichen und kontextbezogener Hilfe."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, secrets_store
from mqlkiscanner.llm import client as llm_client
from mqlkiscanner.llm import prompts as llm_prompts
from mqlkiscanner.mql5.session import Mql5Session
from mqlkiscanner.ui_design import (
    action_button, apply_theme, info_button, page_header, section_header,
)


def _changed(values: dict, saved: dict) -> bool:
    return any(value != saved.get(name) for name, value in values.items())


def _draft_status(changed: bool) -> None:
    st.badge(
        "Ungespeicherte Änderungen" if changed else "Gespeicherte Werte",
        color="orange" if changed else "green",
        icon=":material/edit:" if changed else ":material/check_circle:",
    )


def _finish(message: str, *, widget_updates: dict | None = None,
            clear_result: str | None = None) -> None:
    # Widget state must change before widgets are instantiated on the next run.
    st.session_state["_admin_widget_updates"] = widget_updates or {}
    st.session_state["_admin_notice"] = message
    if clear_result:
        st.session_state.pop(clear_result, None)
    st.rerun()


def _save_group(values: dict, message: str, *, clear_result: str | None = None) -> None:
    # Reload on save: never write an old copy of another group's settings.
    config.save_settings({**config.load_settings(), **values})
    _finish(message, clear_result=clear_result)


def _test_result(key: str, success: bool, message: str) -> None:
    st.session_state[key] = (success, message, datetime.now().strftime("%H:%M:%S"))


def _render_test_result(key: str) -> None:
    result = st.session_state.get(key)
    if result:
        success, message, timestamp = result
        (st.success if success else st.error)(f"{message} · Getestet um {timestamp}")


def _model_options(current: str, suggestions: list[str]) -> list[str]:
    return list(dict.fromkeys([current, *suggestions]))


apply_theme()
for _widget_key, _widget_value in st.session_state.pop("_admin_widget_updates", {}).items():
    st.session_state[_widget_key] = _widget_value

settings = config.load_settings()
secret_status = secrets_store.secret_status()

page_header(
    "SYSTEM / KONFIGURATION", "Einstellungen",
    "Zugänge verbinden, Prüfregeln festlegen und Analysen gezielt steuern.",
)
with st.container(horizontal=True, vertical_alignment="center"):
    st.caption("Jeder Bereich wird separat gespeichert. Gelbes i = ausführliche Erklärung.")
    info_button("settings_overview", key="admin_overview_help")

if _notice := st.session_state.pop("_admin_notice", None):
    st.success(_notice, icon=":material/check_circle:")

with st.container(horizontal=True):
    st.badge("MQL5-Zugang hinterlegt" if secret_status["mql5_user"] and secret_status["mql5_pass"]
             else "MQL5-Zugang unvollständig", color="green" if secret_status["mql5_user"]
             and secret_status["mql5_pass"] else "orange")
    st.badge("KI-Key vorhanden" if secret_status["glm_api_key"] else "KI-Key fehlt",
             color="green" if secret_status["glm_api_key"] else "orange")
    st.badge("Lokale Engine ohne KI-Key nutzbar", color="blue")

access_tab, models_tab, scan_tab, prompts_tab = st.tabs(
    ["Zugänge", "KI & Modelle", "Scan & Risiko", "Analysevorlagen"]
)

with access_tab:
    st.caption("1 · Zugang speichern → 2 · Gespeicherte Verbindung testen → 3 · Scan starten")
    mql_column, key_column = st.columns(2, gap="medium")
    with mql_column, st.container(border=True):
        section_header("MQL5-Zugang", "Für angemeldete Abrufe und Trade-Exporte.",
                       help_key="settings_mql5")
        st.caption("Login: " + ("hinterlegt" if secret_status["mql5_user"] else "fehlt")
                   + " · Passwort: " + ("hinterlegt" if secret_status["mql5_pass"] else "fehlt"))
        new_user = st.text_input("Benutzername oder E-Mail", key="admin_mql5_user",
                                 placeholder="Leer lassen = unverändert")
        new_pass = st.text_input("Passwort", type="password", key="admin_mql5_pass",
                                 placeholder="Leer lassen = unverändert")
        _draft_status(bool(new_user.strip() or new_pass))
        if action_button("MQL5-Zugang speichern", key="admin_mql5_save", type="primary",
                         help_key="settings_mql5", icon=":material/save:"):
            fields = {}
            if new_user.strip():
                fields["mql5_user"] = new_user.strip()
            if new_pass:
                fields["mql5_pass"] = new_pass
            if fields:
                secrets_store.save_secrets(**fields)
                _finish("MQL5-Zugang lokal gespeichert. Bitte die gespeicherte Anmeldung testen.",
                        widget_updates={"admin_mql5_user": "", "admin_mql5_pass": ""},
                        clear_result="_admin_mql5_result")
            else:
                st.info("Keine neuen Zugangsdaten eingegeben; vorhandene Werte bleiben erhalten.")
        if action_button("Gespeicherten Login testen", key="admin_mql5_test",
                         help_key="settings_mql5_test", icon=":material/network_check:"):
            sess = Mql5Session(config.load_settings())
            if not sess.has_credentials:
                _test_result("_admin_mql5_result", False, "Benutzername und Passwort zuerst speichern.")
            else:
                from mqlkiscanner.mql5.browser_session import ensure_mql5_cookies
                with st.status("MQL5-Anmeldung wird geprüft …", expanded=True) as status:
                    st.write("Gespeicherte Session-Cookies prüfen; bei Bedarf öffnet sich "
                             "kurz ein Chrome-Fenster für die Anmeldung.")
                    try:
                        ok = ensure_mql5_cookies(config.load_settings(), sess,
                                                 log=lambda m: st.write(m))
                        _test_result("_admin_mql5_result", ok,
                                     "Anmeldung erfolgreich — Trade-Exporte verfügbar. "
                                     "Session bleibt als lokale Cookie-Datei gespeichert."
                                     if ok else "Anmeldung fehlgeschlagen. Gespeicherten Zugang prüfen.")
                        status.update(label="Login-Test abgeschlossen" if ok else "Login-Test fehlgeschlagen",
                                      state="complete" if ok else "error", expanded=False)
                    except Exception as exc:
                        _test_result("_admin_mql5_result", False,
                                     f"Anmeldung nicht abgeschlossen: {exc}")
                        status.update(label="Login-Test fehlgeschlagen", state="error", expanded=False)
        _render_test_result("_admin_mql5_result")

    with key_column, st.container(border=True):
        section_header("KI-Zugang", "API-Key für die ergänzenden KI-Analysen.",
                       help_key="settings_key")
        st.caption("Wirksamer Key: " + ("vorhanden" if secret_status["glm_api_key"] else "nicht hinterlegt"))
        new_key = st.text_input("Neuen API-Key hinterlegen", type="password",
                                key="admin_key_input", placeholder="Leer lassen = unverändert")
        _draft_status(bool(new_key.strip()))
        if action_button("Key lokal speichern", key="admin_key_save", type="primary",
                         help_key="settings_key", icon=":material/save:"):
            if new_key.strip():
                secrets_store.save_secrets(glm_api_key=new_key.strip())
                _finish("API-Key lokal gespeichert. Verbindung unter „KI & Modelle“ testen.",
                        widget_updates={"admin_key_input": ""}, clear_result="_admin_llm_result")
            else:
                st.info("Kein neuer Key eingegeben; der vorhandene Zugang bleibt erhalten.")
        if action_button("Lokalen Key entfernen", key="admin_key_remove",
                         help_key="settings_key_remove", icon=":material/delete:"):
            secrets_store.save_secrets(glm_api_key="")
            remains = bool(secrets_store.get_secret("glm_api_key"))
            _finish("Lokaler Key entfernt. Ein Key aus Umgebung oder .env ist weiterhin aktiv."
                    if remains else "Lokaler Key entfernt.",
                    widget_updates={"admin_key_input": ""}, clear_result="_admin_llm_result")
        st.caption("Der Verbindungstest steht unter „KI & Modelle“ und prüft den dort gespeicherten Endpunkt.")

    with st.container(border=True):
        st.markdown("**Welche Zugangsdaten verwendet das System?**")
        st.caption("Prozess-Umgebung → .env → lokale Konfiguration. Ein extern gesetzter Wert hat Vorrang. "
                   "Diese Seite schreibt nur die lokale Datei; sie ist aus Git ausgeschlossen und nicht verschlüsselt.")

with models_tab:
    with st.container(border=True):
        section_header("Modelle & Verbindung", "Zwei Modellrollen für Risikoprofil, Trade-Analyse und Gesamtbericht.",
                       help_key="settings_models")
        first, second = st.columns(2)
        configured_model1 = str(settings.get("model_stufe1") or config.MODEL_STUFE1)
        configured_model2 = str(settings.get("model_stufe2") or config.MODEL_STUFE2)
        m1 = first.selectbox("Stufe 1 · Risikoprofil",
                             _model_options(configured_model1, ["glm-5.3-flash", "glm-4.5-flash", "glm-4.5-air"]),
                             key="admin_model1", accept_new_options=True)
        m2 = second.selectbox("Stufe 2 · Trade-Analyse & Gesamtbericht",
                              _model_options(configured_model2, ["glm-5.3", "glm-5.2", "glm-5.1", "glm-4.5"]),
                              key="admin_model2", accept_new_options=True)
        st.caption("Eigene Modellnamen sind möglich. Verfügbarkeit hängt von Anbieter und Tarif ab.")
        section_header("API-Endpunkt", "Passend zum verwendeten Zugang und Anbieter-Kontingent.",
                       help_key="settings_endpoint")
        saved_base = settings.get("glm_base_url") or config.GLM_BASE_URL
        choices = ["GLM Coding Plan (Abo)", "Standard-API (Guthaben)", "Eigene URL"]
        choice_index = 0 if saved_base == config.GLM_BASE_URL_CODING else (
            1 if saved_base == config.GLM_BASE_URL_API else 2)
        url_choice = st.selectbox("Verbindungstyp", choices, index=choice_index, key="admin_baseurl_choice")
        custom_url = st.text_input("Eigene Base-URL", value=saved_base, key="admin_baseurl_custom",
                                   disabled=url_choice != "Eigene URL")
        new_base = (config.GLM_BASE_URL_CODING if url_choice == choices[0] else
                    config.GLM_BASE_URL_API if url_choice == choices[1] else custom_url.strip().rstrip("/"))
        section_header("Verbrauchsrahmen", "Token-Zähler je KI-Lauf; kein Euro-Limit.",
                       help_key="settings_budget")
        budget = st.number_input("Token-Budget je Lauf", min_value=1,
                                  value=int(settings.get("llm_max_total_tokens", 5_000_000)),
                                  step=100_000, key="admin_budget")
        model_values = {"model_stufe1": str(m1 or "").strip(), "model_stufe2": str(m2 or "").strip(),
                        "llm_max_total_tokens": int(budget), "glm_base_url": new_base}
        models_dirty = _changed(model_values, settings)
        _draft_status(models_dirty)
        if action_button("Modelle & Verbindung speichern", key="admin_models_save", type="primary",
                         help_key="settings_models", icon=":material/save:"):
            try:
                parsed = urlsplit(new_base)
                valid_base = (parsed.scheme in {"https", "http"} and bool(parsed.netloc)
                              and not parsed.username and not parsed.password)
            except ValueError:
                valid_base = False
            if not m1 or not m2 or not str(m1).strip() or not str(m2).strip():
                st.error("Beide Modellnamen müssen gesetzt sein.")
            elif not valid_base:
                st.error("Eine vollständige HTTP(S)-Base-URL ohne Zugangsdaten verwenden.")
            elif new_base.endswith("/chat/completions"):
                st.error("Nur die Base-URL eintragen; /chat/completions ergänzt der Client automatisch.")
            elif budget < 1:
                st.error("Das Token-Budget muss positiv sein.")
            else:
                _save_group(model_values, "Modelle, Endpunkt und Budget gespeichert.", clear_result="_admin_llm_result")

    with st.container(border=True):
        section_header("Verbindung prüfen", "Kleine echte Testanfrage mit dem gespeicherten Stufe-1-Modell.",
                       help_key="settings_llm_test")
        st.caption(f"Gespeichertes Testmodell: {configured_model1}. Der Test verbraucht Tokens. Stufe 2 wird nicht geprüft.")
        if models_dirty or new_key.strip():
            st.warning("Es gibt ungespeicherte Änderungen. Der Test verwendet weiterhin die gespeicherten Werte.")
        if action_button("Gespeicherte KI-Verbindung testen", key="admin_llm_test",
                         help_key="settings_llm_test", icon=":material/network_check:"):
            saved = config.load_settings()
            if not secrets_store.get_secret("glm_api_key"):
                _test_result("_admin_llm_result", False, "Zuerst unter „Zugänge“ einen API-Key hinterlegen.")
            else:
                with st.status("KI-Verbindung wird geprüft …", expanded=True) as status:
                    st.write("Gespeicherten Zugang und Stufe-1-Modell geladen. Warte auf Antwort des Anbieters.")
                    client = llm_client.GlmClient(
                        model_stufe1=saved["model_stufe1"], model_stufe2=saved["model_stufe2"],
                        max_total_tokens=int(saved["llm_max_total_tokens"]),
                        base_url=saved.get("glm_base_url") or config.GLM_BASE_URL,
                    )
                    try:
                        out = client.test_connection()
                        _test_result("_admin_llm_result", True,
                                     f"Stufe 1 antwortet erfolgreich · {out['usage']['total_tokens']} Tokens verbraucht.")
                        status.update(label="KI-Verbindung bestätigt", state="complete", expanded=False)
                    except llm_client.LlmNoBalanceError:
                        _test_result("_admin_llm_result", False,
                                     "Kein passendes Kontingent verfügbar. API-Endpunkt und Anbieter-Kontingent prüfen.")
                        status.update(label="Kontingentprüfung fehlgeschlagen", state="error", expanded=False)
                    except Exception as exc:
                        _test_result("_admin_llm_result", False,
                                     f"KI-Test fehlgeschlagen ({type(exc).__name__}). Zugang, Endpunkt und Modell prüfen.")
                        status.update(label="KI-Test fehlgeschlagen", state="error", expanded=False)
        _render_test_result("_admin_llm_result")

with scan_tab:
    filters_column, risk_column = st.columns(2, gap="medium")
    with filters_column, st.container(border=True):
        section_header("Scanprofil", "Ausgangswerte für neue Scans. Größerer Umfang benötigt mehr Zeit.",
                       help_key="settings_filters")
        pages = st.number_input("Listen-Seiten je MT4 / MT5", 1, 10, value=int(settings["listen_seiten"]), key="admin_pages")
        top_n = st.number_input("Export-Kandidaten", min_value=1, value=int(settings["top_n_export"]), key="admin_topn")
        weeks = st.number_input("Mindesthistorie in Wochen", min_value=0, value=int(settings["min_wochen"]), key="admin_weeks")
        subscribers = st.number_input("Mindest-Abonnenten", min_value=0, value=int(settings["min_abonnenten"]), key="admin_subscribers")
        filter_values = {"listen_seiten": int(pages), "top_n_export": int(top_n),
                         "min_wochen": int(weeks), "min_abonnenten": int(subscribers)}
        _draft_status(_changed(filter_values, settings))
        if action_button("Scanprofil speichern", key="admin_filters_save", type="primary",
                         help_key="settings_filters", icon=":material/save:"):
            if not 1 <= pages <= 10 or top_n < 1 or weeks < 0 or subscribers < 0:
                st.error("Scanumfang und Filter müssen innerhalb der angegebenen Grenzen liegen.")
            else:
                _save_group(filter_values, "Scanprofil als Vorgabe für folgende Läufe gespeichert.")

    with risk_column, st.container(border=True):
        section_header("Risikokriterien", "Risiko vor Ertrag. Die Drawdown-Grenze lässt sich nur verschärfen.",
                       help_key="settings_risk")
        old_dd = float(settings["schranke_eq_dd_pct"])
        old_return = float(settings["min_ertrag_pct_monat"])
        if old_dd > 30 or old_return < 5:
            st.warning("Die gespeicherten Grenzen weichen von den Projektvorgaben ab. "
                       "Die Werte unten korrigieren dies erst nach dem Speichern.")
        max_dd = st.number_input("Maximaler Equity-Drawdown (%)", 0.1, 30.0,
                                 value=max(0.1, min(30.0, old_dd)), step=1.0, key="admin_max_dd")
        min_return = st.number_input("Ertragsschwelle pro Monat (%)", min_value=5.0,
                                     value=max(5.0, old_return), step=0.1, key="admin_min_return")
        st.caption("Projektvorgabe: höchstens 30 % Drawdown und mehr als 5 % pro Monat.")
        st.info("Die Engine akzeptiert aktuell Ertrag ≥ eingestellter Schwelle. "
                "Bei 5,0 % gilt daher auch exakt 5,0 % als ausreichend.", icon=":material/info:")
        risk_values = {"schranke_eq_dd_pct": float(max_dd), "min_ertrag_pct_monat": float(min_return)}
        _draft_status(_changed(risk_values, settings))
        if action_button("Risikokriterien speichern", key="admin_risk_save", type="primary",
                         help_key="settings_risk", icon=":material/save:"):
            if not 0 < max_dd <= 30 or not min_return >= 5:
                st.error("Zulässig: Drawdown über 0 bis höchstens 30 %, Ertragsschwelle mindestens 5 %.")
            else:
                _save_group(risk_values, "Risikokriterien für folgende Läufe gespeichert.")
        st.caption("Kein positives Urteil allein anhand dieser Grenzen: Stop-Nachweis und Forensik bleiben erforderlich.")

    with st.container(border=True):
        section_header("Abrufpausen & Drosselung", "Wartezeiten gehören zum Ablauf und schonen die Datenquelle.",
                       help_key="settings_rate")
        interval_column, pause_column, backoff_column = st.columns(3)
        interval = interval_column.number_input("Mindestabstand je Request (s)", 0.5, 30.0,
                                                 value=float(settings["rate_min_interval_s"]), step=0.5, key="admin_interval")
        pause = pause_column.number_input("Pause zwischen Signalen (s)", 0.0, 120.0,
                                           value=float(settings["rate_pause_zwischen_signalen_s"]), step=1.0, key="admin_pause")
        backoff = backoff_column.number_input("Wartezeit bei HTTP 429 / 503 (s)", 10.0, 300.0,
                                               value=float(settings["rate_backoff_429_s"]), step=5.0, key="admin_backoff")
        rate_values = {"rate_min_interval_s": float(interval), "rate_pause_zwischen_signalen_s": float(pause),
                       "rate_backoff_429_s": float(backoff)}
        _draft_status(_changed(rate_values, settings))
        if action_button("Abrufpausen speichern", key="admin_rate_save", type="primary",
                         help_key="settings_rate", icon=":material/save:"):
            if not 0.5 <= interval <= 30 or not 0 <= pause <= 120 or not 10 <= backoff <= 300:
                st.error("Die Wartezeiten müssen innerhalb der angegebenen Grenzen liegen.")
            else:
                _save_group(rate_values, "Abrufpausen für folgende Läufe gespeichert.")

with prompts_tab:
    with st.container(border=True):
        section_header("Analysevorlagen", "Vier Texte, ein nachvollziehbarer Weg vom Befund zum Portfolio-Vorschlag.",
                       help_key="settings_prompts")
        labels = {"trade_analyse": "1 · Trade-Analyse", "risiko_analyse": "2 · Risikoprofil",
                  "gesamtbericht": "3 · Gesamtbericht", "portfolio": "4 · Portfolio-Vorschlag"}
        placeholders = {
            "trade_analyse": ("kandidat_json", "trades_json"),
            "risiko_analyse": ("kandidat_json", "forensik_json", "kriterien"),
            "gesamtbericht": ("kandidat_json", "forensik_json", "trade_analyse", "risiko_analyse", "kriterien"),
            "portfolio": ("kandidaten_json", "kriterien"),
        }
        prompt_key = st.segmented_control("Vorlage auswählen", list(llm_prompts.PROMPT_FILES),
                                          format_func=lambda key: labels.get(key, key), default="trade_analyse",
                                          key="admin_prompt_choice")
        if prompt_key:
            current = llm_prompts.load_prompt(prompt_key)
            modified = current.strip() != llm_prompts.DEFAULTS[prompt_key].strip()
            model = settings["model_stufe1"] if prompt_key == "risiko_analyse" else settings["model_stufe2"]
            st.caption(f"Verwendetes Modell: {model} · Gespeichert: "
                       + ("eigene Vorlage" if modified else "Standardvorlage"))
            required = ["{" + name + "}" for name in placeholders[prompt_key]]
            st.caption("Pflicht-Platzhalter: " + ", ".join(f"`{item}`" for item in required))
            edited = st.text_area("Vorlage bearbeiten", value=current, height=420,
                                  key=f"prompt_{prompt_key}", persist_state="page")
            _draft_status(edited != current)
            missing = [item for item in required if item not in edited]
            if missing:
                st.warning("Fehlende Pflicht-Platzhalter: " + ", ".join(missing))
            save_column, reset_column = st.columns(2)
            with save_column:
                if action_button("Vorlage speichern", key="admin_prompt_save", type="primary",
                                 help_key="settings_prompt_save", icon=":material/save:"):
                    if not edited.strip() or missing:
                        st.error("Vorlage nicht gespeichert: Text und alle Pflicht-Platzhalter sind erforderlich.")
                    else:
                        llm_prompts.save_prompt(prompt_key, edited)
                        _finish("Ausgewählte Analysevorlage gespeichert.")
            with reset_column:
                if action_button("Standard wiederherstellen", key="admin_prompt_reset",
                                 help_key="settings_prompt_reset", icon=":material/restore:"):
                    llm_prompts.reset_prompt(prompt_key)
                    _finish("Standardvorlage gespeichert und im Editor wiederhergestellt.",
                            widget_updates={f"prompt_{prompt_key}": llm_prompts.DEFAULTS[prompt_key]})
            with st.container(horizontal=True, vertical_alignment="center"):
                st.caption("Vorschau ansehen, bevor du eigene Änderungen durch den Standard ersetzt.")
                info_button("settings_prompt_preview", key="admin_prompt_preview_help")
            with st.expander("Standardvorlage ansehen", icon=":material/visibility:"):
                st.markdown(llm_prompts.DEFAULTS[prompt_key])
