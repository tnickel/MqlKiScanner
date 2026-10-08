# -*- coding: utf-8 -*-
"""Stationsdialoge der Scan-Seite: die sieben Kugel-Detailansichten (Stufe 0
bis Abgleich), Problem-Dialog und ihre Tabellen-Helfer.

Aus app_pages/scan.py ausgelagert (08.10.2026): Die Definitions-Reihenfolge
bleibt gleich — der Dialog-Host registriert sich weiterhin beim Import in
jedem App-Lauf. Die Kennzahl-Berechnung (_station_kennzahlen) bleibt beim
Läufer in scan.py; hier wohnt nur die Darstellung.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from mqlkiscanner import client_updates, config, db, pipeline


# Schritt-Status-Labels (Label, Farbe, Material-Icon) — identisch zur
# Live-Anzeige in scan.py, das sie von hier importiert.
STATES = {
    "pending": ("Wartet", "gray", "schedule"),
    "running": ("Läuft", "blue", "autorenew"),
    "complete": ("Fertig", "green", "check_circle"),
    "warning": ("Mit Hinweisen", "orange", "warning"),
    "error": ("Fehlgeschlagen", "red", "error"),
    "skipped": ("Übersprungen", "gray", "skip_next"),
}


def _problem_art(result) -> tuple[str, str, str]:
    """Kategorie + Handlungs-Hinweis für ein Problem-Ergebnis (Badge-Label, Icon, Hinweis)."""
    text = result.fehler or ""
    if "cross_broker=false" in text:
        return (
            "Broker-Kontrakt nicht verifiziert",
            ":material/fact_check:",
            "Das Instrument wurde erkannt und ein Broker-Suffix bereits entfernt. "
            "Die Sperre betrifft die Kontraktgröße: Bei Öl und einigen CFDs kann "
            "1 Lot je Broker stark unterschiedliche Einheiten bedeuten. Deshalb "
            "darf die Engine den bekannten Wert eines anderen Brokers nicht übernehmen. "
            "Broker/Server und dessen MT5-Kontraktspezifikation prüfen; nur den belegten "
            "Broker anschließend in data/contract_specs.json ergänzen.",
        )
    if "Kontraktspec" in text:
        return (
            "Instrument nicht freigegeben",
            ":material/rule:",
            "Lösbar: Auf der MQL5-Seite des Signals den Broker/Server nachsehen, das "
            "Instrument in data/contract_specs.json für diesen Broker freigeben "
            "(Eintrag „brokers“ ergänzen) und das Signal anschließend neu prüfen.",
        )
    if "Kapitalbasis" in text:
        return (
            "Kapitalbasis unbekannt",
            ":material/account_balance_wallet:",
            "Der Trade-Export beginnt ohne Einzahlung vor dem ersten Trade — z. B. gekürzte "
            "Historie oder eine Auszahlung vor Handelsbeginn. Ohne Startkapital sind Schockanteil "
            "und die 30-%-Schranke nicht berechenbar; das Signal bleibt deshalb bewusst ohne Urteil.",
        )
    if not result.forensik_vorhanden:
        return (
            "Nur Vorprüfung",
            ":material/info:",
            "Es liegen keine vollständigen Handelsdaten vor (z. B. kein MQL5-Login oder kein "
            "Trade-Export verfügbar). Gezählt wird trotzdem, damit nichts unter den Tisch fällt.",
        )
    return (
        "Prüfung abgebrochen",
        ":material/report:",
        "Die Prüfung wurde mit einer Meldung abgebrochen — Details stehen im Text. "
        "Ein erneuter Lauf holt die Daten meist neu.",
    )


# ---------------------------------------------------------- Stations-Helfer
# Nutzer-Wunsch 02.10.2026: JEDE Filter-Entscheidung der Pipeline je Signal
# nachvollziehbar — Vollliste je Station, Quelle, Link zum Ursprungssignal,
# Filterleiste (Anzeige/Quelle/Suche), Default „beides anzeigen“.

_STATUS_ICON = {
    "AUSGEWAEHLT": "✅ In der Forensik",
    "FIX": "📌 Fix-ID (immer scannen)",
    "NICHT_IM_SCOPE": "⏭️ Nicht im Teilscan-Scope",
    "OHNE_SLOT": "❌ Kein Forensik-Slot",
    "AUSGESCHLOSSEN": "⛔ Ausschlussliste",
    "DRAUSSEN": "🚫 Vorfilter raus",
    "KANDIDAT": "➡️ Kandidat",
}
_GEWAHLT_STATUS = {"AUSGEWAEHLT", "FIX"}


def _dialog_ergebnisse(settings) -> tuple[list, bool]:
    """Ergebnisse für Stationsdialoge: Sitzungsdaten vor DB-Stand.

    Der DB-Stand wird je Sitzung EINMAL geladen und gecacht — results_from_db
    braucht ~7 s (Forensik-JSONs aller Datensätze), und jede dieser Sekunden
    vergrößert das Rerun-Fenster, in dem Klicks auf die Stationskugeln und
    sogar das Dialog-Schließen hängen bleiben (Live-Befund 08.10.). Frische
    Laufdaten der Sitzung gewinnen immer; nach einem Scan anderer Prozesse
    (z. B. autonomer Sonntagsscan) hilft ein Seiten-Reload.
    """
    if st.session_state.get("scan_results"):
        return list(st.session_state.scan_results), False
    if st.session_state.get("_scan_db_ergebnisse") is None:
        try:
            st.session_state["_scan_db_ergebnisse"] = list(
                pipeline.results_from_db(settings))
        except Exception:
            st.session_state["_scan_db_ergebnisse"] = []
    cache = st.session_state["_scan_db_ergebnisse"]
    return list(cache), bool(cache)


def _signal_link(e: dict) -> str:
    """Echte Signal-URL oder leer. Pelican liefert nur den Plattform-Root —
    das ist kein Signal-Link und wird nicht ausgegeben (keine URLs erfinden).
    Vantage liefert discoverDetail-URLs je Strategie, MQL5 /signals/{id}."""
    url = str(e.get("url") or "").strip()
    quelle = str(e.get("quelle") or e.get("quelle_kuerzel") or "mql5")
    sid = e.get("id")
    if not url and quelle == "mql5" and sid is not None:
        url = f"https://www.mql5.com/en/signals/{sid}"
    if "/signals/" in url or "strategyId=" in url:
        return url
    return ""


def _filterleiste(rows: list[dict], key_suffix: str,
                  label_gewaehlt: str = "Nur gewählt",
                  label_raus: str = "Nur nicht gewählt") -> list[dict]:
    """Filterleiste über den Signaltabellen: Anzeige (Default: alle),
    Quelle (Default: alle) und Freitextsuche nach Name oder ID."""
    c1, c2, c3 = st.columns([1.5, 1.2, 1.8])
    hat_status = any(r.get("_gewaehlt") is not None for r in rows)
    if hat_status:
        anzeige = c1.segmented_control(
            "Anzeige", ["Alle", label_gewaehlt, label_raus],
            default="Alle", key=f"_flt_anzeige_{key_suffix}")
    else:
        anzeige = "Alle"
        c1.caption("Anzeige: alle (keine Auswahlentscheidung in dieser Stufe)")
    quellen = sorted({str(r.get("Quelle")) for r in rows if r.get("Quelle")})
    qsel = c2.multiselect("Quelle", quellen, default=quellen,
                          key=f"_flt_quelle_{key_suffix}",
                          help="Herkunft der Signale — MQL5-Direkt oder eine "
                               "der angeschlossenen Datenquellen (REST).")
    suche = (c3.text_input("Suchen (Name oder ID)",
                           key=f"_flt_suche_{key_suffix}") or "").strip().lower()
    out = rows
    if hat_status and anzeige == label_gewaehlt:
        out = [r for r in out if r["_gewaehlt"]]
    elif hat_status and anzeige == label_raus:
        out = [r for r in out if r["_gewaehlt"] is False]
    erlaubt = set(qsel)
    out = [r for r in out if str(r.get("Quelle")) in erlaubt]
    if suche:
        out = [r for r in out if suche in str(r.get("Signal", "")).lower()
               or suche in str(r.get("ID", "")).lower()]
    return out


def _link_spalte() -> object:
    return st.column_config.LinkColumn("Ursprung", display_text="↗ öffnen")


def _ohne_intern(rows: list[dict]) -> list[dict]:
    """Interne Filter-Marker (_gewaehlt) nicht als Spalte anzeigen."""
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def _begruendung_zeilen(eintraege: list[dict]) -> list[dict]:
    """Begründungs-Einträge (auswahl_begruendung.json) in Tabellen-Zeilen."""
    rows = []
    for e in eintraege:
        status = str(e.get("status") or "KANDIDAT")
        rows.append({
            "Status": _STATUS_ICON.get(status, status),
            "Signal": e.get("name") or f"#{e.get('id')}",
            "ID": e.get("id"),
            "Quelle": e.get("quelle") or "mql5",
            "Wochen": e.get("wochen"),
            "Abos": e.get("abonnenten"),
            "Grund": e.get("grund") or "",
            "Link": _signal_link(e),
            "_gewaehlt": status in _GEWAHLT_STATUS,
        })
    return rows


@st.dialog("Probleme in diesem Lauf", width="large")
def _probleme_dialog(probleme: list, gesamt: int) -> None:
    """Großes Fenster: jedes Problem verständlich erklärt — was passierte, was tun."""
    st.caption(
        f"{len(probleme)} von {gesamt} Signalen konnten nicht vollständig geprüft werden. "
        "Das sind keine Programmabstürze: Der Scanner bricht die Bewertung eines Signals ab, "
        "wenn sich das Risiko nicht belegen lässt — Risiko vor Ertrag, kein Urteil ohne Datenbasis."
    )
    for r in probleme:
        label, icon, hinweis = _problem_art(r)
        with st.container(border=True):
            kopf = st.container(horizontal=True, vertical_alignment="center")
            kopf.markdown(f"**:material/warning: {r.name}** · #{r.id} · {r.platform}")
            with kopf:
                if r.url:
                    st.markdown(f"[Signal auf MQL5 öffnen]({r.url})")
            st.badge(label, icon=icon, color="orange")
            if r.fehler:
                st.markdown(r.fehler)
            else:
                st.markdown("Keine vollständige forensische Prüfung vorhanden — nur Vorprüfung.")
            st.caption(hinweis)


_STATUS_INFO = {
    client_updates.WARTET: ("⚪", "wartet auf Start"),
    client_updates.BEREIT: ("🔵", "bereit — Update wird angestoßen"),
    client_updates.LAEUFT: ("🔵", "läuft"),
    client_updates.LOGIN: ("🟡", "wartet auf Login-Eingabe (Fenster im Client ist offen)"),
    client_updates.FERTIG: ("🟢", "fertig"),
    client_updates.FEHLER: ("🔴", "Fehler"),
    client_updates.TIMEOUT: ("🟡", "Timeout — weiter mit vorhandenem Datenstand"),
    client_updates.OFFLINE: ("🟡", "nicht erreichbar — läuft der Client (startall)?"),
    client_updates.NICHT_UNTERSTUETZT: ("🟡", "Client-Version zu alt (kein Update-Endpoint) — Client aktualisieren"),
    client_updates.ABGEBROCHEN: ("🟡", "abgebrochen (Stop-Button)"),
}


def _client_karte(z: dict, ziel: int) -> None:
    """Eine Status-Karte je Client im Stufe-0-Dialog."""
    emoji, status_text = _STATUS_INFO.get(z.get("status"), ("⚪", str(z.get("status"))))
    with st.container(border=True):
        kopf = st.container(horizontal=True, vertical_alignment="center")
        kopf.markdown(f"{emoji} **{z.get('name')}** · {z.get('base_url', '')}")
        with kopf:
            st.caption(f"{status_text} · geändert {str(z.get('geaendert', ''))[11:]}")
        if z.get("status") == client_updates.LAEUFT and z.get("total"):
            st.progress(min(1.0, (z.get("done") or 0) / max(1, z["total"])),
                        text=f"{z.get('phase') or '…'} — {z.get('done', 0)}/{z['total']}")
        if z.get("detail"):
            st.caption(z["detail"])
        if z.get("fehler"):
            st.error(z["fehler"])
        for hinweis in (z.get("hinweise") or [])[:5]:
            st.caption(f"Hinweis: {hinweis}")
        fakten: list[str] = []
        if z.get("signale_geliefert") is not None:
            fakten.append(f"{z['signale_geliefert']} Signale geliefert "
                          f"(Ziel ≥{ziel})")
        if z.get("katalog_uebersprungen"):
            fakten.append("Katalog übersprungen (3-Tage-Regel)")
        if z.get("tradelisten_neu") is not None or z.get("tradelisten_aktualisiert") is not None:
            fakten.append(f"Tradelisten: {z.get('tradelisten_neu') or 0} neu · "
                          f"{z.get('tradelisten_aktualisiert') or 0} aktualisiert")
        if z.get("datenstand"):
            fakten.append(f"Datenstand {z['datenstand']}")
        if z.get("dauer_s"):
            fakten.append(f"Dauer {z['dauer_s']:.0f} s")
        if fakten:
            st.caption(" · ".join(fakten))


@st.fragment(run_every=2.0, key="stufe0_live_fragment")
def _clients_live_bereich(ziel: int) -> None:
    """Live-Teil des Stufe-0-Dialogs: Zustände aus dem laufenden Worker."""
    live = (st.session_state.get("scan_control") or {}).get("client_updates") or {}
    if not live:
        st.info("Noch kein Stufe-0-Lauf in dieser Sitzung. Die Karten erscheinen, "
                "sobald „Full-Scan“ oder „Teilscan“ gestartet wird.")
        return
    for kuerzel in sorted(live):
        _client_karte(live[kuerzel], ziel)
    st.markdown(f"**Bilanz:** {client_updates.aggregat_text(live)}")


@st.dialog("🔄 Stufe 0 · Clients aktualisieren — Live-Status", width="large")
def _dialog_clients() -> None:
    """Großes Fenster: was Stufe 0 bei jedem Client tut und wie weit er ist."""
    settings = config.load_settings()
    st.markdown(
        "**Was passiert hier?** Vor dem eigentlichen Workflow stößt der Scanner "
        "per REST bei jedem angeschlossenen Client den Daten-Download an "
        "(Signale, Abonnenten, Tradelisten) und wartet auf deren „fertig“. "
        "Erst dann startet Station 1 — der Scan arbeitet also mit aktuellem "
        "Datenstand. Stufe 0 bewertet nichts; sie beschafft nur Daten.")
    ziel = int(settings.get("update_ziel_signale") or 200)
    _clients_live_bereich(ziel)
    st.markdown("---")
    st.markdown("**Letzte Läufe (Chronik je Client)**")
    chronik = db.list_client_updates(limit=12)
    if chronik:
        import pandas as pd
        st.dataframe(pd.DataFrame([{
            "Zeit": e.get("ts"), "Client": e.get("kuerzel"),
            "Status": e.get("status"), "Signale": e.get("signale_geliefert"),
            "Tradelisten neu": e.get("tradelisten_neu"),
            "Datenstand": e.get("datenstand"),
            "Dauer s": e.get("dauer_s"), "Fehler": e.get("fehler") or "",
        } for e in chronik]), width="stretch", hide_index=True)
    else:
        st.caption("Noch keine Einträge — Chronik füllt sich mit dem ersten Stufe-0-Lauf.")
    st.caption("Regeln: Ziel ≥200 Signale mit Abonnenten je Client (Versuch genügt — "
               "MqlDownloader meldet real ~50). Katalog-Load jünger als "
               f"{settings.get('update_katalog_max_alter_h', 72)} h wird übersprungen "
               "(3-Tage-Regel); Tradelisten laufen immer als Delta. Login: Pelican "
               "füllt sich automatisch; scheitert das, wartet Stufe 0 auf deine "
               "Eingabe im Client-Fenster.")


@st.dialog("📡 Station 1 · Signale holen — was kam rein?", width="large")
def _dialog_listen() -> None:
    """Signale je Quelle: was der Crawl geliefert hat und was fehlte."""
    settings = config.load_settings()
    import pandas as pd
    from collections import Counter as _C
    st.markdown("**Was passiert hier?** Der Scanner lädt die Signalkataloge aus den "
                "eingestellten Quellen. Bei MQL5 werden Top-Listen und fehlende Fix-IDs "
                "abgerufen, bei REST-Quellen deren Kataloge. Die Handelsdaten für die "
                "Risikoprüfung folgen in Station 3. Ein geladenes Signal ist noch keine Empfehlung.")
    datei = config.DATA_DIR / "auswahl_begruendung.json"
    daten = {}
    if datei.exists():
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            st.warning(f"Die gespeicherte Auswahl kann nicht gelesen werden: {exc}")
    # B13 (Lauf-Review 02.10.): Während eines laufenden Workflows hat
    # Station 1 die FRISCHE Liste in control['signals'] geschrieben — die
    # alte Session-Liste (scan_signals) würde den vorigen Stand zeigen.
    # Lauf-Daten gehen vor, danach Session, dann gespeicherter Lauf.
    eintraege = list((st.session_state.get("scan_control") or {}).get("signals")
                     or st.session_state.get("scan_signals") or [])
    sitzungsdaten = bool(eintraege)
    if eintraege:
        st.caption("Signale aus dem Lauf in dieser Sitzung.")
    else:
        eintraege = daten.get("eintraege") or []
        if daten:
            st.caption(f"Gespeicherter Lauf: {daten.get('zeitstempel', '?')}.")
        else:
            st.info("Noch keine Signale geladen. Die Tabelle zeigt die konfigurierten "
                    "Quellen; Signalzahlen erscheinen nach Station 1.")
    def _herkunft(e):
        kuerzel = e.get("quelle_kuerzel") or e.get("quelle") or "mql5"
        if sitzungsdaten:
            zugriff = "REST" if e.get("quelle_kuerzel") or e.get("quelle_id") or e.get("quelle") else "MQL5-Direkt"
        else:
            zugriff = "REST" if kuerzel != "mql5" else "Nicht aufgezeichnet"
        return kuerzel, zugriff

    quellen = _C(_herkunft(e) for e in eintraege)
    konfigurierte = {q["kuerzel"]: q for q in db.list_quellen()}
    modus = str(settings.get("listen_modus") or "mql5").strip().lower()
    mql5_nicht_getrennt = bool(quellen.get(("mql5", "Nicht aufgezeichnet")))
    rows = [{"Quelle": "MQL5-Direkt", "Kürzel": "mql5", "Zugriff": "MQL5-Direkt",
             "Im Scan aktiv": "Ja" if modus in ("mql5", "beides") else "Nein",
             "Geladene Signale": (quellen.get(("mql5", "MQL5-Direkt"), 0)
                                  if eintraege and not mql5_nicht_getrennt else None),
             "Letzter Verbindungstest": "—", "Geprüft am": "—"}]
    rest_kuerzel = {k for k, zugriff in quellen if zugriff == "REST"}
    for kuerzel in sorted(set(konfigurierte) | rest_kuerzel):
        q = konfigurierte.get(kuerzel) or {}
        pruefung = q.get("letzte_pruefung") or {}
        im_scan = bool(q.get("aktiv")) and modus in ("quellen", "beides")
        zahl = quellen.get((kuerzel, "REST"), 0) if eintraege else None
        if kuerzel == "mql5" and mql5_nicht_getrennt:
            zahl = None
        rows.append({"Quelle": q.get("name") or kuerzel, "Kürzel": kuerzel,
                     "Zugriff": "REST",
                     "Im Scan aktiv": "Ja" if im_scan else "Nein",
                     "Geladene Signale": zahl,
                     "Letzter Verbindungstest": {
                         "ok": "Erreichbar", "eingeschraenkt": "Eingeschränkt",
                         "fehler": "Nicht erreichbar",
                     }.get(pruefung.get("status"), pruefung.get("text") or "Nicht geprüft"),
                     "Geprüft am": pruefung.get("geprueft") or "—"})
    quellen_tabelle = pd.DataFrame(rows, columns=["Quelle", "Kürzel", "Zugriff", "Im Scan aktiv",
                 "Geladene Signale", "Letzter Verbindungstest", "Geprüft am"])
    quellen_tabelle["Geladene Signale"] = pd.array(quellen_tabelle["Geladene Signale"], dtype="Int64")
    st.dataframe(quellen_tabelle, width="stretch", hide_index=True)
    st.caption("Die Tabelle verwendet gespeicherte Verbindungstests. "
               "Aktivierung zeigt die aktuellen Einstellungen.")
    if mql5_nicht_getrennt:
        st.caption(f"Die gespeicherte Auswahl enthält {quellen[('mql5', 'Nicht aufgezeichnet')]} "
                   "Signale mit Kürzel mql5. MQL5-Direkt und MqlDownloader wurden dort "
                   "nicht getrennt aufgezeichnet; ihre einzelnen Signalzahlen sind unbekannt.")
    if eintraege:
        zeilen = []
        for e in eintraege:
            kuerzel, zugriff = _herkunft(e)
            zeilen.append({
                "Signal": e.get("name", ""), "ID": e.get("id"),
                "Quelle": kuerzel, "Zugriff": zugriff,
                "Wochen": e.get("wochen"), "Abos": e.get("abonnenten"),
                "Link": _signal_link(e)})
        st.caption(f"**Alle {len(zeilen)} geladenen Signale** — Herkunft je "
                   "Signal; über die Filter lässt sich je Quelle einschränken.")
        zeilen = _filterleiste(zeilen, "listen")
        st.dataframe(zeilen, width="stretch", hide_index=True,
                     column_config={"Link": _link_spalte()})
        st.caption("Pelican-Signale haben keinen klickbaren Ursprungs-Link — "
                   "die Plattform liefert keine Signal-URL (nur die Startseite); "
                   "MQL5- und Vantage-Signale verlinken auf ihre Detailseite.")
    st.caption("Nicht erreichbare Kataloge stehen im Meldungs-Feed. Im Teilscan "
               "können gespeicherte 🟢/🟡-Signale aus der DB ergänzt werden.")


@st.dialog("🔍 Station 2 · Auswahl — warum jedes Signal drin oder draußen ist", width="large")
def _dialog_auswahl() -> None:
    """EINE scrollbare Tabelle: ALLE Signale des Laufs mit Grund je Signal,
    Filterleiste (Anzeige/Quelle/Suche) — Nutzer-Wunsch 02.10."""
    settings = config.load_settings()
    st.markdown("**Was passiert hier?** Drei Filter hintereinander: "
                "(1) der **Vorfilter** prüft Mindestalter und Mindest-"
                "Abonnentenzahl, (2) der **Scan-Modus** entscheidet den Scope — "
                "im Teilscan werden nur aktuell 🟢/🟡 laut Datenbank plus "
                "Fix-IDs geprüft, im Full-Scan alle Kandidaten — und (3) die "
                "**Slots**: je Quelle kommen die abonnentenstärksten Kandidaten "
                "in die Forensik (Fix-IDs umgehen alles und belegen keinen "
                "Slot). Für jedes Signal steht der Grund in der Tabelle.")
    datei = config.DATA_DIR / "auswahl_begruendung.json"
    if not datei.exists():
        st.info("Noch keine Auswahl aufgezeichnet. Nach dem Scan zeigt die "
                "Tabelle für jedes Signal, warum es ausgewählt oder "
                "aussortiert wurde.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        st.warning(f"Die gespeicherte Auswahl kann nicht gelesen werden: {exc}")
        return
    eintraege = daten.get("eintraege") or []
    if not eintraege:
        st.info("Die gespeicherte Auswahl ist leer.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    # Filter-Kette als Zahlen — jede Zeile der Tabelle erklärt den Sprung.
    n_gesamt = len(eintraege)
    n_draussen = sum(1 for e in eintraege if e.get("status") == "DRAUSSEN")
    n_kandidaten = sum(1 for e in eintraege
                       if e.get("status") != "DRAUSSEN")
    n_gewaehlt = sum(1 for e in eintraege
                     if e.get("status") in _GEWAHLT_STATUS)
    modus = daten.get("modus") or "—"
    st.caption(f"Stand: {daten.get('zeitstempel', '?')} · Modus: {modus} · "
               f"mindestens {settings['min_wochen']} Wochen, "
               f"{settings['min_abonnenten']} Abonnenten, "
               f"Top {daten.get('top_n_export', '?')} je Quelle. "
               "Abonnentenzahl ist kein Qualitätsnachweis.")
    st.markdown(f"**Filter-Kette:** {n_gesamt} Signale geladen "
                f"→ {n_draussen} fielen durch den **Vorfilter** "
                f"→ {n_kandidaten} Kandidaten → {n_gewaehlt} kamen in die "
                "**Forensik** (Modus-Scope + Slots).")
    zeilen = _begruendung_zeilen(eintraege)
    zeilen = _filterleiste(zeilen, "auswahl")
    st.caption(f"Angezeigt: {len(zeilen)} von {n_gesamt} Signalen.")
    st.dataframe(_ohne_intern(zeilen), width="stretch", hide_index=True,
                 column_config={"Link": _link_spalte()})
    st.caption("Status-Bedeutung: ✅ geprüft · 📌 Fix-ID (immer scannen) · "
               "⏭️ im Teilscan nicht dran (letztes Urteil nicht 🟢/🟡) · "
               "❌ Kandidat, aber hinter den Top-N-Slots je Quelle · "
               "⛔ Ausschlussliste (kuratiert, belegt keinen Slot) · "
               "🚫 Vorfilter (Alter/Abonnenten). Pelican-Signale ohne "
               "Ursprungs-Link: Plattform liefert keine Signal-URL.")


@st.dialog("🔬 Station 3 · Prüfen & speichern — Forensik-Ergebnisse", width="large")
def _dialog_forensik() -> None:
    """Kombinierte Sicht: alle Kandidaten des Laufs — wer geprüft wurde
    (mit Ergebnis) und wer nicht (mit Grund), Filterleiste oben."""
    settings = config.load_settings()
    import pandas as pd
    st.markdown("**Was passiert hier?** Für die ausgewählten Signale lädt der "
                "Scanner Handelsdaten (Export bzw. Quellen-Artefakte) und "
                "prüft Martingale, gleichzeitig offene Positionen, Exposure, "
                "Stop-Signaturen und Drawdown. Der Code berechnet Kennzahlen, "
                f"Ampel und Score. Die Drawdown-Schranke liegt bei "
                f"{settings.get('schranke_eq_dd_pct', 30):g} %. "
                "Fehlender Stop-Nachweis ist neutral.")
    results, aus_db = _dialog_ergebnisse(settings)
    if aus_db:
        st.caption("Kein Lauf in dieser Sitzung — angezeigt ist der letzte "
                   "gespeicherte Datenbank-Stand (kann älter sein als der "
                   "letzte Lauf).")
    res_map = {r.id: r for r in results}
    datei = config.DATA_DIR / "auswahl_begruendung.json"
    eintraege: list[dict] = []
    if datei.exists():
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
            eintraege = [e for e in (daten.get("eintraege") or [])
                         if e.get("status") != "DRAUSSEN"]
            if daten:
                st.caption(f"Auswahl-Stand: {daten.get('zeitstempel', '?')}"
                           + (f" · Modus {daten.get('modus')}" if daten.get("modus") else ""))
        except (OSError, ValueError):
            eintraege = []
    if not eintraege and not results:
        st.info("Noch keine Kandidaten und kein Lauf-Ergebnis. Nach einem Scan "
                "steht hier für jedes Signal, ob es geprüft wurde — und das "
                "Ergebnis.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    zeilen = []
    for e in eintraege:
        status = str(e.get("status") or "KANDIDAT")
        r = res_map.get(e.get("id"))
        if r is not None:
            r.refresh_efficiency()
        geprueft = r is not None and r.forensik_vorhanden
        zeilen.append({
            "Geprüft": "✓ ja" if geprueft else "— nein",
            "Signal": e.get("name") or f"#{e.get('id')}",
            "ID": e.get("id"),
            "Quelle": e.get("quelle") or "mql5",
            "Ampel": (r.ampel if r else None),
            "Score": (r.score if geprueft else None),
            "Max-Drawdown % (Equity)": (r.max_drawdown_equity_pct if geprueft else None),
            "Trading-DD % (geschlossen)": (r.trading_dd_pct if geprueft else None),
            "Equity-Messung": (r.equity_messung_status if r else "Noch nicht geprüft"),
            "Gewinn %/Monat": (getattr(r, "ertrag_monat_geom_pct", None)
                         if geprueft else None),
            "TrueRetDD": (r.true_retdd_monat if geprueft else None),
            "TrueRetDD (Vorbehalt)": (getattr(r, "retdd_monat_vorbehalt", None)
                                      if geprueft else None),
            "Grund": (e.get("grund") or "")
                     + ((" · ⚠ " + (r.fehler or "")[:90]) if r and r.fehler else ""),
            "Link": _signal_link(e),
            "_gewaehlt": geprueft,
        })
    # Ergebnisse ohne Eintrag in der Begründungsliste (z. B. ältere DB-Zeilen
    # ohne Lauf in der Datei) dürfen nicht still verschwinden.
    bekannte = {z["ID"] for z in zeilen}
    for r in results:
        if r.id in bekannte or not r.forensik_vorhanden:
            continue
        r.refresh_efficiency()
        zeilen.append({
            "Geprüft": "✓ ja", "Signal": r.name, "ID": r.id,
            "Quelle": r.quelle or "mql5", "Ampel": r.ampel, "Score": r.score,
            "Max-Drawdown % (Equity)": r.max_drawdown_equity_pct,
            "Trading-DD % (geschlossen)": r.trading_dd_pct,
            "Equity-Messung": r.equity_messung_status,
            "Gewinn %/Monat": getattr(r, "ertrag_monat_geom_pct", None),
            "TrueRetDD": r.true_retdd_monat,
            "TrueRetDD (Vorbehalt)": getattr(r, "retdd_monat_vorbehalt", None),
            "Grund": "Aus dem Datenbank-Stand (kein Eintrag in der gespeicherten "
                     "Auswahl dieses Laufs).",
            "Link": _signal_link({"url": r.url, "id": r.id,
                                  "quelle": r.quelle or "mql5"}),
            "_gewaehlt": True})
    if eintraege:
        n_da = sum(1 for z in zeilen if z["_gewaehlt"])
        st.caption(f"**{len(zeilen)} Kandidaten im Lauf — {n_da} geprüft, "
                   f"{len(zeilen) - n_da} nicht geprüft** (Grund je Signal "
                   "in der Tabelle).")
    n_gesamt = len(zeilen)
    zeilen = _filterleiste(zeilen, "forensik",
                           label_gewaehlt="Nur geprüft",
                           label_raus="Nur nicht geprüft")
    st.caption(f"Angezeigt: {len(zeilen)} von {n_gesamt} Kandidaten.")
    # TrueRetDD mit Vorbehalt-Markierung wie die Ergebnistabelle: belastbar
    # normal, vorbehaltlich orange (Review 05.10. abends, Befund 2 — vorher
    # stand der Wert hier nackig ohne Kennzeichnung da).
    forensik_df = pd.DataFrame(_ohne_intern(zeilen))
    forensik_styled = forensik_df.style
    if {"TrueRetDD", "TrueRetDD (Vorbehalt)"} <= set(forensik_df.columns):
        def _trueretdd_stil(z):
            if pd.isna(z["TrueRetDD (Vorbehalt)"]):
                return ["", ""]
            return ["background-color: rgba(249,115,22,0.12); color: #fb923c", ""]
        forensik_styled = forensik_styled.apply(
            _trueretdd_stil, axis=1, subset=["TrueRetDD", "TrueRetDD (Vorbehalt)"])
    st.dataframe(forensik_styled, width="stretch", hide_index=True,
                 column_config={"Link": _link_spalte()})
    st.caption("Max-Drawdown (Equity) enthält offene Gewinne und Verluste "
               "aus belastbaren Kurs- oder Monitor-Messungen; ohne diese "
               "bleibt das Feld leer. Trading-DD berücksichtigt nur "
               "geschlossene Trades. Die Schranke verwendet zusätzlich "
               "die Plattform-Angaben. Gewinn %/Monat ist die eigene geometrische "
               "Monatsrendite; TrueRetDD ist der Jahres-Calmar (CAGR ÷ "
               "gemessener maximaler Equity-Drawdown inkl. Floating; "
               "Grün-Gate ab 3,0). Geschlossener Drawdown dient nie als "
               "Nenner.")
    probleme = [r for r in results if r.fehler]
    if probleme:
        st.warning(f"{len(probleme)} Signal(e) mit Fehler — Details auf der "
                   "Ergebnisseite unter „Probleme in diesem Lauf“.")


@st.dialog("🧠 Station 4 · KI-Berichte", width="large")
def _dialog_llm() -> None:
    """KI-Berichte: welche Signale bekamen Berichte und wie ausführlich."""
    settings = config.load_settings()
    import pandas as pd
    st.markdown("**Was passiert hier?** Die optionalen KI-Schritte beschreiben "
                "Strategie und Risiko anhand der Trades und berechneten Befunde "
                "und erstellen einen Gesamtbericht. Die Tabelle zeigt, welche "
                "Berichte für jedes Signal vorliegen.")
    results, _aus_db = _dialog_ergebnisse(settings)
    if _aus_db:
        st.caption("Kein Lauf in dieser Sitzung — angezeigt ist der "
                   "letzte gespeicherte Datenbank-Stand.")
    if not results:
        st.info("Noch kein Lauf-Ergebnis in dieser Sitzung. Berichte erscheinen "
                "nach Station 4, sofern KI-Berichte eingeschaltet sind.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    data = [{"Signal": r.name, "Quelle": r.quelle or "mql5", "Ampel": r.ampel,
             "Trade-Analyse": "✓" if getattr(r, "trade_analyse", "") else "—",
             "Risiko-Analyse": "✓" if getattr(r, "risiko_analyse", "") else "—",
             "Gesamtbericht": "✓" if getattr(r, "gesamtbericht", "") else "—",
             "Kurzfassung": (getattr(r, "kurzfassung", "") or "")[:120],
             "Link": _signal_link({"url": r.url, "id": r.id,
                                   "quelle": r.quelle or "mql5"}),
             "_gewaehlt": bool(getattr(r, "gesamtbericht", ""))}
            for r in results]
    data = _filterleiste(data, "llm", label_gewaehlt="Nur mit Bericht",
                         label_raus="Nur ohne Bericht")
    st.dataframe(_ohne_intern(data), width="stretch", hide_index=True,
                 column_config={"Link": _link_spalte()})
    st.caption("Nur 🟢/🟡 erhalten das volle KI-Paket (Design-Regel: Budget sparen).")


@st.dialog("🥧 Station 5 · Portfolio", width="large")
def _dialog_portfolio() -> None:
    """Portfolio-Vorschlag: Empfehlung und Statistik-Deutung."""
    settings = config.load_settings()
    st.markdown("**Was passiert hier?** Die KI führt die Berichte der 🟢/🟡-Signale "
                "zusammen. Code-Befunde zu gemeinsamen Verlustmonaten, "
                "Historienlänge und Instrument-Überschneidungen helfen, "
                "Kombinationen und Klumpenrisiken einzuschätzen. Historische "
                "Diversifikation ist keine Prognose.")
    st.dataframe([
        {"Prüfung": "Gemeinsame Verluste", "Grundlage": "Monate mit mehreren gleichzeitig verlierenden Signalen"},
        {"Prüfung": "Beobachtungsfenster", "Grundlage": "Historienlänge je Signal und gemeinsamer Zeitraum"},
        {"Prüfung": "Klumpenrisiko", "Grundlage": "Gemeinsame Instrumente und Rendite-Risiko-Effizienz"},
    ], width="stretch", hide_index=True)
    p = st.session_state.get("portfolio_result") or {}
    text = p.get("text") or st.session_state.get("portfolio_bericht") or ""
    if not text:
        st.info("Noch kein Portfolio in diesem Lauf — läuft nach dem letzten KI-Bericht.")
        return
    st.markdown(text[:8000])
    if len(text) > 8000:
        st.caption("… (gekürzt — vollständiger Bericht auf der Ergebnisseite)")
    # Welche Signale in die Portfolio-Bewertung eingeflossen sind (Nutzer-
    # Wunsch 02.10.: Herkunft je Signal sichtbar + Link zum Ursprung).
    ergebnisse, _aus_db = _dialog_ergebnisse(settings)
    basis = [r for r in ergebnisse if r.ampel in ("🟢", "🟡")]
    if basis:
        for r in basis:
            r.refresh_efficiency()
        st.caption("Eingeflossen sind die 🟢/🟡-Signale des Laufs (Datenbasis "
                   "der KI-Zusammenfassung):")
        # TrueRetDD mit Vorbehalt-Markierung wie die Ergebnistabelle
        # (Review 05.10. abends, Befund 2).
        import pandas as pd
        basis_df = pd.DataFrame([{
            "Signal": r.name, "Quelle": r.quelle or "mql5",
            "Ampel": r.ampel, "Ertrag/M (geom.)":
            getattr(r, "ertrag_monat_geom_pct", None),
            "TrueRetDD": r.true_retdd_monat,
            "TrueRetDD (Vorbehalt)": getattr(r, "retdd_monat_vorbehalt", None),
            "Link": _signal_link({"url": r.url, "id": r.id,
                                  "quelle": r.quelle or "mql5"})}
            for r in basis])
        basis_styled = basis_df.style
        if {"TrueRetDD", "TrueRetDD (Vorbehalt)"} <= set(basis_df.columns):
            def _trueretdd_stil_basis(z):
                if pd.isna(z["TrueRetDD (Vorbehalt)"]):
                    return ["", ""]
                return ["background-color: rgba(249,115,22,0.12); "
                        "color: #fb923c", ""]
            basis_styled = basis_styled.apply(
                _trueretdd_stil_basis, axis=1,
                subset=["TrueRetDD", "TrueRetDD (Vorbehalt)"])
        st.dataframe(basis_styled, width="stretch", hide_index=True,
                     column_config={"Link": _link_spalte()})


@st.dialog("🔄 Station 6 · Abgleich", width="large")
def _dialog_downloader() -> None:
    """Downloader-Abgleich: was gespiegelt wurde."""
    settings = config.load_settings()
    import pandas as pd
    st.markdown("**Was passiert hier?** Der Abgleich lädt Abonnenten-Verläufe "
                "und vorhandene Testreport-PDFs aus den aktiven Datenquellen. "
                "Bereits vorhandene Dateien werden anhand ihres Inhalts erkannt. "
                "Ein Teilausfall wird protokolliert; die Bewertung der Signale "
                "ändert sich durch diesen Schritt nicht.")
    step = (st.session_state.get("scan_workflow") or {}).get("steps", {}).get("downloader") or {}
    st.dataframe([
        {"Eintrag": "Status", "Wert": STATES.get(step.get("status"), ("Noch nicht gestartet",))[0]},
        {"Eintrag": "Fortschritt", "Wert": f"{step.get('done', 0)} von {step.get('total') or '—'} Signalen"},
        {"Eintrag": "Befund", "Wert": step.get("detail") or "Noch nicht gestartet"},
    ], width="stretch", hide_index=True)
    log = list((st.session_state.get("scan_logs") or {}).get("downloader") or [])
    if log:
        st.dataframe(pd.DataFrame({"Abgleich-Protokoll": log}), width="stretch", hide_index=True)
    else:
        st.info("Noch kein Abgleich-Protokoll in dieser Sitzung. Nach Station 6 "
                "erscheinen hier die geladenen Daten und Hinweise.")
    st.caption("Die gespeicherten Abonnenten-Verläufe und PDFs sind auf der Ergebnisseite erreichbar.")


_station_dialoge = {
    "clients": _dialog_clients,
    "listen": _dialog_listen, "kandidaten": _dialog_auswahl,
    "forensik": _dialog_forensik, "llm": _dialog_llm,
    "portfolio": _dialog_portfolio, "downloader": _dialog_downloader,
}


@st.fragment(key="scan_station_dialog_host")
def _station_dialog_host() -> None:
    """Dialog-Lebensdauer unabhängig vom sekündlichen Status-Fragment.

    Der Stations-Callback rerunnt nur diesen Host; st.dialog übernimmt
    anschließend die Reruns seiner Filter. Der Trigger wird einmal verbraucht.
    """
    station = st.session_state.pop("_scan_station_dialog", None)
    if station is None:
        station = (st.query_params.get("station") or "").strip()
    if "station" in st.query_params:
        del st.query_params["station"]
    if station in _station_dialoge:
        _station_dialoge[station]()


def registriere_station_host() -> None:
    """Den Dialog-Host in jedem App-Lauf anmelden (scan.py ruft das auf).

    Nach den Dialogdefinitionen ausgeführt, damit der Host als Ziel für
    Stationsklicks verfügbar ist. Alte Stations-URLs bleiben gültig.
    """
    _station_dialog_host()
