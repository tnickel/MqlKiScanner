# -*- coding: utf-8 -*-
"""Scan-Seite: die 4 Pipeline-Schritte mit sichtbarem Fortschritt.

Schritt 1  MQL5-Signal-Listen lesen (MT4+MT5, mit Abonnenten)
Schritt 2  Kandidaten-Liste erzeugen (Filter + Ausschlussliste)
Schritt 3  Daten extrahieren + Forensik (Trade-Export je Kandidat)
Schritt 4  LLM-Auswertung (Stufe 1 Flash-Profile, Stufe 2 Verdicts)

Zusatz: Verifikations-Modus — die 8 realen Datensaetze aus data/raw/
durch die Engine laufen lassen (ohne Netz, ohne Login).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, pipeline
from mqlkiscanner import secrets_store
from mqlkiscanner.app_ui import render_results_table

st.title("Scan", icon=":material/radar:")

settings = config.load_settings()
known = config.load_known_signals()
n_excluded = len(known.get("ausgeschlossen", []))

# ------------------------------------------------- Schritt-Übersicht (Chips)
col1, col2, col3, col4 = st.columns(4)
done = {k: bool(st.session_state.scan_logs.get(k)) for k in ("listen", "kandidaten", "forensik", "llm")}
for col, nr, sid, label, icon in (
        (col1, 1, "listen", "Listen lesen", ":material/travel_explore:"),
        (col2, 2, "kandidaten", "Kandidaten", ":material/filter_list:"),
        (col3, 3, "forensik", "Daten + Forensik", ":material/biotech:"),
        (col4, 4, "llm", "LLM-Auswertung", ":material/psychology:")):
    with col.container(border=True):
        st.markdown(f"{'✅' if done[sid] else icon} **{nr}. {label}**")

# ------------------------------------------------------------ Einstellungen
with st.expander("Scan-Einstellungen", icon=":material/tune:"):
    c1, c2, c3 = st.columns(3)
    listen_seiten = c1.number_input("Listen-Seiten je MT4/MT5", 1, 10,
                                    value=int(settings["listen_seiten"]), key="set_seiten")
    top_n = c2.number_input("Top-N Forensik-Exporte", 1, 25,
                            value=int(settings["top_n_export"]), key="set_topn")
    min_wochen = c3.number_input("Min. Wochen", 0, 260,
                                 value=int(settings["min_wochen"]), key="set_wochen")
    c1, c2, c3 = st.columns(3)
    min_abo = c1.number_input("Min. Abonnenten", 0, 1000,
                              value=int(settings["min_abonnenten"]), key="set_abo")
    llm1 = c2.checkbox("LLM Stufe 1 (Flash-Profile)", value=bool(settings["llm_stufe1"]), key="set_llm1")
    llm2 = c3.checkbox("LLM Stufe 2 (Verdicts)", value=bool(settings["llm_stufe2"]), key="set_llm2")
    st.caption(
        f"Rate-Limit (Admin änderbar): {settings['rate_min_interval_s']:.1f}s je Request, "
        f"{settings['rate_pause_zwischen_signalen_s']:.1f}s Pause je Signal, "
        f"Backoff {settings['rate_backoff_429_s']:.0f}s bei Drosselung. "
        "Zu schnelles Abrufen kann zur Account-Sperre führen.")
    if st.button("Einstellungen speichern", icon=":material/save:"):
        settings.update(listen_seiten=int(listen_seiten), top_n_export=int(top_n),
                        min_wochen=int(min_wochen), min_abonnenten=int(min_abo),
                        llm_stufe1=bool(llm1), llm_stufe2=bool(llm2))
        config.save_settings(settings)
        st.toast("Einstellungen gespeichert.", icon=":material/check:")

run_col, ver_col, llm_col = st.columns([2, 2, 2])
start = run_col.button("Scan starten (Schritte 1–4)", type="primary",
                       icon=":material/play_circle:")
verifizieren = ver_col.button("Verifikations-Datensätze laden (data/raw)",
                              icon=":material/fact_check:")
llm_only = llm_col.button("Nur LLM-Auswertung für vorhandene Ergebnisse",
                          icon=":material/psychology:",
                          disabled=not st.session_state.scan_results)

if not secrets_store.get_secret("mql5_user"):
    st.warning("Kein MQL5-Login gesetzt: Schritt 3 kann Kennzahlen-Seiten lesen, "
               "aber keine Trade-Exporte laden (Admin-Bereich eintragen).",
               icon=":material/person_off:")

# ------------------------------------------------------------------ Aktionen
if verifizieren:
    raw_files = [str(p) for p in sorted(config.RAW_DIR.glob("*.csv"))] + \
                [str(p) for p in sorted(config.RAW_DIR.glob("*.json"))]
    with st.status("Verifikations-Datensätze durch die Engine", expanded=True) as status:
        st.write(f"{len(raw_files)} Datensätze in data/raw/ …")
        results = pipeline.ScanPipeline.analyze_local_files(raw_files, settings)
        st.session_state.scan_results = results
        st.session_state.scan_logs = {"forensik": [f"{len(results)} Datensätze analysiert."]}
        st.session_state.last_run_file = pipeline.ScanPipeline.save_run(results, {"forensik": ["Verifikationslauf data/raw"]})
        status.update(label=f"{len(results)} Datensätze analysiert — siehe Ergebnisse.",
                      state="complete", expanded=False)

if llm_only and st.session_state.scan_results:
    pipe = pipeline.ScanPipeline(settings)
    with st.status("LLM-Auswertung (GLM)", expanded=True) as status:
        log = pipeline.StepLog()
        pipe.run_llm(st.session_state.scan_results, log,
                     on_progress=lambda i, n, txt: st.write(f"{i}/{n} — {txt}"))
        st.session_state.scan_logs["llm"] = log.lines
        st.session_state.last_run_file = pipeline.ScanPipeline.save_run(
            st.session_state.scan_results,
            {k: v for k, v in st.session_state.scan_logs.items()})
        status.update(label=f"LLM fertig ({pipe.llm.usage.total_tokens} Tokens).",
                      state="complete", expanded=False)

if start:
    pipe = pipeline.ScanPipeline(settings)
    logs: dict[str, list[str]] = {}
    results: list[pipeline.ScanResult] = []
    session = None

    # ---------------- Schritt 1: Listen lesen
    with st.status("Schritt 1: MQL5-Signal-Listen lesen", expanded=True) as status:
        st.write("MT4- und MT5-Listen werden gedrosselt geladen …")
        log = pipeline.StepLog()
        try:
            session = pipeline.Mql5Session(settings)
            signals = pipe.crawl(
                on_progress=lambda i, n, txt: st.write(f"{i}/{n} — {txt}"),
                log=log)
            logs["listen"] = log.lines
            status.update(label=f"Schritt 1 fertig: {len(signals)} Signale.", state="complete")
            st.session_state["_signals"] = signals
        except Exception as exc:
            logs["listen"] = log.lines + [f"FEHLER: {exc}"]
            status.update(label=f"Schritt 1 fehlgeschlagen: {exc}", state="error", expanded=True)
            st.session_state.scan_logs = logs
            st.stop()

    # ---------------- Schritt 2: Kandidatenliste
    with st.status("Schritt 2: Kandidaten-Liste erzeugen", expanded=True) as status:
        log = pipeline.StepLog()
        candidates = pipe.build_candidates(st.session_state.get("_signals", []), log)
        logs["kandidaten"] = log.lines
        for line in log.lines:
            st.write(line)
        top_preview = candidates[:15]
        if top_preview:
            st.dataframe(
                [{"ID": c["id"], "Name": c.get("name"), "Plattform": c.get("platform"),
                  "Abonnenten": c.get("abonnenten"), "Wochen": c.get("wochen"),
                  "Growth %": c.get("growth_pct"), "Abo $": c.get("abo_preis_usd")}
                 for c in top_preview],
                hide_index=True)
        status.update(label=f"Schritt 2 fertig: {len(candidates)} Kandidaten.", state="complete")

    # ---------------- Schritt 3: Daten extrahieren + Forensik
    with st.status("Schritt 3: Daten extrahieren + Forensik", expanded=True) as status:
        from mqlkiscanner.mql5.session import Mql5Session  # noqa: F811

        if session is None:
            session = Mql5Session(settings)
        needs_login = not session.has_credentials
        if needs_login:
            st.warning("Kein MQL5-Login — Kennzahlen-Seiten ja, Trade-Exporte nein. "
                       "Ergebnisse bleiben 'Vorprüfung'.")
        progress = st.progress(0.0, text="0 %")
        log = pipeline.StepLog()
        for idx, cand in enumerate(candidates[: int(settings["top_n_export"])]):
            st.write(f"[{idx + 1}/{min(len(candidates), settings['top_n_export'])}] "
                     f"{cand.get('name')} #{cand['id']} …")
            res = pipe.analyze_candidate(session, cand, log)
            results.append(res)
            progress.progress((idx + 1) / min(len(candidates), settings["top_n_export"]),
                              text=f"{idx + 1} von {min(len(candidates), settings['top_n_export'])}")
        logs["forensik"] = log.lines
        status.update(label=f"Schritt 3 fertig: {len(results)} Signale forensisiert.",
                      state="complete")

    # ---------------- Schritt 4: LLM
    with st.status("Schritt 4: LLM-Auswertung (GLM 2-stufig)", expanded=True) as status:
        log = pipeline.StepLog()
        if not pipe.llm.has_key:
            st.warning("Kein GLM-Key gesetzt (Admin) — Schritt 4 übersprungen. "
                       "Die Engine-Ergebnisse sind bereits bewertbar.")
        pipe.run_llm(results, log,
                     on_progress=lambda i, n, txt: st.write(f"{i}/{n} — {txt}"))
        logs["llm"] = log.lines
        for line in log.lines[-6:]:
            st.write(line)
        status.update(label=f"Schritt 4 fertig ({pipe.llm.usage.total_tokens} Tokens).",
                      state="complete")

    st.session_state.scan_results = results
    st.session_state.scan_logs = logs
    st.session_state.last_run_file = pipeline.ScanPipeline.save_run(results, logs)
    st.toast("Scan abgeschlossen.", icon=":material/check_circle:")

# ----------------------------------------------------------------- Ergebnis
st.divider()
n = len(st.session_state.scan_results)
ampeln = [r.ampel for r in st.session_state.scan_results]
if n:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Datensätze", n)
    c2.metric("🟢 Kandidaten", ampeln.count("🟢"))
    c3.metric("🟡 Beobachtung", ampeln.count("🟡"))
    c4.metric("🔴 Schranke/Flag", ampeln.count("🔴"))
    c5.metric("⛔ Ausgeschlossen", ampeln.count("⛔"))

sel_id = render_results_table(st.session_state.scan_results)
if sel_id is not None:
    result = next(r for r in st.session_state.scan_results if r.id == sel_id)
    from mqlkiscanner.app_ui import render_detail
    render_detail(result)
