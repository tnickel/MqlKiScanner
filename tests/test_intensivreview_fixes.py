# -*- coding: utf-8 -*-
"""Tests der Fixes aus dem Intensiv-Review 29./30.09.2026
(doc/reviews/intensivreview_2026-09-29/review.md, Befunde B1-B16).

B1: Monitor-EQ-DD als fünftes Schranken-Maximum (Lemonal 🟢 bei 46,65 % war
    der Ziellauf-Befund).
B2: Ertrag/Monat maßgeblich auf der Forensik-Kapitalbasis.
B3: Implizite Kapitalbasis (Web-Balance − Σ Trade-Netto) vor der virtuellen
    10k-Annahme.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mqlkiscanner import pipeline, scoring


# ----------------------------------------------------------------- B1-Schranke

def _report(trading_dd_pct=4.57):
    return {"forensics": {"drawdown": {"trading_dd": {
        "dd_pct": trading_dd_pct, "dd_pct_max_rel": trading_dd_pct,
        "dd_usd": 100.0}}}}

def _platform(**kw):
    basis = {"eq_dd_pct": 3.8, "bal_dd_pct": 8.11, "reko_eq_dd_pct": 0.0,
             "monitor_trade_eq_dd_pct": 0.0}
    basis.update(kw)
    return basis


def test_b1_monitor_wert_reisst_die_schranke():
    ev = scoring.evaluate(_report(trading_dd_pct=2.37),
                          _platform(eq_dd_pct=8.56,
                                    monitor_trade_eq_dd_pct=46.65))
    assert ev["schranke_eq_dd_verletzt"] is True
    assert ev["schranke_dd_pct"] == 46.65


def test_b1_monitor_wert_unter_schranke_unveraendert():
    ev = scoring.evaluate(_report(), _platform(monitor_trade_eq_dd_pct=6.19))
    assert ev["schranke_eq_dd_verletzt"] is False
    assert ev["schranke_dd_pct"] == 8.11  # By-Balance bleibt führend


def test_b1_monitor_wert_in_der_score_dimension():
    """Die DD-Score-Dimension muss dasselbe Maximum sehen wie die Schranke
    (F-12-Muster): Monitor 46,65 % muss die Dimension hochtreiben."""
    dims = scoring.dimension_inputs(_report(trading_dd_pct=2.37),
                                    _platform(eq_dd_pct=8.56,
                                              monitor_trade_eq_dd_pct=46.65))
    assert dims["drawdown"] >= 9.0  # 46,65 % liegt in der obersten Stufe


def test_b1_monitor_gilt_auch_mit_eq_dd_caveat():
    """eq_dd_caveat (KiraCat-Fußnote) wirft nur die Plattform-DDs raus —
    die Monitor-Zweitmessung bleibt ein hartes Maximum."""
    ev = scoring.evaluate(_report(trading_dd_pct=5.0),
                          _platform(eq_dd_caveat=True, eq_dd_pct=40.0,
                                    monitor_trade_eq_dd_pct=35.0))
    assert ev["schranke_eq_dd_verletzt"] is True
    assert ev["schranke_dd_pct"] == 35.0


def test_b1_ampel_gruen_bei_monitor_ueber_schranke_ist_unmoeglich():
    """Ende-zu-Ende auf ampel_for: 🟢 verlangt eine uneingeschränkte
    Schranke — 46,65 % Monitor-Zweitmessung muss 🔴 liefern."""
    res = pipeline.ScanResult(
        id=2063644, name="Lemonal-Fall", dd_equity_pct=8.56,
        trading_dd_pct=2.37, martingale_flag=False, stop_evidence="none",
        ertrag_monat_pct=248.49, ertrag_monat_pct_forensik=12.55,
        score=4.9, forensik_vorhanden=True,
        monitor_trade_eq_dd_pct=46.65, schranke_verletzt=True)
    ampel, grund = pipeline.ampel_for(res, {"schranke_eq_dd_pct": 30})
    assert ampel == "🔴"
    assert "Schranke verletzt" in grund


def test_b1_refresh_berechnet_dieselbe_schranke_wie_der_scan():
    """refresh_report_verdict (DB-Load/Anzeige) darf die Schranke nicht
    schwächer sehen als scoring.evaluate zur Scan-Zeit."""
    res = pipeline.ScanResult(
        id=1, name="X", dd_equity_pct=8.56, trading_dd_pct=2.37,
        monitor_trade_eq_dd_pct=46.65, forensik_vorhanden=True)
    pipeline.refresh_report_verdict(res, {})
    assert res.schranke_verletzt is True


# ------------------------------------------------------- B2 Ertrag Forensik

def test_b2_gruen_braucht_forensik_ertrag():
    """ampel_for: Plattform 6,46 %/Monat, Forensik-Kurve 0,5 %/Monat →
    KEIN Grün mehr (Fall SafeGold)."""
    res = pipeline.ScanResult(
        id=2048285, name="SafeGold-Fall", score=4.5, forensik_vorhanden=True,
        ertrag_monat_pct=6.46, ertrag_monat_pct_forensik=0.5,
        martingale_flag=False, stop_evidence="none")
    ampel, grund = pipeline.ampel_for(res, {})
    assert ampel == "🟡"
    assert "Ertrag" in grund


def test_b2_forensik_ertrag_ueber_schwelle_bleibt_gruen():
    res = pipeline.ScanResult(
        id=2349227, name="Gold-Spike-Fall", score=4.1,
        forensik_vorhanden=True, ertrag_monat_pct=24.54,
        ertrag_monat_pct_forensik=8.6, martingale_flag=False,
        stop_evidence="direct")
    ampel, _ = pipeline.ampel_for(res, {})
    assert ampel == "🟢"


def test_b2_ohne_forensikwert_gilt_weiterhin_der_plattformwert():
    res = pipeline.ScanResult(
        id=1, name="Vorpruefung", score=4.0, forensik_vorhanden=True,
        ertrag_monat_pct=7.0, ertrag_monat_pct_forensik=None,
        martingale_flag=False, stop_evidence="none")
    ampel, _ = pipeline.ampel_for(res, {})
    assert ampel == "🟢"


# --------------------------------------------------- B3 implizite Kapitalbasis

def test_b3_implizite_basis_bevorzugt_vor_virtual(tmp_path, monkeypatch):
    """Web-Balance 998 USD, Trade-Netto +568 USD → implizite Basis 430 USD
    statt starrer 10.000 (Fall SafeGold; DD-% danach ~10× höher)."""
    csv_pfad = tmp_path / "trades.csv"
    csv_pfad.write_text(
        "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        "2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0.10;2026.01.05 12:00:00;"
        "4050.00;0;0;500.00\n"
        "2026.02.05 10:00:00;Buy;0.10;XAUUSD;4010.00;0.10;2026.02.05 12:00:00;"
        "4078.00;0;0;68.00\n",
        encoding="utf-8")
    wert = pipeline._implizite_kapitalbasis(998.0, str(csv_pfad))
    assert wert == pytest.approx(430.0)


def test_b3_implizite_basis_nicht_positive_ergibt_none(tmp_path):
    csv_pfad = tmp_path / "trades.csv"
    csv_pfad.write_text(
        "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        "2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0.10;2026.01.05 12:00:00;"
        "4200.00;0;0;2000.00\n",
        encoding="utf-8")
    # Balance 1000 − Netto 2000 = −1000 → kein positiver Start → None
    assert pipeline._implizite_kapitalbasis(1000.0, str(csv_pfad)) is None


def test_b3_implizite_basis_ohne_balance_ergibt_none(tmp_path):
    csv_pfad = tmp_path / "trades.csv"
    csv_pfad.write_text("Time;Type\n", encoding="utf-8")
    assert pipeline._implizite_kapitalbasis(None, str(csv_pfad)) is None
    assert pipeline._implizite_kapitalbasis(0.0, str(csv_pfad)) is None


def test_b3_urteil_kennzeichnet_implizite_basis():
    res = pipeline.ScanResult(
        id=1, name="X", forensik_vorhanden=True, score=4.0,
        kapitalbasis_verwendet_quelle=pipeline.KAPITALBASIS_QUELLE_IMPLIZIT,
        ertrag_monat_pct=6.0, martingale_flag=False, stop_evidence="none")
    pipeline.refresh_report_verdict(res, {})
    assert "Kapitalbasis implizit" in res.urteil


# ------------------------------------------------------------------ B4 Betreuer

def test_b4_betreuer_nimmt_nur_mql5_und_zaehlt_quellen(monkeypatch):
    from mqlkiscanner.agenten import betreuer
    class R:
        def __init__(self, sid, ampel, quelle):
            self.id, self.ampel, self.quelle = sid, ampel, quelle
            self.name, self.platform = f"S{sid}", "MT5"
            self.forensik_vorhanden = True
    monkeypatch.setattr(
        "mqlkiscanner.pipeline.results_from_db",
        lambda settings=None: [R(1, "🟢", "mql5"), R(2, "🟡", "pelik"),
                               R(3, "🔴", "mql5"), R(4, "🟢", "pelik")])
    kands, uebersprungen = betreuer.mql5_kandidaten({})
    assert [k["id"] for k in kands] == [1]
    assert uebersprungen == 2


# ---------------------------------------------------------------- B6 Parser etc.

def _schreibe_csv(tmp_path, zeilen):
    p = tmp_path / "t.csv"
    p.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return str(p)

KOPF13 = ("Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;"
          "Swap;Profit;Comment")


def test_b6_correction_ist_kontobewegung(tmp_path):
    from mqlkiscanner import parser
    p = _schreibe_csv(tmp_path, [
        KOPF13,
        "2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0;0;2026.01.05 12:00:00;"
        "4050.00;0;0;500.00;",
        "2026.01.06 09:00:00;Correction;;;; ; ; ; ; ; ;-25.00;broker-korrektur"])
    exp = parser.load_export(p)
    assert len(exp.trades) == 1
    assert len(exp.balances) == 1 and exp.balances[0].amount == -25.0


def test_b6_abgeschnittene_letztdatenzeile_bleibt_invalid_mit_hinweis(tmp_path):
    """B6-Entscheidung: Eine unvollständige LETZTE Datenzeile (Beleg 840474)
    ist ein abgebrochener Download — sie bleibt ein LAUTER FEHLER (Cache-
    Poisoning-Abwehr eines früheren Reviews: ein halber Download darf nie
    wie eine vollständige Historie aussehen). Neu ist der Diagnose-Hinweis
    im Fehlertext, der die wahrscheinliche Ursache nennt."""
    from mqlkiscanner import parser
    # Variante A: zu wenige Spalten am Dateiende
    p = _schreibe_csv(tmp_path, [
        KOPF13,
        "2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0;0;2026.01.05 12:00:00;"
        "4050.00;0;0;500.00;",
        "2026.01.06 09:00:00;Sell;0.10;XAUUSD;4100.00;0;0;2026.01.06 1"])
    with pytest.raises(ValueError, match="Download vermutlich unvollständig"):
        parser.load_export(p)
    # Variante B: volle Breite, Pflichtfeld leer am Ende
    p2 = _schreibe_csv(tmp_path, [
        KOPF13,
        "2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0;0;2026.01.05 12:00:00;"
        "4050.00;0;0;500.00;",
        "2026.01.06 09:00:00;Sell;0.10;XAUUSD;4000.00;;;;;;;;"])
    with pytest.raises(ValueError, match="Download vermutlich unvollständig"):
        parser.load_export(p2)


def test_b6_unvollstaendige_zeile_mitten_in_datei_bleibt_lauter_fehler(tmp_path):
    from mqlkiscanner import parser
    p = _schreibe_csv(tmp_path, [
        KOPF13,
        "2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0;0;2026.01.05 12:00:00;"
        "4050.00;0;0;500.00;",
        "2026.01.06 09:00:00;Sell;0.10;XAUUSD;4100.00;0;0;2026.01.06 1",
        "2026.01.07 09:00:00;Buy;0.10;XAUUSD;4000.00;0;0;2026.01.07 12:00:00;"
        "4010.00;0;0;100.00;"])
    with pytest.raises(ValueError, match="Felder"):
        parser.load_export(p)


def test_b6_ger40_loest_auf_de40_spec():
    import shutil
    from mqlkiscanner import config, symbols
    shutil.copy(Path(__file__).resolve().parents[1] / "data" / "contract_specs.json",
                config.CONTRACT_SPECS_FILE)
    symbols._SPECS_CACHE.clear()
    from mqlkiscanner.symbols import spec_for, normalize_symbol
    from mqlkiscanner.forensics import exposure
    entry = spec_for(normalize_symbol("GER40"))
    assert entry is not None and entry.get("class") == "INDEX"


def test_b6_ingest_mappt_broker_aus_metrics():
    from mqlkiscanner.ingest import metrics_zu_stats
    stats = metrics_zu_stats({"metrics": {"Broker": "ICM"}})
    assert stats.get("broker_server") == "ICM"
    assert metrics_zu_stats({"metrics": {}}).get("broker_server") is None


# ------------------------------------------------------------- B7 ⛔-Auswahl

def test_b7_ausschluesse_belegen_keine_slots(tmp_path, monkeypatch):
    from mqlkiscanner import fix_signale
    monkeypatch.setattr(fix_signale.config, "load_known_signals",
                        lambda: {"ausgeschlossen": [{"id": 999, "grund": "Test"}]})
    monkeypatch.setattr(fix_signale.config, "load_settings", lambda: {})
    cands = [{"id": 999, "abonnenten": 500, "quelle_kuerzel": "mql5"},
             {"id": 1, "abonnenten": 100, "quelle_kuerzel": "mql5"},
             {"id": 2, "abonnenten": 50, "quelle_kuerzel": "mql5"}]
    auswahl, infos = fix_signale.waehle_fuer_export(cands, 2)
    assert [c["id"] for c in auswahl] == [1, 2]
    assert {"quelle": "ausschlussliste", "angeboten": 1, "genommen": 0} in infos


# ------------------------------------------------------------- B9 Sync-Toleranz

def test_b9_nur_404_quelle_plus_down_quelle_liest_keinen_raise():
    """Szenario Ziellauf: Quelle A (mql5-Registry) down, Quelle B antwortet,
    kennt aber jedes Signal nicht (404) — Ergebnis leer, aber KEIN Raise;
    nur wenn GAR KEINE Quelle antwortet, wird abgebrochen."""
    from mqlkiscanner import downloader_client, downloader_sync, quellen

    def fn_nur_404(client):
        raise downloader_client.DownloaderNotFound("gibt es nicht")

    def fn_down(client):
        raise downloader_client.DownloaderConnectionError("down")

    def fake_list(nur_aktiv=True):
        return [{"id": 1, "kuerzel": "mql5", "base_url": "http://x",
                 "aktiv": 1, "typ": "mql5-downloader-v1", "name": "", "token": ""}]

    quelle_reaktion = {"antwort": "404"}

    def fake_client(quelle):
        return quelle_reaktion["antwort"]

    orig_list = downloader_sync.db.list_quellen
    orig_client = quellen.client_fuer_quelle
    downloader_sync.db.list_quellen = fake_list
    quellen.client_fuer_quelle = fake_client
    try:
        # B antwortet mit 404, A down → kein Raise, leeres Ergebnis
        assert downloader_sync._ueber_quellen(fn_nur_404) == []
        # beide down → Raise bleibt (echter Systemfehler)
        quelle_reaktion["antwort"] = "down"
        with pytest.raises(downloader_client.DownloaderConnectionError):
            downloader_sync._ueber_quellen(fn_down)
    finally:
        downloader_sync.db.list_quellen = orig_list
        quellen.client_fuer_quelle = orig_client


# ------------------------------------------------------- B10 Suffix-Kursdaten

def test_b10_normalize_stript_die_beobachteten_suffixe():
    import shutil
    from mqlkiscanner import config, symbols
    shutil.copy(Path(__file__).resolve().parents[1] / "data" / "contract_specs.json",
                config.CONTRACT_SPECS_FILE)
    symbols._SPECS_CACHE.clear()
    from mqlkiscanner.symbols import normalize_symbol
    assert normalize_symbol("AUDCADR") == "AUDCAD"
    assert normalize_symbol("XAUUSD.F") == "XAUUSD"
    assert normalize_symbol("EURUSD+") == "EURUSD"
    assert normalize_symbol("AUDCAD-ECN") == "AUDCAD"
    assert normalize_symbol("XAGUSD.Z") == "XAGUSD"
    assert normalize_symbol("EURUSDT") == "EURUSDT"  # nie still kürzen!


def test_b10_kursdaten_faellt_auf_basis_symbol_zurueck():
    from mqlkiscanner.kursdaten import KursDaten
    kd = KursDaten({})
    kd._aktiv = True

    class Mt5Fake:
        TIMEFRAME_H1 = 16385

        def __init__(self):
            self.selektiert = []

        def symbol_select(self, sym, flag):
            self.selektiert.append(sym)
            return sym == "AUDCAD"  # exaktes Suffix-Symbol existiert nicht

        def copy_rates_range(self, sym, tf, von, bis):
            return [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5}]

    kd._mt5 = Mt5Fake()
    bars = kd.hole_h1("AUDCADR", 0, 100)
    assert bars and bars[0]["close"] == 1.5
    assert kd.suffix_annahmen == {"AUDCADR": "AUDCAD"}


def test_b10_kursdaten_whitelist_bleibt_nur_lesend():
    """R-Whitelist (Intensiv-Review): die MT5-Aufruf-Whitelist von kursdaten
    darf keine Order-/Kontofunktionen enthalten — statisch bewacht, wie bei
    marktdata (test_agenten_phase_c)."""
    from mqlkiscanner import kursdaten
    verboten = {"order_send", "order_check", "positions_open", "positions_modify",
                "positions_close", "orders_total", "positions_get",
                "account_info", "trade_request"}
    quelle = open(kursdaten.__file__, encoding="utf-8").read()
    assert not (verboten & set(kursdaten.ERLAUBTE_MT5_AUFRUFE))
    for name in verboten:
        assert f"mt5.{name}" not in quelle, f"kursdaten ruft mt5.{name} auf!"


# ---------------------------------------------------- B12 Default-Vorlagen-Sync

def test_b12_default_prompts_sind_mit_den_dateien_synchron():
    """B12: Die eingebauten Defaults dürfen nie von den Dateien driften —
    bei Datei-Verlust/Reset kehrte sonst die alte harte 'Ablehnung'-
    Regel zurück."""
    from pathlib import Path
    from mqlkiscanner.llm import prompts as P
    basis = Path(P.__file__).resolve().parents[3] / "config" / "prompts"
    for konst, datei in [("DEFAULT_TRADE_ANALYSE", "trade_analyse.md"),
                         ("DEFAULT_RISIKO_ANALYSE", "risiko_analyse.md"),
                         ("DEFAULT_GESAMTBERICHT", "gesamtbericht.md"),
                         ("DEFAULT_PORTFOLIO", "portfolio.md"),
                         ("DEFAULT_TIEFENANALYSE", "tiefenanalyse.md")]:
        assert getattr(P, konst) == (basis / datei).read_text(encoding="utf-8"), datei


# -------------------------------------------------------------- B16 Fremdtext

def test_b16_alle_workflow_vorlagen_markieren_fremdtext():
    from pathlib import Path
    basis = Path("config/prompts")
    for datei in ("trade_analyse.md", "risiko_analyse.md", "gesamtbericht.md",
                  "portfolio.md", "tiefenanalyse.md"):
        text = (basis / datei).read_text(encoding="utf-8")
        assert "FREMDTEXT" in text, datei


# ------------------------------------------------------------- B14 CLI-Lock

def test_b14_cli_einzelrolle_respektiert_rolle_lock(tmp_path, monkeypatch, caplog):
    """B14: CLI-Einzelstart überspringt sauber, wenn der Rollen-Lock von
    einem lebenden Prozess gehalten wird (vorher: Doppel-Export möglich)."""
    import sys
    from mqlkiscanner.agenten import __main__ as cli, lock
    from mqlkiscanner import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    aufgerufen = []
    monkeypatch.setattr("mqlkiscanner.agenten.dirigent.tageslauf",
                        lambda **kw: aufgerufen.append(kw) or {"status": "ok"})
    with lock.lauf_lock(tmp_path, lock.rolle_lock_name("dirigent")):
        monkeypatch.setattr(sys, "argv", ["prog", "--once"])
        cli.main()  # darf NICHT starten, nur warnen
    assert aufgerufen == []
    # ohne Lock startet die Rolle normal
    monkeypatch.setattr(sys, "argv", ["prog", "--once"])
    cli.main()
    assert len(aufgerufen) == 1


# ---------------------------------------------- K1 (Fremd-Review 01.10.2026)

def test_k1_forensik_payload_nennt_vollstaendigkeit_und_basis():
    """K1: 18/54 Gesamtberichte erklärten die Batterie aus null-Feldern
    fälschlich für unvollständig — der Payload muss Vollständigkeit,
    IMMER eine Kapitalbasis (auch CSV) und Status optionaler Messungen
    sowie die Ertrags-Definition explizit nennen."""
    import json as _json
    r = pipeline.ScanResult(
        id=1, name="X", quelle="mql5", platform="MT4",
        forensik_vorhanden=True, kapitalbasis_verwendet_usd=3116.0,
        kapitalbasis_verwendet_quelle="csv_einzahlungen",
        ertrag_monat_pct=24.54, ertrag_monat_pct_forensik=8.71)
    payload = _json.loads(pipeline._forensik_json(r))
    assert payload["forensik_vollstaendig"] is True
    basis = payload["kapitalbasis_verwendet"]
    assert basis == {"usd": 3116.0, "quelle": "csv_einzahlungen"}
    status = payload["status_optionaler_messungen"]
    assert "OPTIONAL" in status["reko_eq_dd"]
    assert "OPTIONAL" in status["monitor_eq_dd"]
    assert "linearer Durchschnitt" in payload["ertrag_forensik_definition"]
    kandidat = _json.loads(pipeline._kandidat_json(r))
    assert "maßgeblich" in kandidat["ertrag_hinweis"]


# ------------------------------------------------ RetDD (Nutzer 01.10.2026)

def test_retdd_berechnung_und_urteil():
    """RetDD = Forensik-Ertrag / DD-Maximum — Gold-Spike-Fall:
    8,71 %/M bei 8,11 % DD => 1.074/Monat, 12.89/Jahr."""
    res = pipeline.ScanResult(
        id=1, name="X", score=4.1, forensik_vorhanden=True,
        ertrag_monat_pct=24.54, ertrag_monat_pct_forensik=8.71,
        retdd_monat=round(8.71 / 8.11, 3), retdd_jahr=round(8.71 / 8.11 * 12, 2),
        martingale_flag=False, stop_evidence="direct",
        schranke_verletzt=False)
    ampel, grund = pipeline.ampel_for(res, {})
    assert ampel == "🟢"
    assert "RetDD 1" in grund


def test_retdd_ampelzelle_schwellen():
    import importlib.util, sys as _sys
    spez = importlib.util.spec_from_file_location(
        "tam", Path(__file__).parent / "test_ampel_matrix.py")
    tam = importlib.util.module_from_spec(spez)
    spez.loader.exec_module(tam)
    m_eff = lambda r: tam._matrix(r)
    gruen = tam._result(retdd_monat=0.8, retdd_jahr=9.6)
    grenze = tam._result(retdd_monat=0.167, retdd_jahr=2.0)
    schlecht = tam._result(retdd_monat=0.05, retdd_jahr=0.6)
    ohne = tam._result(retdd_monat=None, retdd_jahr=None,
                       ertrag_monat_pct_forensik=None)
    assert m_eff(gruen)["retdd"].ampel == "🟢"
    assert m_eff(grenze)["retdd"].ampel == "🟡"
    assert m_eff(schlecht)["retdd"].ampel == "🟠"
    assert m_eff(ohne)["retdd"].ampel == "⚪"


def test_retdd_im_forensik_payload_und_portfolio_statistik():
    import json as _json
    r = pipeline.ScanResult(
        id=1, name="X", forensik_vorhanden=True, ertrag_monat_pct_forensik=6.0,
        retdd_monat=0.3, retdd_jahr=3.6, kapitalbasis_verwendet_usd=1000,
        kapitalbasis_verwendet_quelle="csv_einzahlungen", symbole="XAUUSD, EURUSD",
        trades_path="", ertrag_monat_pct=7.0)
    forensik = _json.loads(pipeline._forensik_json(r))
    assert forensik["retdd_monat"] == 0.3
    assert "Effizienz" in forensik["retdd_monat"] if isinstance(forensik["retdd_monat"], str) else True
    kandidat = _json.loads(pipeline._kandidat_json(r))
    assert kandidat["retdd_jahr"] == 3.6
    from mqlkiscanner import portfolio_statistik
    stat = portfolio_statistik.statistik([r])
    assert stat["signale"][0]["retdd_monat"] == 0.3
