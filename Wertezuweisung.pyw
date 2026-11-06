r"""Analyte Comparison / Wertezuweisung starten (Doppelklick) - ohne schwarzes Fenster.

Geht auch im Netzwerkordner (\\server\...): Python braucht dafür keine
Eingabeaufforderung, deshalb kommt hier keine Meldung "UNC-Pfade werden nicht unterstützt".
Fehlende Zusatzpakete werden beim Start installiert (das Programm fragt vorher).
"""
import importlib
import importlib.util
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

ORDNER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORDNER)

# Paket (Importname) -> (pip-Name, wofür, Pflicht?)
PAKETE = {
    'pdfplumber':  ('pdfplumber',  'PDFs einlesen', True),
    'reportlab':   ('reportlab',   'PDF-Export', True),
    'sv_ttk':      ('sv-ttk',      'modernes Aussehen', False),
    'tkinterdnd2': ('tkinterdnd2', 'PDFs ins Fenster ziehen', False),
}


def _meldung(fehler, text):
    root = tk.Tk()
    root.withdraw()
    (messagebox.showerror if fehler else messagebox.showinfo)('Wertezuweisung', text)
    root.destroy()


def _python_exe():
    # pythonw.exe hat keine Konsole - für pip lieber python.exe aus demselben Ordner nehmen
    exe = sys.executable
    kandidat = os.path.join(os.path.dirname(exe), 'python.exe')
    return kandidat if exe.lower().endswith('pythonw.exe') and os.path.exists(kandidat) else exe


def _installiere(namen):
    flags = 0x08000000 if sys.platform.startswith('win') else 0   # kein Konsolenfenster
    ausgabe = ''
    for extra in ([], ['--user']):        # ohne Adminrechte ggf. ins Benutzerprofil
        try:
            r = subprocess.run([_python_exe(), '-m', 'pip', 'install', '--quiet',
                                '--disable-pip-version-check', '--no-warn-script-location',
                                *extra, *namen],
                               capture_output=True, text=True, creationflags=flags)
        except Exception as e:
            ausgabe += f'\n{e}'
            continue
        ausgabe += r.stdout + r.stderr
        if r.returncode == 0:
            importlib.invalidate_caches()
            if extra:
                import site
                site.addsitedir(site.getusersitepackages())
            return True, ausgabe
    return False, ausgabe


def _pakete_sicherstellen():
    fehlend = [p for p in PAKETE if importlib.util.find_spec(p) is None]
    if not fehlend:
        return True
    pflicht = [p for p in fehlend if PAKETE[p][2]]
    liste = '\n'.join(f'  - {PAKETE[p][0]}  ({PAKETE[p][1]})' for p in fehlend)
    root = tk.Tk()
    root.withdraw()
    ja = messagebox.askyesno('Wertezuweisung',
        f'Es fehlen Zusatzpakete:\n\n{liste}\n\n'
        'Jetzt automatisch installieren? (Internet nötig, dauert ca. 1 Minute)')
    root.destroy()
    if not ja:
        return not pflicht
    ok, ausgabe = _installiere([PAKETE[p][0] for p in fehlend])
    if ok:
        return True
    _meldung(True,
        'Die Zusatzpakete konnten nicht installiert werden (evtl. blockiert die '
        'Firmen-Firewall den Download).\n\nBitte die IT bitten, diesen Befehl auszuführen:\n\n'
        f'"{_python_exe()}" -m pip install {" ".join(PAKETE[p][0] for p in fehlend)}\n\n'
        'Meldung:\n' + '\n'.join(ausgabe.strip().splitlines()[-8:]))
    return not pflicht


if not os.path.exists(os.path.join(ORDNER, 'Wertezuweisung.py')):
    _meldung(True, 'Die Programmdatei Wertezuweisung.py fehlt in diesem Ordner:\n'
                   f'{ORDNER}\n\nWurde die ZIP-Datei entpackt?')
    raise SystemExit(1)

if not _pakete_sicherstellen():
    raise SystemExit(1)

try:
    import Wertezuweisung  # noqa: E402
    Wertezuweisung.App().mainloop()
except Exception:
    import traceback
    _meldung(True, 'Das Programm konnte nicht gestartet werden:\n\n' + traceback.format_exc()[-1500:])
    raise SystemExit(1)
