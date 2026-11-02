"""
Zentrale Einstellungen.

Pfade und Firmenname werden aus einer optionalen ``config.ini`` neben dem
Programm gelesen (siehe ``config.example.ini``). Fehlt die Datei, gelten die
Standardwerte unten. So muss im Code nichts mehr angepasst werden, wenn sich
z. B. der Pfad der Access-Datenbank ändert.
"""
from __future__ import annotations

import configparser
import os
import sys


def app_dir() -> str:
    """Ordner, in dem die .exe bzw. das Startskript liegt."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONFIG_FILE = os.path.join(app_dir(), "config.ini")

_cfg = configparser.ConfigParser()
_cfg.read(CONFIG_FILE, encoding="utf-8")


def _get(section: str, key: str, default: str = "") -> str:
    # Umgebungsvariable hat Vorrang, z. B. LB_ACCESS_DB
    env = os.environ.get(f"LB_{key.upper()}")
    if env:
        return env
    return _cfg.get(section, key, fallback=default).strip()


DATEN_ORDNER = _get("pfade", "daten_ordner") or app_dir()
DATA_FILE = os.path.join(DATEN_ORDNER, "labordaten.json")
PREISE_FILE = os.path.join(DATEN_ORDNER, "preise.json")

# Leer = Access-Anbindung deaktiviert (Programm arbeitet nur mit JSON)
ACCESS_DB = _get("pfade", "access_db")

FIRMA = _get("allgemein", "firma")

# ── Bewertung ─────────────────────────────────────────────────────────────────
# Gewichte der Kategorien. Sie werden beim Gesamtscore auf die vorhandenen
# Kategorien normiert, müssen also nicht 100 ergeben.
GEWICHTE = {
    "qualitaet": 50,
    "zuverlaessigkeit": 20,
    "kosten": 20,
    "service": 30,
}

KATEGORIE_NAMEN = {
    "qualitaet": "Qualität",
    "zuverlaessigkeit": "Zuverlässigkeit",
    "kosten": "Kosten",
    "service": "Service",
}

# Anteil innerhalb der Qualität
QUALITAET_ANTEIL_FEHLERQUOTE = 0.7
QUALITAET_ANTEIL_ANALYTAUSWAHL = 0.3

# Werktage, die bei der Termintreue als Puffer abgezogen werden
TERMINTREUE_PUFFER = 2

GRENZE_FREIGEGEBEN = 75
GRENZE_BEOBACHTUNG = 50

DATUMSFORMAT = "%d.%m.%Y"
