@echo off
setlocal
chcp 65001 >nul
title MqlKiScanner

rem ============================================================
rem  MqlKiScanner - Startskript (Windows)
rem  - nutzt .venv, wenn vorhanden, sonst das System-Python
rem  - installiert fehlende Abhaengigkeiten automatisch
rem  - startet die Streamlit-App und oeffnet den Browser
rem ============================================================

rem ---- Projektverzeichnis = Ordner dieser Datei ----
cd /d "%~dp0"

rem ---- Python finden: bevorzugt .venv, sonst System-Python ----
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

rem ---- Abhaengigkeiten pruefen / bei Bedarf installieren ----
%PYTHON% -c "import streamlit, requests, bs4, pandas" >nul 2>nul
if errorlevel 1 (
  echo.
  echo [Setup] Abhaengigkeiten fehlen - installiere requirements.txt
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

rem ---- App starten (headless=false => Browser oeffnet sich selbst) ----
%PYTHON% -m streamlit run streamlit_app.py --server.port 8501 --server.headless=false

echo.
echo App beendet.
pause
