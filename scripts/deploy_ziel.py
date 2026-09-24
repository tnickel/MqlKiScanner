# -*- coding: utf-8 -*-
"""Deployment: MqlKiScanner auf den konfigurierten Zielrechner.

Ein Klick-Deploy von dem Entwicklungssystem auf den Trading-Rechner:

  1. Verbinden (SSH/SFTP, Zugangsdaten aus config/deploy.local.json
     oder Umgebungsvariablen DEPLOY_HOST/USER/PASSWORD) und ABSICHERN,
     dass der Hostname wirklich der konfigurierte Zielrechner ist
     (falscher-Rechner-Schutz).
  2. Portables Python 3.12 ins Tools-Verzeichnis am Ziel entpacken
     (NuGet-Paket), falls es dort fehlt.
  3. Code + config (inkl. secrets.local.json) + Daten-Kern via SFTP syncen.
     Die SQLite-DB wird vorher lokal über die backup-API gespiegelt — auch
     wenn die App gerade läuft.
  4. Ziel-Einstellungen patchen (siehe settings_patched unten).
  5. .venv anlegen + requirements installieren (+ MetaTrader5-Paket).
  6. start.bat als Ziel-User starten und Streamlit-Gesundheit pruefen.

Aufruf (aus dem Projekt-Root):
  python scripts/deploy_ns1mqsv.py              # alles
  python scripts/deploy_ns1mqsv.py --code-only  # nur Sync+Konfig (kein Python/venv-Setup)
  python scripts/deploy_ns1mqsv.py --kein-start # installieren, aber nicht starten

Zugangsdaten-Datei (gitignored, einmal anlegen):
  config/deploy.local.json mit host, user, password, ziel (Zielordner),
  hostname_erwartet (Falsch-Rechner-Schutz), ziel_user (Session, in der
  die Apps laufen sollen) und tools_python_pfad.
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
NUGET = ROOT / "deploy-cache" / "python-3.12.10.nupkg"
NUGET_URL = "https://www.nuget.org/api/v2/package/python/3.12.10"

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
        "ziel": daten.get("ziel", ""),
        "hostname_erwartet": daten.get("hostname_erwartet", ""),
        "ziel_user": daten.get("ziel_user", ""),
        "tools_python_pfad": daten.get("tools_python_pfad", ""),
    }
    fehlt = [k for k in ("host", "user", "password", "ziel",
                         "hostname_erwartet", "ziel_user",
                         "tools_python_pfad") if not zugang[k]]
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


def tools_python_sicherstellen(ziel: Ziel) -> str:
    """Portables Python ins Tools-Verzeichnis am Ziel (NuGet-Paket).

    Warum kein Installer: der python.org-Bootstrapper sieht ein vorhandenes
    per-user-Python als 'bereits installiert' und tut dann still nichts
    (Exit 0 ohne Kopieren). Das NuGet-Paket ist ein ZIP mit vollständigem
    Python (pip + venv), braucht keine Installation UND liegt bewusst
    ausserhalb der Nutzerprofile, damit die Apps unter der Ziel-User-
    Session laufen."""
    tools_py = ziel.zugang["tools_python_pfad"].replace("\\", "/")
    basis = tools_py.rsplit("/", 1)[0]
    out, _, _ = ziel.run(f'"{tools_py}" --version')
    if out.strip().startswith("Python 3.1"):
        _log("python", f"vorhanden: {out.strip()} ({tools_py})")
        return tools_py
    if not NUGET.exists():
        raise SystemExit(f"NuGet-Paket fehlt lokal: {NUGET} — einmal laden: "
                         f'curl -L -o "{NUGET}" {NUGET_URL}')
    _log("python", f"entpacke portables Python (NuGet) nach {basis} …")
    ziel.sftp.put(str(NUGET), "C:/Users/Public/python.nupkg.zip")
    ziel.ps(f"Remove-Item -Recurse -Force '{basis}', "
            f"'{basis}_tmp' -ErrorAction SilentlyContinue; "
            "Expand-Archive -Path C:\\Users\\Public\\python.nupkg.zip "
            f"-DestinationPath '{basis}_tmp' -Force; "
            f"New-Item -ItemType Directory -Force -Path '{basis}' | Out-Null; "
            f"Move-Item '{basis}_tmp\\tools\\*' '{basis}\\'; "
            f"Remove-Item -Recurse -Force '{basis}_tmp'",
            timeout=300)
    out, err, _ = ziel.run(f'"{tools_py}" --version')
    if not out.strip().startswith("Python"):
        raise SystemExit(f"Tools-Python laeuft nicht: {out.strip()} "
                         f"{err.strip()[:200]}")
    _log("python", f"bereit: {out.strip()}")
    return tools_py


def rechte_setzen(ziel: Ziel) -> None:
    """Der Ziel-User braucht Vollzugriff auf Projekt und Python — die
    liegen bewusst ausserhalb seines Nutzerprofils."""
    tools_py = ziel.zugang["tools_python_pfad"].replace("\\", "/")
    for pfad in (ziel.ziel, tools_py.rsplit("/", 1)[0]):
        out, err, _ = ziel.run(
            f'icacls "{pfad.replace("/", chr(92))}" '
            f"/grant {ziel.zugang['ziel_user']}:(OI)(CI)F /T /C /Q",
            timeout=600)
        _log("rechte", f"{pfad} -> {ziel.zugang['ziel_user']} voll"
              + ("" if "fehler" not in (err or "").lower() else
                 f" (Hinweis: {err[:100]})"))


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


def settings_patched(ziel: Ziel, zugang: dict) -> dict:
    """Lokale app_settings.json lesen und ziel-spezifisch anpassen."""
    settings = json.loads((ROOT / "config" / "app_settings.json")
                          .read_text(encoding="utf-8"))
    # Downloader laeuft AUF dem Zielrechner (dort Port 8089, Health 200).
    settings["downloader_base_url"] = "http://127.0.0.1:8089/api/v1"
    # MT5-Terminal am Ziel — aus der Zugangsdaten-Datei (optionaler Key
    # markt_terminal_pfad); nur setzen, wenn es dort existiert.
    terminal = str(zugang.get("markt_terminal_pfad") or "")
    if terminal:
        out, _, _ = ziel.ps(f"Test-Path '{terminal}'")
        if out.strip().lower() == "true":
            settings["markt_terminal_pfad"] = terminal
            _log("konfig", f"markt_terminal_pfad -> {terminal}")
        else:
            _log("konfig", "Terminal am Ziel nicht gefunden — Pfad bleibt "
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
    settings = settings_patched(ziel, ziel.zugang)
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
    # NuGet-Python bringt pip nicht mit — venv-ensurepip als Sicherung
    out, _, _ = ziel.run(f'"{venv_py}" -m pip --version')
    if "No module named pip" in out:
        _log("venv", "pip fehlt -> ensurepip")
        ziel.run(f'"{venv_py}" -m ensurepip --upgrade', timeout=300)

    _log("pip", "installiere/aktualisiere Abhaengigkeiten (Dauer ~Minuten) …")
    out, err, code = ziel.run(
        f'"{venv_py}" -m pip install --upgrade pip '
        f'&& "{venv_py}" -m pip install -r "{ziel.ziel}/requirements.txt" '
        f'&& "{venv_py}" -m pip install MetaTrader5 '
        f'&& "{venv_py}" -m pip install "streamlit==1.63.0"', timeout=1200)
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


def task_anlegen(ziel: Ziel, name: str, bat: str, onstart: bool) -> None:
    """Task ALS ZIEL-USER (Interactive — laeuft in der Trader-Session,
    Fenster sind sichtbar; kein Passwort noetig, startet nur bei
    angemeldetem User = Normalzustand dort). OHNE Zeitlimit: der
    schtasks-Default wuerde die App nach 72 h killen."""
    trigger = ("$t = New-ScheduledTaskTrigger -AtStartup"
               if onstart else
               "$t = New-ScheduledTaskTrigger -Once -At "
               "(Get-Date).AddMinutes(10)")
    skript = (
        f"$ErrorActionPreference = 'Stop'; {trigger}; "
        "$a = New-ScheduledTaskAction -Execute 'cmd.exe' "
        f"-Argument '/c start \"MqlKiScanner\" /min \"{bat}\"'; "
        "$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit "
        "(New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -StartWhenAvailable; "
        f"Register-ScheduledTask -TaskName '{name}' -Action $a -Trigger $t "
        f"-Settings $s -User '{ziel.zugang['ziel_user']}' "
        f"-Force | Out-Null; 'angelegt'")
    out, err, _ = ziel.ps(skript, timeout=90)
    _log("task", f"{name}: {out.strip() or err.strip()[:160]}")


def starten_und_pruefen(ziel: Ziel) -> None:
    bat = ziel.ziel.replace("/", chr(92)) + "\\start.bat"
    task_anlegen(ziel, "MqlKiScannerStart", bat, onstart=False)
    task_anlegen(ziel, "MqlKiScanner Autostart", bat, onstart=True)
    ziel.run('schtasks /Run /TN "MqlKiScannerStart"')
    # Der WMI-Vorlauf von start.bat dauert auf der beschaeftigten Maschine
    # Minuten — grosszuegig pollen.
    deadline = time.time() + 420
    antwort = ""
    while time.time() < deadline:
        time.sleep(8)
        out, _, _ = ziel.ps(
            "$ErrorActionPreference = 'SilentlyContinue'; "
            "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8504"
            "/_stcore/health' -UseBasicParsing -TimeoutSec 4).Content } "
            "catch { 'warte' }")
        antwort = out.strip()
        if antwort == "ok":
            break
    _log("start", f"Streamlit 8504: {antwort}"
          + ("" if antwort == "ok" else
             " — nicht hochgekommen; dort start.bat-Fenster bzw. "
             "data/streamlit_restart.log pruefen"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-only", action="store_true",
                        help="kein Python/venv/pip (nur Sync+Konfig)")
    parser.add_argument("--kein-start", action="store_true",
                        help="installieren, aber nicht starten")
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
            python_exe = tools_python_sicherstellen(ziel)
        sync(ziel)
        if not args.code_only:
            venv_und_pakete(ziel, python_exe)
        rechte_setzen(ziel)
        if not args.kein_start:
            starten_und_pruefen(ziel)
        _log("fertig", f"MqlKiScanner liegt unter {zugang['ziel']} "
                       f"(laeuft als {zugang['ziel_user']}: App Port 8504, "
                       f"REST :8611 "
                       "lazy; Tasks 'MqlKiScannerStart' + Autostart).")
    finally:
        ziel.close()


if __name__ == "__main__":
    main()
