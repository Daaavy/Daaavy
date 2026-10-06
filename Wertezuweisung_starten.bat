@echo off
REM Analyte Comparison / Wertezuweisung starten (Doppelklick)
cd /d "%~dp0"
if not exist "Wertezuweisung.py" (
  echo Die Programmdatei Wertezuweisung.py fehlt in diesem Ordner.
  echo Wurde die ZIP-Datei vielleicht nicht entpackt?
  echo Bitte im Explorer: Rechtsklick auf die ZIP-Datei - "Alle extrahieren..." - "Extrahieren",
  echo dann im entpackten Ordner "Wertezuweisung" Wertezuweisung_starten.bat doppelklicken.
  pause
  exit /b 1
)
set PY=python
where py >NUL 2>NUL && set PY=py -3
%PY% --version >NUL 2>NUL || (
  echo Python ist nicht installiert. Bitte von https://www.python.org/downloads/ installieren
  echo und beim Installieren das Haekchen "Add python.exe to PATH" setzen.
  pause
  exit /b 1
)
REM Zusatzpakete nur installieren, wenn sie noch fehlen
%PY% -c "import pdfplumber, reportlab, sv_ttk, tkinterdnd2" >NUL 2>NUL || (
  echo Erster Start: Zusatzpakete werden installiert, bitte kurz warten ...
  %PY% -m pip install --quiet --disable-pip-version-check --no-warn-script-location pdfplumber reportlab sv-ttk tkinterdnd2 || echo Hinweis: Zusatzpakete konnten nicht installiert werden - bitte Internetverbindung pruefen.
)
%PY% Wertezuweisung.py
if errorlevel 1 pause
