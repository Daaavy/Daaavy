@echo off
setlocal
cd /d "%~dp0"
title Lieferantenbewertung

rem --- Python suchen ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto keinpython
%PY% -c "import sys" >nul 2>nul || goto keinpython

rem --- Beim ersten Start fehlende Pakete installieren ---
%PY% -c "import matplotlib, reportlab" >nul 2>nul
if errorlevel 1 (
  echo Erster Start: benoetigte Pakete werden installiert. Das dauert einen Moment ...
  %PY% -m pip install --user -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Installation fehlgeschlagen. Bitte Internetverbindung pruefen.
    pause
    exit /b 1
  )
)

rem --- Programm starten (dieses Fenster bitte offen lassen) ---
echo Lieferantenbewertung laeuft. Dieses Fenster nicht schliessen.
%PY% start.py
if errorlevel 1 (
  echo.
  echo Das Programm wurde mit einem Fehler beendet. Meldung siehe oben.
  pause
)
exit /b 0

:keinpython
echo Python wurde nicht gefunden.
echo.
echo Bitte Python von https://www.python.org/downloads/ installieren
echo und dabei unten "Add python.exe to PATH" anhaken.
echo Danach diese Datei erneut doppelklicken.
pause
exit /b 1
