# -*- coding: utf-8 -*-
"""Visuelle Topologie & Baumdiagramm für den Agentenbetrieb (doc/19).

Rendert ein interaktives Baumdiagramm mit Datenfluss-Pfeilen, Cyberpunk-
Stil, Rollen-Avataren, Direkt-Start-Buttons und einem großen modalen
Detail-Fenster (@st.dialog) mit vollständigem Protokoll, LLM-Prompts/Antworten,
Postfach-Meldungen und Live-Erkenntnissen.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from .. import config, ui_design
from ..ui_design import aktivitaets_banner
from . import journal, lock, rollen

ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"

AVATAR_DATEIEN = {
    "dirigent": "agent_dirigent_thumb.jpg",
    "markt": "agent_markt_thumb.jpg",
    "betreuer": "agent_betreuer_thumb.jpg",
    "chef": "agent_chef_thumb.jpg",
    "melder": "agent_melder_thumb.jpg",
}
AVATAR_FALLBACK_DATEIEN = {
    "dirigent": "agent_dirigent.jpg",
    "markt": "agent_markt.jpg",
    "betreuer": "agent_betreuer.jpg",
    "chef": "agent_chef.jpg",
    "melder": "agent_melder.jpg",
}


@st.cache_data(ttl=3600)
def _lade_avatar_b64(rolle_key: str) -> str:
    """Lädt das Rollenbild als kompakte Base64-Data-URI (gecacht je Rerun)."""
    dateiname = AVATAR_DATEIEN.get(rolle_key)
    pfad = ASSETS_DIR / dateiname if dateiname else None
    if not pfad or not pfad.exists():
        fallback = AVATAR_FALLBACK_DATEIEN.get(rolle_key)
        pfad = ASSETS_DIR / fallback if fallback else None

    if pfad and pfad.exists():
        try:
            daten = base64.b64encode(pfad.read_bytes()).decode("ascii")
            return f"data:image/jpeg;base64,{daten}"
        except OSError:
            return ""
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. Einzelstart-Handler
# ─────────────────────────────────────────────────────────────────────────────

def _starte_rolle(rolle_key: str):
    """Ruft den Tageslauf/Lagebericht der Rolle auf (Lock liegt beim Aufrufer)."""
    from . import betreuer, chef, dirigent, markt, melder

    if rolle_key == "dirigent":
        return dirigent.tageslauf(quelle="gui", log=lambda m: None)
    if rolle_key == "markt":
        return markt.tageslauf(quelle="gui", log=lambda m: None)
    if rolle_key == "betreuer":
        return betreuer.tageslauf(quelle="gui", log=lambda m: None)
    if rolle_key == "chef":
        return chef.lagebericht(quelle="gui", log=lambda m: None)
    if rolle_key == "melder":
        return melder.tagesdigest(quelle="gui", log=lambda m: None)
    raise ValueError(f"Unbekannte Rolle: {rolle_key}")


def _kompakt_zusammenfassung(rolle_key: str, res: dict) -> str:
    """Einzeiler für den Toast — je Rolle aus den Keys, die der Lauf liefert."""
    if res.get("resultat"):
        return str(res["resultat"])
    if res.get("zusammenfassung"):
        return str(res["zusammenfassung"])
    if rolle_key == "dirigent":
        plan = res.get("plan") or []
        return f"Plan: {', '.join(plan)}" if plan else ""
    if rolle_key == "markt":
        symbole = res.get("symbole") or []
        return f"{len(symbole)} Symbol(e) analysiert" if symbole else ""
    if res.get("meldung_id") is not None:
        return f"Meldung #{res['meldung_id']} im Postfach"
    return ""


def agent_manuell_ausfuehren(rolle_key: str) -> None:
    """Führt eine Agenten-Rolle synchron aus — unter dem Lauf-Lock.

    Der Dirigent nimmt das Lock selbst (kurz, beim Lauf-Start — siehe
    dirigent.tageslauf). Für alle anderen Rollen hält dieser Wrapper das
    prozessübergreifende Lock über die GESAMTE Laufdauer: Ohne ihn könnte
    ein GUI-Klick parallel zu einem Daemon-Takt einen zweiten Lauf starten
    (doppelter MQL5-Traffic, konkurrierende Dossier-Schreibzugriffe).
    Bei besetztem Lock gibt es — wie beim Dirigenten — einen dokumentierten
    Skip-Lauf im Journal statt eines stillen Doppel-Laufs.
    """
    rolle = rollen.ROLLEN_NACH_KEY.get(rolle_key)
    anzeige_name = rolle.name if rolle else rolle_key.capitalize()

    banner = aktivitaets_banner(f"Agent »{anzeige_name}« läuft …")
    try:
        with st.spinner(f"Agent »{anzeige_name}« wird ausgeführt..."):
            try:
                if rolle_key == "dirigent":
                    res = _starte_rolle(rolle_key)  # Lock intern (dirigent.py)
                else:
                    with lock.lauf_lock(config.DATA_DIR):
                        res = _starte_rolle(rolle_key)
            except lock.LockBesetzt as exc:
                lauf_id = journal.lauf_starten(rolle_key, quelle="gui")
                pid_info = f" (PID {exc.pid})" if getattr(exc, "pid", None) else ""
                aktion = f"Manueller Startversuch ({anzeige_name})"
                resultat = f"Übersprungen: Ein anderer Lauf{pid_info} war noch aktiv (Kollisionsschutz)."
                journal.schritt_protokollieren(
                    lauf_id, rolle_key, "lock", status="skipped",
                    detail={"grund": str(exc), "pid": getattr(exc, "pid", None),
                            "alter_s": getattr(exc, "alter_s", None)})
                journal.lauf_abschliessen(
                    lauf_id, "skipped", aktion=aktion, resultat=resultat)
                st.error(
                    f"Lauf-Lock besetzt: Ein anderer Prozess führt gerade einen "
                    f"Agentenlauf oder Scan aus{pid_info}. "
                    "Bitte kurz warten.", icon=":material/lock:")
                return

            res = res if isinstance(res, dict) else {}
            status = res.get("status", "ok")
            kompakt = _kompakt_zusammenfassung(rolle_key, res)
            if status == "skipped":
                st.toast(f"⏭️ {anzeige_name}: übersprungen — "
                         f"{res.get('grund') or kompakt}",
                         icon=":material/skip_next:")
            elif status == "fehler":
                st.toast(f"⚠️ {anzeige_name}: Fehler — {res.get('grund') or kompakt}",
                         icon=":material/error:")
            else:
                st.toast(f"⚡ {anzeige_name}: Lauf beendet ({status}) {kompakt}",
                         icon="✅")
            st.rerun()
    except Exception as e:
        st.error(f"Fehler beim Ausführen von {anzeige_name}: {e}",
                 icon=":material/error:")
    finally:
        banner.empty()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Großes modales Detail-Fenster ("Dickes Protokoll")
# ─────────────────────────────────────────────────────────────────────────────

# Meldungen tragen keinen Rollen-Stempel, nur typ/quellen. Diese Zuordnung
# legt fest, welche Postfach-Typen je Rolle wirklich vom Absender stammen —
# Substring-Suche würde Fremd-Treffer liefern („Marktkontext" matcht „markt").
# Dirigent und Markt versenden nichts, der Melder zeigt das gesamte Postfach.
_MELDUNGS_TYPEN_JE_ROLLE: dict[str, tuple[str, ...]] = {
    "betreuer": ("alert",),       # Stilbruch-Sofort-Alerts (P3)
    "chef": ("lagebericht",),
}

@st.dialog("Agenten-Dossier & Protokoll", width="large")
def zeige_agent_dialog(rolle_key: str) -> None:
    """Großes Detailfenster mit vollem Protokoll, Prompts, Antworten und Erkenntnissen."""
    rolle = rollen.ROLLEN_NACH_KEY.get(rolle_key)
    if not rolle:
        st.error(f"Rolle '{rolle_key}' nicht gefunden.")
        return

    avatar_b64 = _lade_avatar_b64(rolle_key)
    settings = config.load_settings()
    modell = settings.get(f"agenten_{rolle_key}_modell", rollen.STANDARD_MODELL)
    max_tokens = settings.get(f"agenten_{rolle_key}_max_tokens", rolle.max_tokens)
    ist_aktiv = settings.get(f"agenten_{rolle_key}_aktiv", True)

    # Header-Bereich im Dialog
    col_img, col_info = st.columns([1, 4], vertical_alignment="center")
    with col_img:
        if avatar_b64:
            st.markdown(
                f'<div style="text-align:center;">'
                f'<img src="{avatar_b64}" style="width:110px; height:110px; border-radius:50%; '
                f'border:3px solid #00D2D3; box-shadow:0 0 20px rgba(0,210,211,0.4); object-fit:cover;">'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"<h1 style='text-align:center;'>{rolle.icon}</h1>", unsafe_allow_html=True)
    with col_info:
        st.subheader(f"{rolle.name} ({rolle.key})")
        st.caption(f"{rolle.beschreibung}")
        with st.container(horizontal=True, vertical_alignment="center", wrap=True):
            st.badge(f"Phase {rolle.phase} · {'Aktiv' if ist_aktiv else 'Inaktiv'}",
                     color="green" if ist_aktiv else "gray")
            st.badge(f"Modell: {modell}", color="blue")
            st.badge(f"Takt: {rolle.takt}", color="primary")
            st.badge(f"Limit: {max_tokens} Tokens", color="gray")

    # Kennzahlen-Schnellzeile
    laeufe = journal.list_laeufe(limit=50, rolle=rolle_key)
    schritte = journal.list_schritte(limit=200, rolle=rolle_key)
    letzter_lauf = laeufe[0] if laeufe else None

    with st.container(border=True):
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Letzter Status", letzter_lauf["status"].upper() if letzter_lauf else "—")
        with m2:
            start_zeit = str(letzter_lauf["start"]) if letzter_lauf and letzter_lauf.get("start") else "—"
            uhrzeit = start_zeit.split(" ")[-1][:8] if " " in start_zeit else start_zeit
            st.metric("Letzter Start", uhrzeit)
        with m3:
            total_tokens = sum(s.get("tokens") or 0 for s in schritte)
            st.metric("Tokens (Protokoll)", f"{total_tokens:,}")
        with m4:
            st.metric("Schritte erfasst", len(schritte))

    # Drei strukturierte Tabs im Dialog
    tab_protokoll, tab_meldungen, tab_erkenntnisse = st.tabs(
        ["📜 Protokoll & Schritte", "💬 Postfach & Meldungen", "🧠 Erkenntnisse & Live-Zustand"]
    )

    # ── TAB 1: PROTOKOLL & SCHRITTE ─────────────────────────────────────
    with tab_protokoll:
        st.markdown(
            f"**Chronologische Ausführungsschritte von »{rolle.name}«**. "
            f"Jeder LLM-Aufruf speichert den vollständigen Prompt und die ungekürzte Antwort."
        )
        if not schritte:
            st.info(f"Für »{rolle.name}« liegen noch keine protokollierten Schritte vor.")
        else:
            schritt_eintraege = [
                {"ID": s["id"], "Zeit": s["ts"], "Schritt": s["schritt"],
                 "Status": s["status"], "Modell": s["modell"] or "Code",
                 "Token": int(s["tokens"] or 0),
                 "Dauer (s)": f"{s['dauer_s']:.2f}" if s.get("dauer_s") is not None else "—"}
                for s in schritte
            ]
            st.dataframe(schritt_eintraege, width="stretch", hide_index=True)

            auswahl_id = st.selectbox(
                "Inspektor: Teilschritt zur Vollanalyse auswählen",
                [s["id"] for s in schritte],
                format_func=lambda sid: next(
                    f"#{s['id']} · {s['ts']} · {s['schritt']} [{s['status']}] ({s['modell'] or 'Code'})"
                    for s in schritte if s["id"] == sid
                ),
                key=f"dialog_step_sel_{rolle_key}",
            )

            if auswahl_id:
                detail = journal.schritt_lesen(auswahl_id)
                if detail:
                    with st.container(border=True):
                        st.markdown(f"#### Teilschritt #{detail['id']}: `{detail['schritt']}`")
                        st.caption(f"Status: **{detail['status']}** · Dauer: **{detail.get('dauer_s', '—')}s** · "
                                   f"Tokens: **{detail.get('tokens', 0)}** · Zeit: **{detail['ts']}**")

                        if detail.get("detail"):
                            with st.expander("Parameter & Metadaten (JSON)", expanded=False):
                                st.json(detail["detail"])

                        if detail.get("prompt"):
                            st.markdown("📥 **Gesendeter Prompt (vollständig)**")
                            st.text_area(
                                "Prompt", value=detail["prompt"], height=250, disabled=True,
                                label_visibility="collapsed", key=f"dialog_prompt_{auswahl_id}"
                            )

                        if detail.get("antwort"):
                            st.markdown("📤 **Modell-Antwort (vollständig)**")
                            st.text_area(
                                "Antwort", value=detail["antwort"], height=250, disabled=True,
                                label_visibility="collapsed", key=f"dialog_antwort_{auswahl_id}"
                            )

    # ── TAB 2: POSTFACH & MELDUNGEN ─────────────────────────────────────
    with tab_meldungen:
        if rolle_key == "melder":
            st.markdown("**Das gesamte Postfach** — der Melder versendet Alerts, "
                        "Digests und Lageberichte.")
            relevante = journal.meldungen_lesen(limit=25)
        elif rolle_key in _MELDUNGS_TYPEN_JE_ROLLE:
            st.markdown(f"**Vom Agenten »{rolle.name}« erzeugte Meldungen**.")
            relevante = []
            for typ in _MELDUNGS_TYPEN_JE_ROLLE[rolle_key]:
                relevante.extend(journal.meldungen_lesen(limit=25, typ=typ))
            relevante.sort(key=lambda m: m["ts"], reverse=True)
        elif rolle_key == "markt":
            st.info("Der Marktbeobachter versendet keine Postfach-Meldungen — "
                    "seine Kennzahlen fließen in die Betreuer-Prompts "
                    "(Tab „Erkenntnisse & Live-Zustand“).")
            relevante = []
        else:  # dirigent
            st.info("Der Dirigent plant und protokolliert nur — Meldungen "
                    "versenden Betreuer, Chefermittler und Melder "
                    "(Postfach-Tab der Seite).")
            relevante = []

        if not relevante:
            if rolle_key in _MELDUNGS_TYPEN_JE_ROLLE or rolle_key == "melder":
                st.info(f"Keine spezifischen Postfach-Meldungen für {rolle.name} "
                        "vorhanden.")
        else:
            for m in relevante:
                prio_color = {3: "red", 2: "orange", 1: "blue"}.get(m["prioritaet"], "gray")
                with st.container(border=True):
                    with st.container(horizontal=True, vertical_alignment="center", wrap=True):
                        st.badge(f"P{m['prioritaet']}", color=prio_color)
                        st.badge(m["typ"].upper(), color="gray")
                        st.caption(f"{m['ts']}")
                    st.markdown(f"**{m['titel']}**")
                    st.markdown(m["text"])
                    if m.get("quellen"):
                        st.caption("Quellen-Nachweise: " + ", ".join(f"`{q}`" for q in m["quellen"]))

    # ── TAB 3: ERKENNTNISSE & LIVE-ZUSTAND ──────────────────────────────
    with tab_erkenntnisse:
        if rolle_key == "dirigent":
            st.markdown("### 🎼 Dirigent: Betriebsplanung & Budgets")
            st.markdown(
                "Der Dirigent koordiniert die Zeitpläne, schützt vor Überlastung und "
                "überwacht das Token-Budget."
            )
            t_heute = journal.tokens_heute()
            t_monat = journal.tokens_monat()
            b_tag = int(settings.get("agenten_tagesbudget_tokens", 500_000))
            b_monat = int(settings.get("agenten_monatsbudget_tokens", 5_000_000))

            c1, c2 = st.columns(2)
            with c1:
                st.metric("Token-Verbrauch heute", f"{t_heute:,}")
                st.caption(f"Tageslimit: {b_tag:,}")
                st.progress(min(1.0, t_heute / max(1, b_tag)))
            with c2:
                st.metric("Token-Verbrauch Monat", f"{t_monat:,}")
                st.caption(f"Monatslimit: {b_monat:,}")
                st.progress(min(1.0, t_monat / max(1, b_monat)))

            from .dirigent import ERLAUBTE_AKTIONEN
            st.markdown("**Aktions-Whitelist** (`dirigent.ERLAUBTE_AKTIONEN` — "
                        "nur diese Aktionen kann eine LLM-Entscheidung übernehmen):")
            st.code("\n".join(sorted(ERLAUBTE_AKTIONEN)), language="text")

        elif rolle_key == "markt":
            st.markdown("### 📈 Marktbeobachter: Aktuelle Marktlage")
            from . import markt
            kontext = markt.kontext_heute()
            if not kontext:
                st.info("Noch kein Marktkontext für heute gespeichert. Klicke auf 'Lauf starten', um Kurse abzurufen.")
            else:
                st.caption(f"Erfasst am: {kontext['ts']}")
                st.markdown(f"**LLM-Lagebericht:**\n\n{kontext.get('lage', '')}")

                kennzahlen = kontext.get("kennzahlen", {})
                if kennzahlen:
                    st.markdown("**Erfasste Symbole & Kennzahlen:**")
                    daten = []
                    for sym, k in kennzahlen.items():
                        v_pct = k.get("veraenderung_pct") or {}
                        daten.append({
                            "Symbol": sym,
                            "Close": f"{k.get('close'):.2f}" if k.get("close") is not None else "—",
                            "Heute %": f"{v_pct.get('heute', 0):+.2f}%" if v_pct.get('heute') is not None else "—",
                            "7 Tage %": f"{v_pct.get('7t', 0):+.2f}%" if v_pct.get('7t') is not None else "—",
                            "ATR14 H1": f"{k.get('atr14_h1'):.2f}" if k.get("atr14_h1") is not None else "—",
                            "Range %": f"{k.get('range_pct'):.2f}%" if k.get("range_pct") is not None else "—",
                        })
                    st.dataframe(daten, width="stretch", hide_index=True)

        elif rolle_key == "betreuer":
            st.markdown("### 🛡️ Signal-Betreuer: Dossier-Status & Beobachtungen")
            from .. import db as scanner_db
            from . import dossier as dossier_db

            kandidaten = scanner_db.list_catalog()
            if not kandidaten:
                st.info("Keine Kandidaten im System vorhanden.")
            else:
                st.caption("Auszug der letzten forensischen Dossier-Beobachtungen:")
                for k in kandidaten[:5]:
                    sig_id = k["signal_id"]
                    profil = dossier_db.profil_lesen(sig_id)
                    beob = dossier_db.beobachtungen_lesen(sig_id, limit=3)
                    if profil or beob:
                        with st.expander(f"Signal #{sig_id}: {k.get('name') or 'Unbenannt'}", expanded=False):
                            if profil:
                                st.markdown(f"**Algo-Profil (v{profil['version']}):**")
                                st.markdown(profil["profil_text"][:500] + ("…" if len(profil["profil_text"]) > 500 else ""))
                            if beob:
                                st.markdown(f"**Letzte Beobachtung ({beob[0]['einordnung']}):**")
                                st.markdown(beob[0]["text"])

        elif rolle_key == "chef":
            st.markdown("### 🔍 Chefermittler: Strategische Lage & Empfehlungen")
            meldungen = journal.meldungen_lesen(limit=10, typ="lagebericht")
            if not meldungen:
                st.info("Noch kein Wochen-Lagebericht des Chefermittlers vorliegend.")
            else:
                neuester = meldungen[0]
                st.caption(f"Verfasst am: {neuester['ts']}")
                st.markdown(f"### {neuester['titel']}")
                st.markdown(neuester["text"])

        elif rolle_key == "melder":
            st.markdown("### 📢 Melder: Alarmierungszentrale")
            meldungen = journal.meldungen_lesen(limit=15)
            st.markdown(
                "Der Melder überwacht laufend Ampelwechsel (P2/P3), Stilbrüche (P3) "
                "und stellt den täglichen Digest zusammen."
            )
            p3_count = sum(1 for m in meldungen if m.get("prioritaet") == 3)
            p2_count = sum(1 for m in meldungen if m.get("prioritaet") == 2)
            c1, c2, c3 = st.columns(3)
            c1.metric("Kritische Alerts (P3)", p3_count)
            c2.metric("Warnungen (P2)", p2_count)
            c3.metric("Gesamtmeldungen", len(meldungen))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Baumdiagramm & Cyberpunk Topologie Rendering (Entzerrt, 20% Größer & Dynamisch)
# ─────────────────────────────────────────────────────────────────────────────

def _rendere_topologie_html(aktive_rollen: set[str] | None = None) -> str:
    """Rendert das visualisierte Baumdiagramm im Cyberpunk-Stil.

    - 20% größere Kreise und Portraits für optimale Erkennbarkeit.
    - Melder vertikal nach unten entzerrt (Tier 4 bei cy=440), um Flusslinien und Badges
      maximalen Freiraum ohne Überlappungen zu geben.
    - Dynamisch: Still bei Standby, leuchtend mit animierten Datenstrahlen bei aktiven Läufen.
    """
    aktive = set(aktive_rollen or set())
    ist_ruhig = len(aktive) == 0

    b64_dirigent = _lade_avatar_b64("dirigent")
    b64_markt = _lade_avatar_b64("markt")
    b64_betreuer = _lade_avatar_b64("betreuer")
    b64_chef = _lade_avatar_b64("chef")
    b64_melder = _lade_avatar_b64("melder")

    # Datenstrom-Aktivierung
    stream_dir_mkt_aktiv = "dirigent" in aktive
    stream_dir_bet_aktiv = "dirigent" in aktive
    stream_mkt_bet_aktiv = "markt" in aktive
    stream_mkt_chf_aktiv = "markt" in aktive
    stream_bet_chf_aktiv = "betreuer" in aktive
    stream_bet_mel_aktiv = "betreuer" in aktive or "melder" in aktive
    stream_chf_mel_aktiv = "chef" in aktive

    def cls_stream(ist_aktiv: bool) -> str:
        if ist_ruhig:
            return "flow-calm"
        return "flow-active" if ist_aktiv else "flow-dimmed"

    def cls_alert(ist_aktiv: bool) -> str:
        if ist_ruhig:
            return "flow-alert-calm"
        return "flow-active-alert" if ist_aktiv else "flow-dimmed"

    if ist_ruhig:
        status_html = """
        <rect x="220" y="493" width="340" height="26" rx="13" fill="#0A1424" stroke="#273E5B" stroke-width="1.2"/>
        <circle cx="238" cy="506" r="4.5" fill="#64748B"/>
        <text x="390" y="510" text-anchor="middle" class="status-calm">💤 SYSTEM RUHIG · STANDBY</text>
        """
    else:
        aktive_text = ", ".join(rollen.ROLLEN_NACH_KEY[r].name for r in aktive if r in rollen.ROLLEN_NACH_KEY) or "AGENT"
        status_html = f"""
        <rect x="180" y="491" width="420" height="28" rx="14" fill="#03272C" stroke="#00D2D3" stroke-width="1.8" filter="url(#glow)"/>
        <circle cx="200" cy="505" r="5" fill="#00D2D3" class="beacon-pulse"/>
        <text x="395" y="509" text-anchor="middle" class="status-active">⚡ {aktive_text.upper()} ARBEITET GERADE...</text>
        """

    def radar_effekt(rolle_key: str, cx: int, cy: int, r: int, farbe: str = "#00D2D3") -> str:
        if rolle_key not in aktive:
            return ""
        return f"""
        <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{farbe}" stroke-width="2.8" class="radar-pulse"/>
        <circle cx="{cx}" cy="{cy}" r="{r+5}" fill="none" stroke="{farbe}" stroke-width="3.5" class="active-glow-ring" filter="url(#glowBright)"/>
        <g transform="translate({cx}, {cy-48})">
          <rect x="-28" y="-10" width="56" height="20" rx="10" fill="#04262B" stroke="{farbe}" stroke-width="1.5"/>
          <circle cx="-16" cy="0" r="3.5" fill="{farbe}" class="beacon-pulse"/>
          <text x="5" y="3.5" text-anchor="middle" font-size="9.5" font-weight="900" fill="#F8FAFC" letter-spacing="0.06em">AKTIV</text>
        </g>
        """

    radar_dir = radar_effekt("dirigent", 630, 65, 44, "#00D2D3")
    radar_mkt = radar_effekt("markt", 200, 195, 38, "#38BDF8")
    radar_bet = radar_effekt("betreuer", 1060, 195, 38, "#00D2D3")
    radar_chf = radar_effekt("chef", 380, 340, 38, "#818CF8")
    radar_mel = radar_effekt("melder", 920, 440, 38, "#F59E0B")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 0;
    background: #0A111E;
    color: #F8FAFC;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    overflow: hidden;
    user-select: none;
  }}
  .diagram-wrap {{
    width: 100%;
    height: 540px;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 6px 14px;
  }}
  svg {{
    width: 100%;
    height: 100%;
    max-height: 535px;
    filter: drop-shadow(0 4px 18px rgba(0,0,0,0.5));
  }}
  
  .flow-calm {{
    stroke-dasharray: 6, 6;
    opacity: 0.42;
  }}
  .flow-alert-calm {{
    stroke-dasharray: 6, 5;
    opacity: 0.48;
  }}
  .flow-dimmed {{
    stroke-dasharray: 6, 6;
    opacity: 0.18;
  }}
  .flow-active {{
    stroke-dasharray: 10, 6;
    animation: flowAnim 0.95s linear infinite;
    stroke-width: 3.5px !important;
    opacity: 1 !important;
    filter: url(#glowBright);
  }}
  .flow-active-alert {{
    stroke-dasharray: 8, 5;
    animation: flowAlertAnim 0.75s linear infinite;
    stroke-width: 3.8px !important;
    opacity: 1 !important;
    filter: url(#glowBright);
  }}
  
  @keyframes flowAnim {{
    to {{ stroke-dashoffset: -32; }}
  }}
  @keyframes flowAlertAnim {{
    to {{ stroke-dashoffset: -26; }}
  }}
  @keyframes radarPulse {{
    0% {{ r: 42px; opacity: 0.95; stroke-width: 3.5px; }}
    100% {{ r: 76px; opacity: 0; stroke-width: 0.5px; }}
  }}
  @keyframes activeGlowRing {{
    0%, 100% {{ filter: drop-shadow(0 0 6px #00D2D3); }}
    50% {{ filter: drop-shadow(0 0 22px #00FFFF) drop-shadow(0 0 38px rgba(0,255,255,0.8)); }}
  }}
  @keyframes beaconPulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.3; transform: scale(0.85); }}
  }}
  
  .radar-pulse {{
    animation: radarPulse 1.7s cubic-bezier(0.2, 0.8, 0.4, 1) infinite;
  }}
  .active-glow-ring {{
    animation: activeGlowRing 2s ease-in-out infinite;
  }}
  .beacon-pulse {{
    animation: beaconPulse 1.2s ease-in-out infinite;
    transform-origin: center;
  }}

  .node-title {{
    font-size: 13.5px;
    font-weight: 800;
    letter-spacing: 0.05em;
    fill: #F8FAFC;
  }}
  .node-sub {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.05em;
  }}
  .pill-text {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.03em;
  }}
  .status-calm {{
    font-size: 11px;
    font-weight: 700;
    fill: #94A3B8;
    letter-spacing: 0.06em;
  }}
  .status-active {{
    font-size: 11.5px;
    font-weight: 800;
    fill: #E0F2FE;
    letter-spacing: 0.06em;
  }}
</style>
</head>
<body>
<div class="diagram-wrap">
<svg viewBox="0 0 1260 540" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>
    <linearGradient id="gStream" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00D2D3" stop-opacity="0.95" />
      <stop offset="50%" stop-color="#38BDF8" stop-opacity="0.95" />
      <stop offset="100%" stop-color="#818CF8" stop-opacity="0.95" />
    </linearGradient>
    <linearGradient id="gAlert" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#F59E0B" stop-opacity="0.95" />
      <stop offset="100%" stop-color="#EF4444" stop-opacity="0.95" />
    </linearGradient>
    
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3.5" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
    <filter id="glowBright" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="5.5" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>

    <marker id="arrowCyan" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#00D2D3" />
    </marker>
    <marker id="arrowAmber" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#F59E0B" />
    </marker>
    <marker id="arrowBlue" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#38BDF8" />
    </marker>

    <!-- Clip-Pfade für 20% größere runde Porträts -->
    <clipPath id="cpDir"><circle cx="630" cy="65" r="41" /></clipPath>
    <clipPath id="cpMkt"><circle cx="200" cy="195" r="35" /></clipPath>
    <clipPath id="cpBet"><circle cx="1060" cy="195" r="35" /></clipPath>
    <clipPath id="cpChf"><circle cx="380" cy="340" r="35" /></clipPath>
    <clipPath id="cpMel"><circle cx="920" cy="440" r="35" /></clipPath>
  </defs>

  <!-- HINTERGRUND-RAHMEN (1260 x 540) -->
  <rect x="8" y="8" width="1244" height="524" rx="20" fill="#0E1A2C" stroke="#1E3A5F" stroke-width="1.2" opacity="0.88"/>

  <!-- PFEILE & DATENFLUSS-VERBINDUNGEN -->
  <!-- 1. Dirigent -> Marktbeobachter (06:35 Takt) -->
  <path d="M 570 85 C 430 95, 230 120, 205 155" fill="none" stroke="url(#gStream)" stroke-width="2.8" class="{cls_stream(stream_dir_mkt_aktiv)}" marker-end="url(#arrowCyan)" filter="url(#glow)"/>

  <!-- 2. Dirigent -> Signal-Betreuer (06:45 Takt) -->
  <path d="M 690 85 C 830 95, 1030 120, 1055 155" fill="none" stroke="url(#gStream)" stroke-width="2.8" class="{cls_stream(stream_dir_bet_aktiv)}" marker-end="url(#arrowCyan)" filter="url(#glow)"/>

  <!-- 3. Marktbeobachter -> Signal-Betreuer (Marktkontext ATR) -->
  <path d="M 320 195 L 940 195" fill="none" stroke="#00D2D3" stroke-width="2.4" class="{cls_stream(stream_mkt_bet_aktiv)}" marker-end="url(#arrowCyan)" filter="url(#glow)"/>

  <!-- 4. Marktbeobachter -> Chefermittler -->
  <path d="M 215 280 C 235 315, 310 330, 340 340" fill="none" stroke="url(#gStream)" stroke-width="2.4" class="{cls_stream(stream_mkt_chf_aktiv)}" marker-end="url(#arrowBlue)"/>

  <!-- 5. Signal-Betreuer -> Chefermittler -->
  <path d="M 960 270 C 830 330, 600 335, 495 350" fill="none" stroke="url(#gStream)" stroke-width="2.4" class="{cls_stream(stream_bet_chf_aktiv)}" marker-end="url(#arrowBlue)"/>

  <!-- 6. Signal-Betreuer -> Melder (Entzerrter Alert-Pfad P3 Stilbruch) -->
  <path d="M 1050 280 C 1035 340, 975 390, 940 405" fill="none" stroke="url(#gAlert)" stroke-width="3" class="{cls_alert(stream_bet_mel_aktiv)}" marker-end="url(#arrowAmber)" filter="url(#glow)"/>

  <!-- 7. Chefermittler -> Melder (Wochen-Lagebericht nach unten fließend) -->
  <path d="M 495 360 C 640 385, 780 410, 875 435" fill="none" stroke="#38BDF8" stroke-width="2.4" class="{cls_stream(stream_chf_mel_aktiv)}" marker-end="url(#arrowBlue)"/>

  <!-- BESCHRIFTUNGEN / PILLS (PERFEKT ENTZERRT MIT MAXIMALEM FREIRAUM) -->
  <rect x="330" y="95" width="110" height="22" rx="11" fill="#0A1424" stroke="#00D2D3" stroke-width="0.9"/>
  <text x="385" y="110" text-anchor="middle" class="pill-text" fill="#67E8F9">06:35 Takt</text>

  <rect x="820" y="95" width="110" height="22" rx="11" fill="#0A1424" stroke="#00D2D3" stroke-width="0.9"/>
  <text x="875" y="110" text-anchor="middle" class="pill-text" fill="#67E8F9">06:45 Takt</text>

  <rect x="560" y="184" width="140" height="22" rx="11" fill="#0A1424" stroke="#00D2D3" stroke-width="0.9"/>
  <text x="630" y="199" text-anchor="middle" class="pill-text" fill="#67E8F9">Marktkontext (ATR)</text>

  <rect x="1005" y="330" width="125" height="22" rx="11" fill="#241014" stroke="#EF4444" stroke-width="1.2"/>
  <text x="1067" y="345" text-anchor="middle" class="pill-text" fill="#FCA5A5">⚡ P3 Stilbrüche</text>

  <rect x="625" y="388" width="130" height="22" rx="11" fill="#0A1424" stroke="#38BDF8" stroke-width="0.9"/>
  <text x="690" y="403" text-anchor="middle" class="pill-text" fill="#BAE6FD">Wochenbericht</text>

  <!-- KNOTEN 1: DIRIGENT (Spitze Center, 20% größer) -->
  <g>
    {radar_dir}
    <circle cx="630" cy="65" r="44" fill="none" stroke="#00D2D3" stroke-width="3.5" filter="url(#glow)"/>
    <image href="{b64_dirigent}" xlink:href="{b64_dirigent}" x="588" y="23" width="84" height="84" clip-path="url(#cpDir)" preserveAspectRatio="xMidYMid slice"/>
    <rect x="515" y="122" width="230" height="32" rx="16" fill="#102038" stroke="#00D2D3" stroke-width="1.8"/>
    <text x="630" y="137" text-anchor="middle" class="node-title">🎼 DIRIGENT</text>
    <text x="630" y="148" text-anchor="middle" class="node-sub" fill="#00D2D3">MASTER-ORCHESTRATOR</text>
  </g>

  <!-- KNOTEN 2: MARKTBEOBACHTER (Mid Left, 20% größer) -->
  <g>
    {radar_mkt}
    <circle cx="200" cy="195" r="38" fill="none" stroke="#38BDF8" stroke-width="3" filter="url(#glow)"/>
    <image href="{b64_markt}" xlink:href="{b64_markt}" x="165" y="160" width="70" height="70" clip-path="url(#cpMkt)" preserveAspectRatio="xMidYMid slice"/>
    <rect x="85" y="245" width="230" height="32" rx="16" fill="#102038" stroke="#38BDF8" stroke-width="1.6"/>
    <text x="200" y="260" text-anchor="middle" class="node-title">📈 MARKTBEOBACHTER</text>
    <text x="200" y="271" text-anchor="middle" class="node-sub" fill="#38BDF8">MT5-KURSDATEN & ATR</text>
  </g>

  <!-- KNOTEN 3: SIGNAL-BETREUER (Mid Right, 20% größer) -->
  <g>
    {radar_bet}
    <circle cx="1060" cy="195" r="38" fill="none" stroke="#00D2D3" stroke-width="3" filter="url(#glow)"/>
    <image href="{b64_betreuer}" xlink:href="{b64_betreuer}" x="1025" y="160" width="70" height="70" clip-path="url(#cpBet)" preserveAspectRatio="xMidYMid slice"/>
    <rect x="945" y="245" width="230" height="32" rx="16" fill="#102038" stroke="#00D2D3" stroke-width="1.6"/>
    <text x="1060" y="260" text-anchor="middle" class="node-title">🛡️ SIGNAL-BETREUER</text>
    <text x="1060" y="271" text-anchor="middle" class="node-sub" fill="#2DD4BF">DELTAS & DOSSIERS</text>
  </g>

  <!-- KNOTEN 4: CHEFERMITTLER (Tier 3 Left-Center, 20% größer) -->
  <g>
    {radar_chf}
    <circle cx="380" cy="340" r="38" fill="none" stroke="#818CF8" stroke-width="3" filter="url(#glow)"/>
    <image href="{b64_chef}" xlink:href="{b64_chef}" x="345" y="305" width="70" height="70" clip-path="url(#cpChf)" preserveAspectRatio="xMidYMid slice"/>
    <rect x="265" y="390" width="230" height="32" rx="16" fill="#102038" stroke="#818CF8" stroke-width="1.6"/>
    <text x="380" y="405" text-anchor="middle" class="node-title">🔍 CHEFERMITTLER</text>
    <text x="380" y="416" text-anchor="middle" class="node-sub" fill="#A5B4FC">SYNTHESE & BERICHT</text>
  </g>

  <!-- KNOTEN 5: MELDER (Tier 4 Down-Right, entzerrt & 20% größer) -->
  <g>
    {radar_mel}
    <circle cx="920" cy="440" r="38" fill="none" stroke="#F59E0B" stroke-width="3" filter="url(#glow)"/>
    <image href="{b64_melder}" xlink:href="{b64_melder}" x="885" y="405" width="70" height="70" clip-path="url(#cpMel)" preserveAspectRatio="xMidYMid slice"/>
    <rect x="795" y="490" width="250" height="32" rx="16" fill="#102038" stroke="#F59E0B" stroke-width="1.6"/>
    <text x="920" y="505" text-anchor="middle" class="node-title">📢 MELDER</text>
    <text x="920" y="516" text-anchor="middle" class="node-sub" fill="#FCD34D">ALERTS & POSTFACH</text>
  </g>

  <!-- STATUS-INDIKATOR (UNTEN LINKS ENTZERRT) -->
  {status_html}

</svg>
</div>
</body>
</html>"""


