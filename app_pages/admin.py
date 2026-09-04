# -*- coding: utf-8 -*-
"""Admin-Bereich: Credentials (GLM-Key, MQL5-Login), Rate-Limits, Prompts.

Sicherheit (AGENTS.md + Nutzeranforderung):
- Alle Geheimnisse liegen NUR in Umgebung / .env / config/secrets.local.json
  (alles gitignored). Diese Seite speichert nur dorthin.
- Im Frontend erscheint der Key nie im Klartext (Passwort-Feld, Maskierung).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, secrets_store
from mqlkiscanner.llm import client as llm_client
from mqlkiscanner.llm import prompts as llm_prompts
from mqlkiscanner.mql5.session import Mql5Session

st.title("Admin & Einstellungen", icon=":material/settings:")

admin1, admin2 = st.tabs(["Zugänge & Modelle", "Prompts & Rate-Limits"])

# ============================================================ Zugänge
with admin1:
    st.subheader("GLM (Z.ai) — LLM-Zugang", icon=":material/key:")
    st.caption(
        "Der Key wird in `config/secrets.local.json` bzw. der Umgebungsvariable "
        "`GLM_API_KEY` gespeichert — beides ist via .gitignore aus dem Repository "
        "ausgeschlossen und landet NIE auf GitHub.")
    env_key = secrets_store.get_secret("glm_api_key")
    if env_key:
        st.success(f"Key gesetzt: {env_key[:6]}…{env_key[-4:]} (maskiert)", icon=":material/visibility_off:")
    else:
        st.error("Kein GLM-Key gesetzt.")

    new_key = st.text_input("GLM-API-Key (neu setzen/ändern)", type="password",
                            placeholder="leer lassen = unverändert",
                            help="Format: xxxxxxxxxx.xxxxxxxxxxx — von z.ai / bigmodel.cn.")
    c1, c2 = st.columns(2)
    if c1.button("Key speichern", icon=":material/save:"):
        if new_key.strip():
            secrets_store.save_secrets(glm_api_key=new_key.strip())
            st.toast("GLM-Key gespeichert (lokal, nicht im Git).", icon=":material/check:")
        else:
            st.warning("Leeres Feld — nichts geändert.")
    if c2.button("Key aus Konfiguration entfernen", icon=":material/delete:"):
        secrets_store.save_secrets(glm_api_key="")
        st.toast("GLM-Key entfernt.")

    settings = config.load_settings()
    c1, c2, c3 = st.columns(3)
    m1 = c1.selectbox("Stufe 1 — Risiko-Analyse (schnell/günstig, Flash-Klasse)",
                      ["glm-5.3-flash", "glm-4.5-flash", "glm-4.5-air"],
                      index=["glm-5.3-flash", "glm-4.5-flash", "glm-4.5-air"].index(
                          settings.get("model_stufe1", "glm-5.3-flash")),
                      key="admin_model1")
    m2 = c2.selectbox("Stufe 2 — Trade-Analyse + Gesamtbericht (stark)",
                      ["glm-5.3", "glm-5.2", "glm-5.1", "glm-4.5"],
                      index=["glm-5.3", "glm-5.2", "glm-5.1", "glm-4.5"].index(
                          settings.get("model_stufe2", "glm-5.3")),
                      key="admin_model2")
    budget = c3.number_input("Token-Budget je Lauf", 50_000, 50_000_000,
                             value=int(settings.get("llm_max_total_tokens", 5_000_000)),
                             step=100_000, key="admin_budget")
    st.caption(
        "**Endpunkt wählen** (getrennte Kontingente bei Z.ai): Abo-Keys aus dem "
        "GLM Coding Plan laufen über `…/api/coding/paas/v4` — Pay-as-you-go-Keys "
        "mit Guthaben über `…/api/paas/v4`. Falscher Endpunkt = Fehler 1113 "
        "„Insufficient balance“.")
    url_choice = st.selectbox(
        "GLM-Endpunkt",
        ["GLM Coding Plan (Abo)", "Standard-API (Guthaben)", "Eigene URL"],
        index=0 if "coding" in (settings.get("glm_base_url") or "") else
              (1 if settings.get("glm_base_url") == config.GLM_BASE_URL_API else 2),
        key="admin_baseurl_choice")
    custom_url = st.text_input(
        "Eigene Base-URL (nur bei „Eigene URL“)",
        value=settings.get("glm_base_url", config.GLM_BASE_URL),
        key="admin_baseurl_custom", disabled=url_choice != "Eigene URL")
    if st.button("Modelle + Endpunkt + Budget speichern", icon=":material/save:"):
        if url_choice == "GLM Coding Plan (Abo)":
            new_base = config.GLM_BASE_URL_CODING
        elif url_choice == "Standard-API (Guthaben)":
            new_base = config.GLM_BASE_URL_API
        else:
            new_base = custom_url.strip().rstrip("/")
        config.save_settings({**settings, "model_stufe1": m1, "model_stufe2": m2,
                              "llm_max_total_tokens": int(budget),
                              "glm_base_url": new_base})
        st.toast(f"Konfiguration gespeichert. Endpunkt: {new_base}", icon=":material/check:")

    if st.button("Verbindung testen", icon=":material/network_check:"):
        test_base = config.load_settings().get("glm_base_url") or config.GLM_BASE_URL
        with st.spinner(f"Teste GLM-API über {test_base} …"):
            client = llm_client.GlmClient(model_stufe1=m1, model_stufe2=m2,
                                          base_url=test_base)
            try:
                out = client.test_connection()
                st.success(f"Verbindung ok — Antwort: {out['antwort']!r} "
                           f"({out['usage']['total_tokens']} Tokens, Endpunkt {client.base_url}).")
            except llm_client.LlmNoBalanceError as exc:
                st.warning(f"Key/Endpunkt-Problem: {exc}")
            except llm_client.LlmError as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("MQL5 — Login für Trade-Exporte", icon=":material/person:")
    st.caption(
        "Login/Passwort landen NUR in Umgebung (`MQL5_USER`/`MQL5_PASS`) bzw. "
        "`config/secrets.local.json` — nie im Code, nie im Git. "
        "Achtung: Zu schnelles Scraping kann zur Account-Sperre führen; "
        "Rate-Limits unten nicht aggressively senken.")
    status = secrets_store.secret_status()
    st.markdown(f"Login: {'🟢 gesetzt' if status['mql5_user'] else '🔴 nicht gesetzt'}")
    new_user = st.text_input("MQL5-Login (E-Mail/Benutzer)", placeholder="leer = unverändert")
    new_pass = st.text_input("MQL5-Passwort", type="password", placeholder="leer = unverändert")
    c1, c2 = st.columns(2)
    if c1.button("MQL5-Zugang speichern", icon=":material/save:"):
        fields = {}
        if new_user.strip():
            fields["mql5_user"] = new_user.strip()
        if new_pass:
            fields["mql5_pass"] = new_pass
        if fields:
            secrets_store.save_secrets(**fields)
            st.toast("MQL5-Zugang gespeichert (lokal, nicht im Git).", icon=":material/check:")
        else:
            st.info("Keine Änderung eingegeben.")
    if c2.button("MQL5-Login testen", icon=":material/network_check:"):
        sess = Mql5Session(config.load_settings())
        if not sess.has_credentials:
            st.error("Erst Login + Passwort speichern.")
        else:
            with st.spinner("Login bei MQL5 …"):
                try:
                    ok = sess.login()
                    if ok:
                        st.success("Login erfolgreich — Trade-Exporte verfügbar.")
                    else:
                        st.error("Login fehlgeschlagen (Credentials prüfen).")
                except Exception as exc:
                    st.error(f"Login-Fehler: {exc}")

# ============================================================ Prompts + Limits
with admin2:
    st.subheader("LLM-Prompts (dreistufig)", icon=":material/edit_note:")
    st.caption(
        f"Prompt 1 **Trade-Analyse** (`{settings.get('model_stufe2', 'glm-5.3')}`, stark): "
        "ermittelt die Strategie ANHAND DER TRADES. Prompt 2 **Risiko-Analyse** "
        f"(`{settings.get('model_stufe1', 'glm-5.3-flash')}`): Risikoprofil aus der "
        "Forensik. Prompt 3 **Gesamtbericht** (`glm-5.3`, stark): wertet ALLE "
        "Teilergebnisse aus — ausführlich; in der Tabelle steht nur die Kurzfassung. "
        "Die Engine übergibt nur fertige Befund-JSONs — das LLM rechnet nie selbst. "
        "Vorlagen sind editierbar und werden unter `config/prompts/` gespeichert.")
    _PROMPT_LABELS = {
        "trade_analyse": "Prompt 1 — Trade-Analyse (stark)",
        "risiko_analyse": "Prompt 2 — Risiko-Analyse (Flash)",
        "gesamtbericht": "Prompt 3 — Gesamtbericht (stark, ausführlich)",
    }
    prompt_key = st.segmented_control(
        "Vorlage", list(llm_prompts.PROMPT_FILES),
        format_func=lambda k: _PROMPT_LABELS.get(k, k),
        default="trade_analyse")
    if prompt_key:
        current = llm_prompts.load_prompt(prompt_key)
        changed = llm_prompts.prompt_is_modified(prompt_key)
        st.markdown(f"Status: {'🟡 geändert (nicht Standard)' if changed else '⬜ Standard-Vorlage'}")
        _platzhalter = {
            "trade_analyse": "{kandidat_json}, {trades_json}",
            "risiko_analyse": "{kandidat_json}, {forensik_json}, {kriterien}",
            "gesamtbericht": ("{kandidat_json}, {forensik_json}, {trade_analyse}, "
                              "{risiko_analyse}, {kriterien}"),
        }
        edited = st.text_area(
            f"Prompt-Vorlage (Platzhalter: {_platzhalter[prompt_key]})",
            value=current, height=420, key=f"prompt_{prompt_key}")
        c1, c2, c3 = st.columns([1, 1, 2])
        if c1.button("Speichern", icon=":material/save:"):
            llm_prompts.save_prompt(prompt_key, edited)
            st.toast("Prompt gespeichert.", icon=":material/check:")
            st.rerun()
        if c2.button("Auf Standard zurücksetzen", icon=":material/restore:"):
            llm_prompts.reset_prompt(prompt_key)
            st.toast("Standard wiederhergestellt.", icon=":material/check:")
            st.rerun()
        with c3.popover("Vorschau Standard-Vorlage"):
            st.markdown(llm_prompts.DEFAULTS[prompt_key])

    st.divider()
    st.subheader("Rate-Limits & Scan-Umfang", icon=":material/speed:")
    st.caption(
        "MQL5-Server schonen: Mindestabstand je Request (doc/02 empfiehlt 1–2 s), "
        "zusätzliche Pause zwischen Signalen, Backoff bei Drosselung (429/503).")
    settings = config.load_settings()
    c1, c2 = st.columns(2)
    min_interval = c1.number_input("Mindestabstand Requests (Sekunden)", 0.5, 30.0,
                                   value=float(settings["rate_min_interval_s"]), step=0.5)
    pause = c2.number_input("Pause zwischen Signalen (Sekunden)", 0.0, 120.0,
                            value=float(settings["rate_pause_zwischen_signalen_s"]), step=1.0)
    c1, c2 = st.columns(2)
    backoff = c1.number_input("Backoff bei 429/503 (Sekunden)", 10.0, 300.0,
                              value=float(settings["rate_backoff_429_s"]), step=5.0)
    seiten = c2.number_input("Listen-Seiten je MT4/MT5", 1, 10,
                             value=int(settings["listen_seiten"]))
    c1, c2 = st.columns(2)
    schranke = c1.number_input("Harte Drawdown-Schranke (EQ-DD %)", 5.0, 100.0,
                               value=float(settings["schranke_eq_dd_pct"]), step=1.0)
    ertrag = c2.number_input("Mindest-Ertrag (%/Monat)", 0.0, 50.0,
                             value=float(settings["min_ertrag_pct_monat"]), step=0.5)
    if st.button("Limits speichern", icon=":material/save:"):
        config.save_settings({**settings,
                              "rate_min_interval_s": float(min_interval),
                              "rate_pause_zwischen_signalen_s": float(pause),
                              "rate_backoff_429_s": float(backoff),
                              "listen_seiten": int(seiten),
                              "schranke_eq_dd_pct": float(schranke),
                              "min_ertrag_pct_monat": float(ertrag)})
        st.toast("Limits gespeichert.", icon=":material/check:")
