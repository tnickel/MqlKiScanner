@echo off
setlocal
chcp 65001 >nul
title MqlKiScanner

rem ============================================================
rem  MqlKiScanner - Startskript (Windows)
rem  1. prueft, ob noch eine alte Instanz laeuft, und beendet sie
rem  2. nutzt .venv, wenn vorhanden, sonst das System-Python
rem  3. installiert fehlende Abhaengigkeiten automatisch
rem  4. startet die Streamlit-App und oeffnet den Browser
rem ============================================================

rem ---- Projektverzeichnis = Ordner dieser Datei ----
cd /d "%~dp0"

rem -----------------------------------------------------------
rem  SCHRITT 0: Alte Instanzen beenden (sonst "Port not available")
rem -----------------------------------------------------------
echo Pruefe auf laufende Alt-Instanzen ...

rem a) Jeden Prozess beenden, der auf Port 8501 hoert
rem    (Get-NetTCPConnection: sprachunabhaengig, kein LISTENING/ABHOEREN-Matching)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -Unique OwningProcess | ForEach-Object { $pn = (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName; Write-Host ('  Beende PID ' + $_.OwningProcess + ' (' + $pn + ') - belegt Port 8501'); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

rem b) Streamlit-Wrapper (pip-Shim) beenden
taskkill /F /IM streamlit.exe >nul 2>&1

rem c) Python-Prozesse mit "streamlit ... run" in der Kommandozeile beenden
rem    (erwischt auch `python -m streamlit run` aus vergessenen Fenstern;
rem     eigene PID ausgenommen)
powershell -NoProfile -Command "$me = $PID; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -match 'streamlit' -and $_.CommandLine -match 'run' } | ForEach-Object { Write-Host ('  Beende PID ' + $_.ProcessId + ' (alte Streamlit-Instanz)'); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

rem Kurz warten, bis Windows den Port wirklich freigibt (bis zu ~15 s),
rem PATH-sicher per PowerShell (kein Kollision mit GNU-timeout in manchen PATHs)
powershell -NoProfile -Command "$deadline = (Get-Date).AddSeconds(15); while ((Get-Date) -lt $deadline) { $c = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue; if (-not $c) { Write-Host '  Port 8501 ist frei.'; exit 0 }; Start-Sleep -Milliseconds 500 }; Write-Host '  HINWEIS: Port 8501 immer noch belegt - Startversuch trotzdem.'"

rem -----------------------------------------------------------
rem  SCHRITT 1: Python finden (bevorzugt .venv, sonst System)
rem -----------------------------------------------------------
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

%PYTHON% --version >nul 2>nul
if errorlevel 1 (
  echo [FEHLER] Python wurde nicht gefunden.
  echo.
  echo Bitte Python 3.12 oder neuer installieren:
  echo   https://www.python.org/downloads/
  echo Wichtig: Haken bei "Add python.exe to PATH" setzen.
  echo.
  pause
  exit /b 1
)

for /f "tokens=*" %%v in ('%PYTHON% --version 2^>^&1') do echo Python gefunden: %%v

rem -----------------------------------------------------------
rem  SCHRITT 2: Abhaengigkeiten pruefen / bei Bedarf installieren
rem -----------------------------------------------------------
%PYTHON% -c "import streamlit, requests, bs4, pandas; assert tuple(map(int, streamlit.__version__.split('.')[:2])) >= (1, 63)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo [Setup] Abhaengigkeiten fehlen oder sind veraltet - installiere requirements.txt
  echo         ^(erster Start kann einige Minuten dauern^) ...
  echo.
  %PYTHON% -m pip install --upgrade pip
  %PYTHON% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [FEHLER] Installation fehlgeschlagen - Meldungen oben pruefen.
    pause
    exit /b 1
  )
)

echo.
echo ================================================
echo   MqlKiScanner startet auf http://localhost:8501
echo   Der Browser oeffnet sich automatisch.
echo   Beenden: dieses Fenster schliessen oder Strg+C
echo ================================================
echo.

rem -----------------------------------------------------------
rem  SCHRITT 3: App starten (headless=false => Browser oeffnet sich)
rem -----------------------------------------------------------
%PYTHON% -m streamlit run streamlit_app.py --server.port 8501 --server.headless=false

echo.
echo App beendet.
pause
