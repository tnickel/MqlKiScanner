# -*- coding: utf-8 -*-
"""Einstellungen mit klaren Speicherbereichen und kontextbezogener Hilfe."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import (config, db, secrets_store, downloader_client, downloader_sync,
                          tradeserver_client, tradeserver_sync)
from mqlkiscanner.llm import client as llm_client
from mqlkiscanner.llm import prompts as llm_prompts
from mqlkiscanner.mql5.session import Mql5Session
from mqlkiscanner.ui_design import (
    action_button, apply_theme, info_button, page_header, section_header,
)


def _changed(values: dict, saved: dict) -> bool:
    return any(value != saved.get(name) for name, value in values.items())


def _draft_status(
    changed: bool,
    *,
    clean_label: str = "Gespeicherte Werte",
    clean_color: str = "green",
) -> None:
    st.badge(
        "Ungespeicherte Änderungen" if changed else clean_label,
        color="orange" if changed else clean_color,
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

admin_hero_banner = Path(__file__).resolve().parents[1] / "assets" / "hero_settings_banner.jpg"
page_header(
    "SYSTEM / KONFIGURATION", "Einstellungen",
    "Zugänge verbinden, Prüfregeln festlegen und Analysen gezielt steuern.",
    image_path=str(admin_hero_banner) if admin_hero_banner.exists() else None,
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
    dl_start = downloader_sync.verbindungs_status()
    st.badge("MqlDownloader verbunden" if dl_start["ok"]
             else ("MqlDownloader nicht konfiguriert" if not dl_start["konfiguriert"]
                   else "MqlDownloader nicht erreichbar"),
             color="green" if dl_start["ok"]
             else ("gray" if not dl_start["konfiguriert"] else "red"))
    ts_start = tradeserver_sync.verbindungs_status()
    st.badge("Tradeserver verbunden" if ts_start["ok"]
             else ("Tradeserver nicht konfiguriert" if not ts_start["konfiguriert"]
                   else "Tradeserver nicht erreichbar"),
             color="green" if ts_start["ok"]
             else ("gray" if not ts_start["konfiguriert"] else "red"))
    st.badge("Lokale Engine ohne KI-Key nutzbar", color="blue")

access_tab, models_tab, downloader_tab, tradeserver_tab, rest_api_tab, scan_tab, prompts_tab = st.tabs(
    ["Zugänge", "KI & Modelle", "MqlDownloader", "Tradeserver", "REST-API",
     "Scan & Risiko", "Analysevorlagen"]
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
        mql_complete = bool(secret_status["mql5_user"] and secret_status["mql5_pass"])
        mql_partial = bool(secret_status["mql5_user"] or secret_status["mql5_pass"])
        _draft_status(
            bool(new_user.strip() or new_pass),
            clean_label=(
                "Zugangsdaten hinterlegt" if mql_complete
                else "Zugangsdaten unvollständig" if mql_partial
                else "Keine Zugangsdaten hinterlegt"
            ),
            clean_color="green" if mql_complete else "orange" if mql_partial else "gray",
        )
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
        _draft_status(
            bool(new_key.strip()),
            clean_label="KI-Key hinterlegt" if secret_status["glm_api_key"] else "Kein KI-Key hinterlegt",
            clean_color="green" if secret_status["glm_api_key"] else "gray",
        )
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

with downloader_tab:
    with st.container(border=True):
        section_header("MqlDownloader REST-Interface",
                       "Adresse und Zugang des lokalen Downloaders — Quelle der "
                       "Abonnenten-Verläufe und Testreport-PDFs je Signal-ID.",
                       help_key="settings_downloader")
        saved_downloader_base = str(settings.get("downloader_base_url") or "")
        downloader_base = st.text_input(
            "Base-URL", value=saved_downloader_base,
            placeholder=config.DOWNLOADER_DEFAULT_BASE, key="admin_downloader_base")
        st.caption(f"Standard: {config.DOWNLOADER_DEFAULT_BASE} · „/api/v1“ wird ergänzt, "
                   "wenn nur Host:Port eingetragen ist.")
        downloader_token = st.text_input(
            "API-Token", type="password", key="admin_downloader_token",
            placeholder="Leer lassen = unverändert")
        token_active = secrets_store.get_secret("downloader_token")
        st.caption("Token: " + ("hinterlegt" if token_active
                                else "nicht hinterlegt (Downloader ohne Token-Schutz)"))
        downloader_dirty = (downloader_base.strip() != saved_downloader_base
                            or bool(downloader_token.strip()))
        _draft_status(downloader_dirty,
                      clean_label="Verbindung konfiguriert" if saved_downloader_base
                      else "Nicht konfiguriert",
                      clean_color="green" if saved_downloader_base else "gray")
        save_column, token_column = st.columns(2)
        with save_column:
            if action_button("MqlDownloader-Verbindung speichern", key="admin_downloader_save",
                             type="primary", help_key="settings_downloader",
                             icon=":material/save:"):
                try:
                    normalized = downloader_client.normalize_base_url(downloader_base)
                except (downloader_client.DownloaderError, ValueError):
                    normalized = ""
                if downloader_base.strip() and not normalized:
                    st.error("Eine vollständige HTTP(S)-Base-URL verwenden, "
                             "z. B. http://rechner:8089/api/v1")
                else:
                    if downloader_token.strip():
                        secrets_store.save_secrets(downloader_token=downloader_token.strip())
                    # Reload on save: nie eine alte Kopie anderer Einstellungen schreiben.
                    config.save_settings({**config.load_settings(),
                                          "downloader_base_url": normalized})
                    downloader_sync.status_cache_leeren()
                    _finish("MqlDownloader-Verbindung gespeichert. "
                            "Bitte die gespeicherte Verbindung testen.",
                            widget_updates=({"admin_downloader_token": ""}
                                            if downloader_token.strip() else None),
                            clear_result="_admin_downloader_result")
        with token_column:
            if action_button("Token entfernen", key="admin_downloader_token_remove",
                             help_key="settings_downloader", icon=":material/delete:",
                             disabled=not token_active):
                secrets_store.save_secrets(downloader_token="")
                downloader_sync.status_cache_leeren()
                _finish("Token entfernt. Ist im Downloader keiner gesetzt, bleibt die "
                        "Verbindung voll nutzbar.",
                        widget_updates={"admin_downloader_token": ""},
                        clear_result="_admin_downloader_result")

    with st.container(border=True):
        section_header("Verbindung prüfen", "Health-Check gegen den gespeicherten Downloader.",
                       help_key="settings_downloader_test")
        if downloader_dirty:
            st.warning("Es gibt ungespeicherte Änderungen. Der Test verwendet "
                       "weiterhin die gespeicherten Werte.")
        if action_button("Gespeicherte Downloader-Verbindung testen", key="admin_downloader_test",
                         help_key="settings_downloader_test", icon=":material/network_check:"):
            saved = config.load_settings()
            if not str(saved.get("downloader_base_url") or "").strip():
                _test_result("_admin_downloader_result", False, "Zuerst eine Base-URL speichern.")
            else:
                with st.status("MqlDownloader wird geprüft …", expanded=True) as status:
                    st.write(f"Health-Check gegen {saved['downloader_base_url']}/health. "
                             "Der Test liest nur und verbraucht keine MQL5-Ressourcen.")
                    try:
                        info = downloader_client.client_from_settings(saved).health()
                        if str(info.get("status", "")).lower() != "ok":
                            raise downloader_client.DownloaderError(
                                f"Unerwarteter Status: {info.get('status')!r}")
                        needed = bool(info.get("tokenRequired"))
                        token_there = bool(secrets_store.get_secret("downloader_token"))
                        _test_result(
                            "_admin_downloader_result", True,
                            f"Downloader erreichbar · {info.get('providers', '?')} Provider · "
                            f"API-Version {info.get('apiVersion', '?')} · "
                            + ("Token erforderlich und hinterlegt" if needed and token_there
                               else "Token erforderlich, aber keiner hinterlegt!" if needed
                               else "kein Token erforderlich"))
                        status.update(label="Downloader-Verbindung bestätigt",
                                      state="complete", expanded=False)
                    except downloader_client.DownloaderNotConfigured:
                        _test_result("_admin_downloader_result", False,
                                     "Zuerst eine Base-URL speichern.")
                        status.update(label="Verbindungstest fehlgeschlagen",
                                      state="error", expanded=False)
                    except downloader_client.DownloaderAuthError as exc:
                        _test_result("_admin_downloader_result", False, str(exc))
                        status.update(label="Token abgelehnt", state="error", expanded=False)
                    except downloader_client.DownloaderConnectionError as exc:
                        _test_result("_admin_downloader_result", False, str(exc))
                        status.update(label="Downloader nicht erreichbar", state="error", expanded=False)
                    except Exception as exc:
                        _test_result("_admin_downloader_result", False,
                                     f"Verbindungstest fehlgeschlagen ({type(exc).__name__}). "
                                     "Base-URL und Downloader prüfen.")
                        status.update(label="Verbindungstest fehlgeschlagen",
                                      state="error", expanded=False)
        _render_test_result("_admin_downloader_result")

with tradeserver_tab:
    with st.container(border=True):
        section_header("MqlTradeMonitor-Tradeserver",
                       "Adresse und API-Key des Tradeservers — Ziel des Einmal-Syncs "
                       "für Signal-Tabelle und PDF-Dokumente (Kachel „MqlKiScanner“).",
                       help_key="settings_tradeserver")
        saved_ts_base = str(settings.get("tradeserver_base_url") or "")
        ts_base = st.text_input(
            "Base-URL", value=saved_ts_base,
            placeholder=config.TRADESERVER_DEFAULT_BASE, key="admin_tradeserver_base")
        st.caption(f"Beispiel: {config.TRADESERVER_DEFAULT_BASE} — feste IP/Port des "
                   "Tradeservers; „/api/kiscanner“ hängt der Sync selbst an.")
        ts_key = st.text_input(
            "API-Key", type="password", key="admin_tradeserver_key",
            placeholder="Leer lassen = unverändert")
        ts_key_active = secrets_store.get_secret("tradeserver_api_key")
        st.caption("API-Key: " + ("hinterlegt" if ts_key_active
                                  else "nicht hinterlegt — der Tradeserver lehnt "
                                       "jeden Sync ohne Key ab"))
        ts_dirty = (ts_base.strip() != saved_ts_base or bool(ts_key.strip()))
        _draft_status(ts_dirty,
                      clean_label="Verbindung konfiguriert" if saved_ts_base
                      else "Nicht konfiguriert",
                      clean_color="green" if saved_ts_base else "gray")
        ts_save_column, ts_key_column = st.columns(2)
        with ts_save_column:
            if action_button("Tradeserver-Verbindung speichern", key="admin_tradeserver_save",
                             type="primary", help_key="settings_tradeserver",
                             icon=":material/save:"):
                try:
                    ts_normalized = tradeserver_client.normalize_base_url(ts_base)
                except tradeserver_client.TradeserverError:
                    ts_normalized = ""
                if ts_base.strip() and not ts_normalized:
                    st.error("Eine vollständige HTTP(S)-Base-URL verwenden, "
                             "z. B. http://192.0.2.10:8080")
                else:
                    if ts_key.strip():
                        secrets_store.save_secrets(tradeserver_api_key=ts_key.strip())
                    # Reload on save: nie eine alte Kopie anderer Einstellungen schreiben.
                    config.save_settings({**config.load_settings(),
                                          "tradeserver_base_url": ts_normalized})
                    tradeserver_sync.status_cache_leeren()
                    _finish("Tradeserver-Verbindung gespeichert. "
                            "Bitte die gespeicherte Verbindung testen.",
                            widget_updates=({"admin_tradeserver_key": ""}
                                            if ts_key.strip() else None),
                            clear_result="_admin_tradeserver_result")
        with ts_key_column:
            if action_button("API-Key entfernen", key="admin_tradeserver_key_remove",
                             help_key="settings_tradeserver", icon=":material/delete:",
                             disabled=not ts_key_active):
                secrets_store.save_secrets(tradeserver_api_key="")
                tradeserver_sync.status_cache_leeren()
                _finish("API-Key entfernt. Ohne Key nimmt der Tradeserver "
                        "keine Daten mehr an.",
                        widget_updates={"admin_tradeserver_key": ""},
                        clear_result="_admin_tradeserver_result")

    with st.container(border=True):
        section_header("Verbindung prüfen", "Ping gegen den gespeicherten Tradeserver "
                       "(prüft Erreichbarkeit und API-Key, überträgt keine Daten).",
                       help_key="settings_tradeserver_test")
        if ts_dirty:
            st.warning("Es gibt ungespeicherte Änderungen. Der Test verwendet "
                       "weiterhin die gespeicherten Werte.")
        if action_button("Gespeicherte Tradeserver-Verbindung testen",
                         key="admin_tradeserver_test",
                         help_key="settings_tradeserver_test", icon=":material/network_check:"):
            saved = config.load_settings()
            if not str(saved.get("tradeserver_base_url") or "").strip():
                _test_result("_admin_tradeserver_result", False,
                             "Zuerst eine Base-URL speichern.")
            else:
                with st.status("Tradeserver wird geprüft …", expanded=True) as status:
                    st.write(f"Ping gegen {saved['tradeserver_base_url']}/api/kiscanner/ping. "
                             "Der Test liest nur und startet keinen Sync.")
                    try:
                        info = tradeserver_client.client_from_settings(saved).ping()
                        if str(info.get("status", "")).lower() != "ok":
                            raise tradeserver_client.TradeserverError(
                                f"Unerwarteter Status: {info.get('status')!r}")
                        _test_result(
                            "_admin_tradeserver_result", True,
                            f"Tradeserver erreichbar · Dienst {info.get('service', '?')} · "
                            f"API {info.get('kiscannerApi', '?')} · API-Key akzeptiert")
                        status.update(label="Tradeserver-Verbindung bestätigt",
                                      state="complete", expanded=False)
                    except tradeserver_client.TradeserverNotConfigured:
                        _test_result("_admin_tradeserver_result", False,
                                     "Zuerst eine Base-URL speichern.")
                        status.update(label="Verbindungstest fehlgeschlagen",
                                      state="error", expanded=False)
                    except tradeserver_client.TradeserverAuthError as exc:
                        _test_result("_admin_tradeserver_result", False, str(exc))
                        status.update(label="API-Key abgelehnt", state="error", expanded=False)
                    except tradeserver_client.TradeserverConnectionError as exc:
                        _test_result("_admin_tradeserver_result", False, str(exc))
                        status.update(label="Tradeserver nicht erreichbar",
                                      state="error", expanded=False)
                    except Exception as exc:
                        _test_result("_admin_tradeserver_result", False,
                                     f"Verbindungstest fehlgeschlagen ({type(exc).__name__}). "
                                     "Base-URL und Tradeserver prüfen.")
                        status.update(label="Verbindungstest fehlgeschlagen",
                                      state="error", expanded=False)
        _render_test_result("_admin_tradeserver_result")

    with st.container(border=True):
        section_header("Sync-Historie", "Die letzten Läufe des Tradeserver-Syncs.",
                       help_key="tradeserver_sync")
        runs = db.list_tradeserver_sync_runs(limit=8)
        if not runs:
            st.caption("Noch kein Sync gelaufen. Der Sync-Button steht auf der "
                       "Ergebnisseite neben dem MqlDownloader-Abgleich.")
        else:
            for run in runs:
                summary = run.get("summary") or {}
                detail = (f"{summary.get('signale', '?')} Signale · "
                          f"{summary.get('uebertragen', 0)} PDFs übertragen · "
                          f"{summary.get('uebersprungen', 0)} unverändert")
                zustand = ("abgebrochen" if run["status"] == "abgebrochen" else "ok")
                st.caption(f"{run['started_at']} · {zustand} · {detail}"
                           + (f" · Abbruch: {summary['abgebrochen']}"
                              if summary.get("abgebrochen") else ""))

with rest_api_tab:
    with st.container(border=True):
        section_header("REST-API für MqlRealMonitor",
                       "Schreibgeschütztes Interface, über das der MqlRealMonitor die "
                       "Signalliste samt Ampel abholt (Button „KiScanner“). Läuft nur "
                       "auf diesem Rechner (127.0.0.1); Änderungen greifen nach dem "
                       "nächsten App-Start.",
                       help_key="settings_rest_api")
        rest_enabled = st.toggle("REST-API aktiviert",
                                 value=bool(settings.get("rest_api_enabled", True)),
                                 key="admin_rest_enabled")
        rest_port = st.number_input("Port", min_value=1024, max_value=65535,
                                    value=int(settings.get("rest_api_port") or 8611),
                                    step=1, key="admin_rest_port")
        rest_token = st.text_input(
            "Zugriffs-Token (optional)", type="password", key="admin_rest_token",
            placeholder="Leer lassen = unverändert")
        rest_token_active = secrets_store.get_secret("rest_api_token")
        st.caption("Token: " + ("hinterlegt — MqlRealMonitor muss denselben Key als "
                                "X-User-Key senden" if rest_token_active
                                else "nicht gesetzt — lokale Aufrufe brauchen keinen Key"))
        st.caption("Endpunkte: /api/v1/health und /api/v1/signals"
                   " (Filter z. B. ?ampel=gruen,gelb)")
        rest_dirty = (rest_enabled != bool(settings.get("rest_api_enabled", True))
                      or int(rest_port) != int(settings.get("rest_api_port") or 8611)
                      or bool(rest_token.strip()))
        _draft_status(rest_dirty, clean_label="Gespeicherte Werte")
        rest_save_column, rest_test_column = st.columns(2)
        with rest_save_column:
            if action_button("REST-Einstellungen speichern", key="admin_rest_save",
                             type="primary", help_key="settings_rest_api",
                             icon=":material/save:"):
                if rest_token.strip():
                    secrets_store.save_secrets(rest_api_token=rest_token.strip())
                _save_group({"rest_api_enabled": bool(rest_enabled),
                             "rest_api_port": int(rest_port)},
                            "REST-Einstellungen gespeichert. Neustart der App, "
                            "wenn Port oder Aktivierung geändert wurden.",
                            clear_result="_admin_rest_result")
        with rest_test_column:
            if action_button("REST-API testen", key="admin_rest_test",
                             help_key="settings_rest_api",
                             icon=":material/network_check:"):
                import requests as _requests
                saved = config.load_settings()
                url = (f"http://127.0.0.1:{int(saved.get('rest_api_port') or 8611)}"
                       "/api/v1/health")
                headers = {}
                if secrets_store.get_secret("rest_api_token"):
                    headers["X-User-Key"] = secrets_store.get_secret("rest_api_token")
                try:
                    resp = _requests.get(url, headers=headers, timeout=3.0)
                    ok = (resp.status_code == 200
                          and resp.json().get("status") == "ok")
                    if ok:
                        info = resp.json()
                        _test_result("_admin_rest_result", True,
                                     f"REST-API erreichbar · Dienst {info.get('service', '?')} "
                                     f"· Version {info.get('version', '?')} · Token akzeptiert")
                    else:
                        _test_result("_admin_rest_result", False,
                                     f"Unerwartete Antwort: HTTP {resp.status_code} "
                                     f"({resp.text[:120]})")
                except Exception as exc:
                    _test_result("_admin_rest_result", False,
                                 f"Nicht erreichbar unter {url} ({type(exc).__name__}). "
                                 "Läuft die App? Port/Token prüfen und App ggf. neu starten.")
        _render_test_result("_admin_rest_result")

with scan_tab:
    filters_column, risk_column = st.columns(2, gap="medium")
    with filters_column, st.container(border=True):
        section_header("Scanprofil", "Ausgangswerte für neue Scans. Größerer Umfang benötigt mehr Zeit.",
                       help_key="settings_filters")
        pages = st.number_input("Listen-Seiten je MT4 / MT5", *config.SCAN_INPUT_BOUNDS["listen_seiten"], value=int(settings["listen_seiten"]), key="admin_pages")
        top_n = st.number_input("Export-Kandidaten", *config.SCAN_INPUT_BOUNDS["top_n_export"], value=int(settings["top_n_export"]), key="admin_topn")
        weeks = st.number_input("Mindesthistorie in Wochen", *config.SCAN_INPUT_BOUNDS["min_wochen"], value=int(settings["min_wochen"]), key="admin_weeks")
        subscribers = st.number_input("Mindest-Abonnenten", *config.SCAN_INPUT_BOUNDS["min_abonnenten"], value=int(settings["min_abonnenten"]), key="admin_subscribers")
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
        section_header(
            "Vom Engine-Befund zum Bericht",
            "Fünf Vorlagen übersetzen bereits berechnete Fakten in verständliche Texte — "
            "vier im Workflow, eine als manuelle Vollanalyse.",
            help_key="settings_prompts",
        )
        st.info(
            "**Die Engine rechnet, die KI interpretiert.** Drawdown, Exposure, "
            "Martingale-Signatur, Stop-Evidenz und Risikostatus stehen vor jedem "
            "Prompt fest. Keine Vorlage darf diese Werte neu berechnen.",
            icon=":material/calculate:",
        )
        st.markdown("**Ablauf pro Signal**")
        engine_card, arrow_one, parallel_card, arrow_two, final_card = st.columns(
            [1.15, .18, 1.6, .18, 1.15], vertical_alignment="center", wrap=False)
        with engine_card.container(border=True):
            st.badge("ENGINE", color="blue", icon=":material/memory:")
            st.markdown("**Forensische Fakten**")
            st.caption("CSV + MQL5-Daten → feste Kennzahlen, Evidenz und Risikokriterien")
        arrow_one.markdown("### →")
        with parallel_card.container(border=True):
            st.badge("PARALLEL", color="gray", icon=":material/call_split:")
            st.markdown("**1 · Trade-Analyse** · starkes Modell")
            st.caption("Handelsweise aus den Trades")
            st.markdown("**2 · Risiko-Analyse** · schnelles Modell")
            st.caption("Risikoprofil aus dem Engine-Befund")
        arrow_two.markdown("### →")
        with final_card.container(border=True):
            st.badge("FINAL", color="green", icon=":material/description:")
            st.markdown("**3 · Gesamtbericht**")
            st.caption("Beide Analysen + dieselben Engine-Fakten → Signalurteil")
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**Danach:**")
            st.badge("4 · Portfolio", color="green", icon=":material/pie_chart:")
            st.caption(
                "Alle fertigen Signalberichte und Engine-Befunde werden zu einem "
                "globalen Portfolio-Gesamtbericht zusammengeführt."
            )
        st.caption(
            "Stufe 1 ist auf schnelle Risikoprofile ausgelegt. Stufe 2 formuliert "
            "die tiefe Trade-Analyse, beide finalen Berichte und den Portfolio-Vorschlag."
        )
        st.warning(
            "ℹ️ Sonderrolle „Tiefenanalyse“ (Erweiterte KI-Analyse): Diese Vorlage "
            "gehört NICHT zum Workflow. Sie wird je Signal über den Button "
            "„Erweiterte KI Analyse machen“ in der Detailansicht gestartet — mit "
            "vollständigen Trade-Daten, dem Stufe-2-Modell und eigener PDF-Ausgabe.",
            icon=":material/info:",
        )

        labels = {"trade_analyse": "1 · Trade-Analyse", "risiko_analyse": "2 · Risikoprofil",
                  "gesamtbericht": "3 · Gesamtbericht", "portfolio": "4 · Portfolio-Vorschlag",
                  "tiefenanalyse": "ℹ️ Tiefenanalyse"}
        placeholders = {
            "trade_analyse": ("kandidat_json", "trades_json"),
            "risiko_analyse": ("kandidat_json", "forensik_json", "kriterien"),
            "gesamtbericht": ("kandidat_json", "forensik_json", "trade_analyse", "risiko_analyse", "kriterien"),
            "portfolio": ("kandidaten_json", "kriterien"),
            "tiefenanalyse": ("kandidat_json", "forensik_json", "trades_json",
                              "signal_name", "signal_url"),
        }
        prompt_flow = {
            "trade_analyse": {
                "why": "Erkennt Handelslogik und Muster, ohne Risikokennzahlen neu zu rechnen.",
                "input": "Kandidatendaten + vorbereitete Trades",
                "output": "Zwischenbericht: Handelsweise",
            },
            "risiko_analyse": {
                "why": "Ordnet die bereits berechneten Forensik-Befunde vorsichtig ein.",
                "input": "Kandidat + Forensik + Grenzwerte",
                "output": "Zwischenbericht: Risikoprofil",
            },
            "gesamtbericht": {
                "why": "Verdichtet beide Sichtweisen zu einem nachvollziehbaren Signalurteil.",
                "input": "Engine-Fakten + beide Zwischenberichte",
                "output": "Finaler Gesamtbericht je Signal",
            },
            "portfolio": {
                "why": "Vergleicht geeignete Signale und prüft Diversifikation statt Einzelmarketing.",
                "input": "Alle Signalbefunde + Gesamtberichte",
                "output": "Finaler Portfolio-Gesamtbericht",
            },
            "tiefenanalyse": {
                "why": "Manuelle Vollanalyse EINES Signals: Risiko, System-Typ, Performance-Forensik.",
                "input": "Kandidat + Forensik + vollständige Trade-Daten + Name/URL",
                "output": "Tiefenanalyse-Bericht als eigenes PDF",
            },
        }
        st.markdown("**Alle Vorlagen auf einen Blick**")
        st.table([
            {
                "Vorlage": labels[key],
                "Warum": prompt_flow[key]["why"],
                "Eingang": prompt_flow[key]["input"],
                "Modell": (settings["model_stufe1"] if key == "risiko_analyse"
                           else settings["model_stufe2"]),
                "Ausgang": prompt_flow[key]["output"],
            }
            for key in ("trade_analyse", "risiko_analyse", "gesamtbericht",
                        "portfolio", "tiefenanalyse")
        ])
        st.space("small")
        st.markdown("**Vorlage verstehen und bearbeiten**")
        prompt_key = st.segmented_control("Vorlage auswählen", list(llm_prompts.PROMPT_FILES),
                                          format_func=lambda key: labels.get(key, key), default="trade_analyse",
                                          key="admin_prompt_choice")
        if prompt_key:
            current = llm_prompts.load_prompt(prompt_key)
            modified = current.strip() != llm_prompts.DEFAULTS[prompt_key].strip()
            model = settings["model_stufe1"] if prompt_key == "risiko_analyse" else settings["model_stufe2"]
            flow = prompt_flow[prompt_key]
            if prompt_key == "tiefenanalyse":
                st.warning(
                    "ℹ️ Gelb markierte Sonderrolle: Die Tiefenanalyse ist die "
                    "Erweiterte KI-Analyse — manuell je Signal aus der "
                    "Detailansicht gestartet, mit vollständigen Trade-Daten im "
                    "Prompt und eigener PDF-Ausgabe (04-tiefenanalyse.pdf).",
                    icon=":material/info:")
            purpose, source, model_card, output = st.columns(4)
            with purpose.container(border=True):
                st.caption("WARUM")
                st.write(flow["why"])
            with source.container(border=True):
                st.caption("EINGANG")
                st.write(flow["input"])
            with model_card.container(border=True):
                st.caption("MODELL")
                st.write(model)
                st.badge("Stufe 1" if prompt_key == "risiko_analyse" else "Stufe 2",
                         color="blue")
            with output.container(border=True):
                st.caption("AUSGANG")
                st.write(flow["output"])
            st.caption("Gespeichert: " + ("eigene Vorlage" if modified else "Standardvorlage"))
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