def _rendere_kompakte_kachel(rolle: rollen.Rolle, settings: dict, ist_aktiv: bool = False) -> None:
    """Rendert eine schlanke, platzsparende Karte für eine Agentenrolle mit ⓘ-Erklärungsfenster."""
    avatar_b64 = _lade_avatar_b64(rolle.key)
    laeufe = journal.list_laeufe(limit=1, rolle=rolle.key)
    letzter = laeufe[0] if laeufe else None
    modell = settings.get(f"agenten_{rolle.key}_modell", rollen.STANDARD_MODELL)

    status_color = "gray"
    status_text = "Bereit"
    if ist_aktiv:
        status_color = "primary"
        status_text = "Läuft..."
    elif letzter:
        s = (letzter.get("status") or "").lower()
        if s == "ok":
            status_color = "green"
            start_zeit = str(letzter.get("start") or "")
            uhrzeit = start_zeit.split(" ")[-1][:5] if " " in start_zeit else start_zeit[:5]
            status_text = f"OK ({uhrzeit})"
        elif s == "laeuft":
            status_color = "primary"
            status_text = "Läuft..."
        elif s == "skipped":
            status_color = "orange"
            status_text = "Skip"
        else:
            status_color = "red"
            status_text = s.upper()

    with st.container(border=True, key=f"agentenkachel_{rolle.key}"):
        # Kopfzeile: Name + Info-Button (ⓘ) für die genaue Funktionserklärung
        c_title, c_info = st.columns([5, 1.2], vertical_alignment="center")
        with c_title:
            st.markdown(
                f"<div style='font-weight:700; font-size:0.92rem; white-space:nowrap; "
                f"overflow:hidden; text-overflow:ellipsis;'>{rolle.name}</div>",
                unsafe_allow_html=True,
            )
        with c_info:
            ui_design.info_button(f"agent_{rolle.key}", key=f"kachel_info_{rolle.key}")

        # Bild zentriert (70px x 70px, 20% größer)
        avatar_border = "3px solid #00FFFF" if ist_aktiv else "2px solid #00D2D3"
        avatar_glow = "box-shadow: 0 0 18px rgba(0, 255, 255, 0.6);" if ist_aktiv else "box-shadow: 0 0 12px rgba(0, 210, 211, 0.3);"
        if avatar_b64:
            st.markdown(
                f'<div style="display:flex; justify-content:center; margin:4px 0 6px;">'
                f'<img src="{avatar_b64}" alt="{rolle.name}" style="width:70px; height:70px; '
                f'border-radius:50%; border:{avatar_border}; {avatar_glow} object-fit:cover;"></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"<h2 style='text-align:center; margin:4px 0;'>{rolle.icon}</h2>", unsafe_allow_html=True)

        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(status_text, color=status_color)
            st.badge(f"P{rolle.phase}", color="blue")

        st.caption(f"Takt: **{rolle.takt.split(' ')[0]}** · `{modell}`")

        # Zwei Buttons nebeneinander (kompakt & passgenau)
        c_btn1, c_btn2 = st.columns(2, gap="xsmall")
        with c_btn1:
            if st.button("⚡ Start", key=f"run_{rolle.key}", width="stretch",
                         help=f"Agent »{rolle.name}« sofort starten"):
                st.session_state["aktiver_agent_lauf"] = rolle.key
                st.rerun()

        with c_btn2:
            if st.button("🔍 Details", key=f"details_{rolle.key}", width="stretch",
                         help=f"Protokoll & Erkenntnisse von »{rolle.name}« anzeigen"):
                zeige_agent_dialog(rolle.key)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Haupt-Render-Einstiegspunkt
# ─────────────────────────────────────────────────────────────────────────────

def rendere_agenten_baum() -> None:
    """Rendert das vollständige visuelle Baumdiagramm und kompakte Kacheln."""
    settings = config.load_settings()

    # 1. Ermitteln, welche Agenten aktiv sind
    db_aktive = journal.aktive_rollen()
    gui_aktiver = st.session_state.get("aktiver_agent_lauf")
    aktive_rollen = set(db_aktive)
    if gui_aktiver:
        aktive_rollen.add(gui_aktiver)

    # 2. Das dynamische Baumdiagramm im IFrame rendern (Breit: 1260px, Höhe: 545px)
    st.iframe(_rendere_topologie_html(aktive_rollen=aktive_rollen), height=545)

    # 3. Kompakte Steuerungs-Kacheln in 5 Spalten direkt darunter (passt perfekt auf eine Seite!)
    st.markdown(
        "<div style='font-size:0.85rem; font-weight:700; color:#67E8F9; text-transform:uppercase; "
        "letter-spacing:0.08em; margin:0.4rem 0 0.3rem;'>Agenten-Steuerung & Protokoll-Inspektor</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(5, gap="small")
    for idx, rolle in enumerate(rollen.ROLLEN):
        with cols[idx]:
            _rendere_kompakte_kachel(rolle, settings, ist_aktiv=(rolle.key in aktive_rollen))

    # 4. Falls ein Start per Button getriggert wurde: Jetzt ausführen (während das Diagramm bereits leuchtet!)
    if gui_aktiver:
        rolle_start = st.session_state.pop("aktiver_agent_lauf", None)
        if rolle_start:
            agent_manuell_ausfuehren(rolle_start)
