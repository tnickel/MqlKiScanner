@echo off
rem ============================================================
rem  MqlKiScanner - Agenten-Daemon Autostart (04.10.2026)
rem  Wird per Startup-Verknuepfung nach Rechner-Neustart
rem  aufgerufen (Auftrag "Autostart offen seit Phase E").
rem  Der Daemon respektiert agenten_enabled aus app_settings.json:
rem  Ausgeschaltet = er idlet einfach (keine Rollen, keine Scans).
rem ============================================================
cd /d "%~dp0"
set "PYTHON=python"
if exist ".venv\Scripts\pythonw.exe" set "PYTHON=.venv\Scripts\pythonw.exe"
set "PYTHONPATH=src"
start "MqlKiScanner Agenten-Daemon" /min %PYTHON% -m mqlkiscanner.agenten
