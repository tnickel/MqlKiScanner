# -*- coding: utf-8 -*-
"""Deployment: MqlKiScanner -> Zielrechner ZIELRECHNER (C:\\Forex\\MqlKiScanner).

Ein Klick-Deploy von dem Entwicklungssystem auf den Trading-Rechner:

  1. Verbinden (SSH/SFTP, Zugangsdaten aus config/deploy.local.json
     oder Umgebungsvariablen DEPLOY_HOST/USER/PASSWORD) und ABSICHERN,
     dass der Hostname wirklich ZIELRECHNER ist (falscher-Rechner-Schutz).
  2. Python 3.12 silent installieren (per-user, ohne Admin), falls fehlt.
  3. Code + config (inkl. secrets.local.json) + Daten-Kern via SFTP syncen.
     Die SQLite-DB wird vorher lokal über die backup-API gespiegelt — auch
     wenn die App gerade läuft.
  4. Ziel-Einstellungen patchen: Downloader-URL -> 127.0.0.1:8089 (laeuft
     dort), MT5-Terminal -> Vantage (falls vorhanden), Terminal-Selbststart
     aus (nie das Trading-Terminal anfassen).
  5. .venv anlegen + requirements installieren (+ MetaTrader5-Paket).
  6. start.bat detached starten und Streamlit-Gesundheit pruefen.

Aufruf (aus dem Projekt-Root):
  python scripts/deploy_ns1mqsv.py              # alles
  python scripts/deploy_ns1mqsv.py --code-only  # nur Sync+Konfig (kein Python/venv-Setup)
  python scripts/deploy_ns1mqsv.py --kein-start # installieren, aber nicht starten

Zugangsdaten-Datei (gitignored, einmal anlegen):
  config/deploy.local.json
  {"host": "LAN-ZIELRECHNER", "hostname_erwartet": "ZIELRECHNER",
   "user": "...", "password": "...", "ziel": "C:\\\\Forex\\\\MqlKiScanner"}
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy-cache" / "python-3.12.10-amd64.exe"
INSTALLER_URL = ("https://www.python.org/ftp/python/3.12.10/"
                 "python-3.12.10-amd64.exe")
ERWARTETER_HOSTNAME = "ZIELRECHNER"

# Was mitwandert (Code): alles im Projekt-Root ausser diesen Eintraegen.
CODE_ORDNER_AUS = {".git", "__pycache__", ".venv", "deploy-cache", "data",
                   "node_modules", ".pytest_cache", ".ruff_cache",
                   ".agents", ".claude", ".vscode"}
CODE_ENDUNGEN_AUS = {".pyc", ".pyo", ".log", ".tmp"}
CODE_DATEIEN_AUS = {"scratch_probeziel.py", "deploy.local.json"}
# Daten-Kern (fuellt sich auf dem Ziel sonst neu): Historie + Geraete-Login.
DATA_DATEIEN = ("candidates.json", "known_signals.json",
                "contract_specs.json", "mql5_cookies.json")
DATA_ORDNER = ("fx_rates", "stats")
DB_NAME = "mqlkiscanner.db"


def _log(schritt: str, text: str) -> None:
    print(f"[{schritt}] {text}", flush=True)


def lade_zugang() -> dict:
    """Zugangsdaten: Datei config/deploy.local.json vor Env."""
    pfad = ROOT / "config" / "deploy.local.json"
    if pfad.exists():
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    else:
        daten = {}
    zugang = {
        "host": os.environ.get("DEPLOY_HOST", daten.get("host", "")),
        "user": os.environ.get("DEPLOY_USER", daten.get("user", "")),
        "password": os.environ.get("DEPLOY_PASSWORD", daten.get("password", "")),
        "ziel": daten.get("ziel", r"ZIELORDNER"),
        "hostname_erwartet": daten.get("hostname_erwartet",
                                       ERWARTETER_HOSTNAME),
    }
    fehlt = [k for k in ("host", "user", "password") if not zugang[k]]
    if fehlt:
        raise SystemExit(
            f"Zugangsdaten unvollstaendig ({', '.join(fehlt)}). "
            f"{pfad} anlegen (siehe Kopf dieses Skripts) oder Env-Variablen "
            "DEPLOY_HOST/USER/PASSWORD setzen.")
    return zugang


class Ziel:
    """Duennes paramiko-Fassade: run(), ps() (PowerShell), SFTP-Sync."""

    def __init__(self, zugang: dict):
        self.zugang = zugang
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(zugang["host"], username=zugang["user"],
                         password=zugang["password"], timeout=15)
        self.sftp = self.ssh.open_sftp()
        self.ziel = zugang["ziel"].replace("\\", "/")

    def run(self, befehl: str, timeout: int = 120) -> tuple[str, str, int]:
        _, out, err = self.ssh.exec_command(befehl, timeout=timeout)
        exit_code = out.channel.recv_exit_status()
        return (out.read().decode("utf-8", errors="replace"),
                err.read().decode("utf-8", errors="replace"),
                exit_code)

    def ps(self, skript: str, timeout: int = 120) -> tuple[str, str, int]:
        """PowerShell mit EncodedCommand (robust gegen alle Quote-Hoellen)."""
        kodiert = base64.b64encode(skript.encode("utf-16le")).decode("ascii")
        return self.run(f"powershell -NoProfile -NonInteractive "
                        f"-EncodedCommand {kodiert}", timeout=timeout)

    # ── SFTP-Helfer ────────────────────────────────────────────────────
    def mkdir_p(self, pfad: str) -> None:
        teile = pfad.strip("/").split("/")
        aktuell = ""
        for teil in teile:
            aktuell += "/" + teil if ":" not in teil else teil
            try:
                self.sftp.stat(aktuell)
            except FileNotFoundError:
                self.sftp.mkdir(aktuell)

    def _put_neu(self, lokal: Path, remote: str) -> bool:
        """Upload nur bei Groesse/Mtime-Abweichung; True = hochgeladen."""
        try:
            st = self.sftp.stat(remote)
            if (st.st_size == lokal.stat().st_size
                    and int(st.st_mtime) == int(lokal.stat().st_mtime)):
                return False
        except FileNotFoundError:
            pass
        self.sftp.put(str(lokal), remote)
        self.sftp.utime(remote, (lokal.stat().st_mtime, lokal.stat().st_mtime))
        return True

    def sync_ordner(self, lokal: Path, remote: str,
                    ordner_aus: set[str] | None = None,
                    endungen_aus: set[str] | None = None,
                    dateien_aus: set[str] | None = None) -> tuple[int, int]:
        """Rekursiver Baum-Sync. Rueckgabe (hochgeladen, geprueft)."""
        ordner_aus = ordner_aus or set()
        endungen_aus = endungen_aus or set()
        dateien_aus = dateien_aus or set()
        self.mkdir_p(remote)
        hochgeladen = geprueft = 0
        for eintrag in sorted(lokal.iterdir()):
            if eintrag.name in ordner_aus or eintrag.name in dateien_aus:
                continue
            ziel_pfad = f"{remote}/{eintrag.name}"
            if eintrag.is_dir():
                if eintrag.name in ordner_aus:
                    continue
                h, g = self.sync_ordner(eintrag, ziel_pfad, ordner_aus,
                                        endungen_aus, dateien_aus)
                hochgeladen += h
                geprueft += g
            elif eintrag.suffix.lower() not in endungen_aus:
                geprueft += 1
                if self._put_neu(eintrag, ziel_pfad):
                    hochgeladen += 1
        return hochgeladen, geprueft

    def close(self) -> None:
        try:
            self.sftp.close()
        finally:
            self.ssh.close()


def hostname_absichern(ziel: Ziel) -> None:
    out, _, _ = ziel.run("hostname")
    name = out.strip().upper()
    erwartet = ziel.zugang["hostname_erwartet"].upper()
    if name != erwartet:
        raise SystemExit(
            f"ABBRUCH — falscher Rechner! Angemeldet an '{name}', "
            f"erwartet '{erwartet}'. Zugangsdaten pruefen.")


def python_sicherstellen(ziel: Ziel) -> str:
    """Liefert den Pfad eines echten Python (>=3.12) auf dem Ziel."""
    out, _, _ = ziel.ps("$ErrorActionPreference = 'SilentlyContinue'; "
                        "$c = Get-Command python -ErrorAction SilentlyContinue; "
                        "if ($c) { & python -c 'import sys; print(sys.executable)'; "
                        "& python --version }")
    zeilen = [z.strip() for z in out.splitlines() if z.strip()]
    if zeilen and any(z.startswith("Python 3.1") for z in zeilen):
        _log("python", f"vorhanden: {zeilen[1] if len(zeilen) > 1 else zeilen[0]} "
                       f"({zeilen[0]})")
        return zeilen[0]
    if zeilen and "Python" not in " ".join(zeilen):
        pass  # Store-Stub oder nichts -> unten installieren

    if not INSTALLER.exists():
        raise SystemExit(
            f"Kein Python auf dem Ziel und Installer fehlt lokal: {INSTALLER}\n"
            f"Einmal herunterladen: curl -L -o \"{INSTALLER}\" {INSTALLER_URL}")

    _log("python", "kein echtes Python — stiller Install 3.12.10 (per-user) …")
    remote_installer = "C:/Users/Public/python-3.12.10-amd64.exe"
    ziel.sftp.put(str(INSTALLER), remote_installer)
    ziel.run(f'"{remote_installer.replace("/", chr(92))}" /quiet '
             f"InstallAllUsers=0 PrependPath=1 Include_test=0 "
             f"Include_launcher=1", timeout=600)
    kandidat = ("C:/Users/" + ziel.zugang["user"]
                + "/AppData/Local/Programs/Python/Python312/python.exe")
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            ziel.sftp.stat(kandidat)
            break
        except FileNotFoundError:
            time.sleep(3)
    else:
        raise SystemExit("Python-Installation nicht nach 300 s fertig "
                         f"(erwartet: {kandidat}).")
    out, _, _ = ziel.run(f'"{kandidat}" --version')
    _log("python", f"installiert: {out.strip()} -> {kandidat}")
    return kandidat


def db_lokal_spiegeln() -> Path:
    """Konsistente DB-Kopie via sqlite3-backup-API (auch bei laufender App)."""
    quelle = ROOT / "data" / DB_NAME
    ziel_datei = ROOT / "deploy-cache" / DB_NAME
    ziel_datei.parent.mkdir(exist_ok=True)
    con_q = sqlite3.connect(quelle)
    con_z = sqlite3.connect(ziel_datei)
    with con_z:
        con_q.backup(con_z)
    con_q.close()
    con_z.close()
    return ziel_datei


def settings_patched(ziel: Ziel) -> dict:
    """Lokale app_settings.json lesen und ziel-spezifisch anpassen."""
    settings = json.loads((ROOT / "config" / "app_settings.json")
                          .read_text(encoding="utf-8"))
    # Downloader laeuft AUF dem Zielrechner (dort Port 8089, Health 200).
    settings["downloader_base_url"] = "http://127.0.0.1:8089/api/v1"
    # MT5-Terminal dort heisst Vantage — nur setzen, wenn es existiert.
    vantage = "C:\\Forex\\Mt5\\Vantage\\terminal64.exe"
    out, _, _ = ziel.ps(f"Test-Path '{vantage}'")
    if out.strip().lower() == "true":
        settings["markt_terminal_pfad"] = vantage
        _log("konfig", f"markt_terminal_pfad -> {vantage}")
    else:
        _log("konfig", "Vantage-Terminal nicht gefunden — Pfad bleibt "
                       "wie lokal (im Admin-Tab anpassbar).")
    # Politik auf dem Trading-Rechner: Terminal NIEMALS selbst starten
    # (terminal_beenden wuerde es nach dem Lauf schliessen).
    settings["markt_start_erlauben"] = False
    return settings


def sync(ziel: Ziel) -> None:
    ziel.mkdir_p(ziel.ziel)

    # 1) Alte Code-Baeume loeschen (kein Muell aus frueheren Laeufen) …
    for ordner in ("src", "app_pages", "assets", "doc", "tests",
                   "scripts", "config/prompts"):
        ziel.run(f'if exist "{ziel.ziel.replace("/", chr(92))}\\{ordner}" '
                 f"rmdir /s /q "
                 f'"{ziel.ziel.replace("/", chr(92))}\\{ordner}"')

    # 2) … und Code frisch syncen (inkrementell je Datei).
    h, g = ziel.sync_ordner(ROOT, ziel.ziel, CODE_ORDNER_AUS,
                            CODE_ENDUNGEN_AUS, CODE_DATEIEN_AUS)
    _log("sync", f"Code/Bilder/Doku: {h} von {g} Dateien hochgeladen")

    # 3) Daten-Kern: DB gespiegelt + JSONs + kleine Ordner.
    ziel.mkdir_p(f"{ziel.ziel}/data")
    db_deploy = db_lokal_spiegeln()
    ziel.sftp.put(str(db_deploy), f"{ziel.ziel}/data/{DB_NAME}")
    _log("sync", f"{DB_NAME} ({db_deploy.stat().st_size / 1e6:.1f} MB, "
                 "konsistent gespiegelt)")
    for name in DATA_DATEIEN:
        lokal = ROOT / "data" / name
        if lokal.exists():
            ziel.sftp.put(str(lokal), f"{ziel.ziel}/data/{name}")
    for name in DATA_ORDNER:
        lokal = ROOT / "data" / name
        if lokal.is_dir():
            h2, g2 = ziel.sync_ordner(lokal, f"{ziel.ziel}/data/{name}")
            _log("sync", f"data/{name}: {h2} von {g2} Dateien")

    # 4) Config: Prompts (schon im Code-Sync via config/) + gepatchte
    #    Settings + Secrets. app_settings.json hier IMMER frisch (Patch!).
    settings = settings_patched(ziel)
    patch_pfad = ROOT / "deploy-cache" / "app_settings.ziel.json"
    patch_pfad.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    ziel.sftp.put(str(patch_pfad), f"{ziel.ziel}/config/app_settings.json")
    secrets = ROOT / "config" / "secrets.local.json"
    if secrets.exists():
        ziel.sftp.put(str(secrets), f"{ziel.ziel}/config/secrets.local.json")
        _log("konfig", "app_settings (gepatcht) + secrets.local.json "
                       "uebertragen")


def venv_und_pakete(ziel: Ziel, python_exe: str) -> None:
    venv_py = f"{ziel.ziel}/.venv/Scripts/python.exe"
    try:
        ziel.sftp.stat(venv_py)
        _log("venv", "existiert schon")
    except FileNotFoundError:
        _log("venv", f"anlegen mit {python_exe} …")
        out, err, code = ziel.run(f'"{python_exe}" -m venv '
                                  f'"{ziel.ziel}/.venv"', timeout=300)
        if code != 0:
            raise SystemExit(f"venv-Anlage fehlgeschlagen: {err[:400]}")
        ziel.sftp.stat(venv_py)  # wirft, wenn es trotzdem fehlt

    _log("pip", "installiere/aktualisiere Abhaengigkeiten (Dauer ~Minuten) …")
    out, err, code = ziel.run(
        f'"{venv_py}" -m pip install --upgrade pip '
        f'&& "{venv_py}" -m pip install -r "{ziel.ziel}/requirements.txt" '
        f'&& "{venv_py}" -m pip install MetaTrader5', timeout=900)
    letzte = [z for z in out.splitlines() if z.strip()][-2:]
    _log("pip", (" | ".join(letzte) if code == 0 else
                 f"FEHLER (Exit {code}): {err[-400:]}"))
    if code != 0:
        raise SystemExit("pip-Installation fehlgeschlagen.")

    out, err, code = ziel.run(
        f'"{venv_py}" -m compileall -q "{ziel.ziel}/src" '
        f'"{ziel.ziel}/streamlit_app.py" && "{venv_py}" -c '
        '"import streamlit, requests, bs4, pandas; '
        "print('deps ok, streamlit', streamlit.__version__)\"",
        timeout=300)
    _log("smoke", out.strip() or err.strip())


def starten_und_pruefen(ziel: Ziel) -> None:
    _log("start", "start.bat detached starten …")
    ziel.ps(f"Start-Process -FilePath '{ziel.ziel}/start.bat' "
            f"-WorkingDirectory '{ziel.ziel}'")
    deadline = time.time() + 150
    antwort = ""
    while time.time() < deadline:
        out, _, _ = ziel.ps(
            "$ErrorActionPreference='SilentlyContinue'; "
            "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8504"
            "/_stcore/health' -UseBasicParsing -TimeoutSec 4).Content } "
            "catch { 'warte' }")
        antwort = out.strip()
        if antwort == "ok":
            break
        time.sleep(5)
    if antwort == "ok":
        _log("start", "Streamlet gesund: http://127.0.0.1:8504/_stcore/health "
                      "-> ok (Port 8504, Browser oeffnet start.bat dort)")
    else:
        _log("start", f"Health-Check ohne 'ok' ({antwort!r}) — dort "
                      "start.bat-Fenster bzw. data/streamlit_restart.log "
                      "pruefen.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-only", action="store_true",
                        help="kein Python-Install/venv/pip (nur Sync+Konfig)")
    parser.add_argument("--kein-start", action="store_true",
                        help="installieren, aber start.bat nicht ausfuehren")
    args = parser.parse_args()

    zugang = lade_zugang()
    _log("verbinde", f"{zugang['user']}@{zugang['host']} …")
    ziel = Ziel(zugang)
    try:
        hostname_absichern(ziel)
        _log("verbinde", "Hostname-Bestätigung: "
              + ziel.run("hostname")[0].strip())

        python_exe = ""
        if not args.code_only:
            python_exe = python_sicherstellen(ziel)
        sync(ziel)
        if not args.code_only:
            venv_und_pakete(ziel, python_exe)
        if not args.kein_start:
            starten_und_pruefen(ziel)
        _log("fertig", f"MqlKiScanner liegt unter {zugang['ziel']} "
                       "(start.bat startet die App auf Port 8504, "
                       "REST :8611).")
    finally:
        ziel.close()


if __name__ == "__main__":
    main()
