"""
Datenhaltung in JSON-Dateien.

Format von ``labordaten.json`` (kompatibel zur alten Version)::

    {"DE92": [ {eintrag}, {eintrag}, ... ], ...}

Neu: Jeder Eintrag bekommt beim Laden eine eindeutige ``id``. Damit lassen
sich Einträge sicher bearbeiten/löschen, auch wenn es mehrere Einträge im
selben Monat gibt (z. B. Level L1–L3).

Gespeichert wird atomar (erst in eine temporäre Datei, dann umbenennen) und
die vorherige Version bleibt als ``.bak`` erhalten.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Optional

from . import config


def _lese_json(pfad: str, standard):
    if not os.path.exists(pfad):
        return standard
    with open(pfad, "r", encoding="utf-8") as f:
        return json.load(f)


def _schreibe_json(pfad: str, daten) -> None:
    ordner = os.path.dirname(os.path.abspath(pfad))
    os.makedirs(ordner, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=ordner)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
        if os.path.exists(pfad):
            shutil.copy2(pfad, pfad + ".bak")
        os.replace(tmp, pfad)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def neue_id() -> str:
    return uuid.uuid4().hex[:12]


def labor_sortierschluessel(code: str):
    """DE9 < DE29 < DE106 < FR109 – erst Länderkürzel, dann Zahl."""
    m = re.match(r"([A-Za-z]+)(\d*)(.*)", str(code))
    if m:
        return (m.group(1).upper(), int(m.group(2)) if m.group(2) else 0, m.group(3))
    return (str(code), 0, "")


def laenderkuerzel(code: str) -> str:
    m = re.match(r"([A-Za-z]+)", str(code))
    return m.group(1).upper() if m else "?"


def eintrag_sortierschluessel(e: dict):
    return (e.get("monat", ""), e.get("produkt", ""),
            str(e.get("konzentration", "")), str(e.get("pruefnummer", "")))


def _normalisieren(e: dict) -> dict:
    e.setdefault("id", neue_id())
    for key in ("qualitaet", "zuverlaessigkeit", "kosten", "service"):
        if not isinstance(e.get(key), dict):
            e[key] = {}
    for key in ("monat", "produkt", "konzentration", "pruefnummer", "kommentar"):
        e[key] = "" if e.get(key) is None else str(e.get(key))
    return e


class Datenspeicher:
    """Bewertungsdaten aller Labore."""

    def __init__(self, pfad: str = config.DATA_FILE):
        self.pfad = pfad
        self.daten: dict = {}
        self.laden()

    # ── Laden / Speichern ─────────────────────────────────────────────────
    def laden(self) -> None:
        roh = _lese_json(self.pfad, {})
        geaendert = False
        for labor, eintraege in roh.items():
            for e in eintraege:
                if "id" not in e:
                    geaendert = True
                _normalisieren(e)
        self.daten = roh
        if geaendert and os.path.exists(self.pfad):
            self.speichern()

    def speichern(self) -> None:
        for labor in self.daten:
            self.daten[labor].sort(key=eintrag_sortierschluessel)
        _schreibe_json(self.pfad, self.daten)

    # ── Labore ────────────────────────────────────────────────────────────
    def labore(self) -> list:
        return sorted(self.daten.keys(), key=labor_sortierschluessel)

    def labor_anlegen(self, code: str) -> None:
        if code in self.daten:
            raise ValueError(f"Labor '{code}' existiert bereits.")
        self.daten[code] = []
        self.speichern()

    def labor_loeschen(self, code: str) -> None:
        if self.daten.pop(code, None) is not None:
            self.speichern()

    # ── Einträge ──────────────────────────────────────────────────────────
    def eintraege(self, labor: Optional[str] = None) -> list:
        """Liste von (labor, eintrag), sortiert nach Labor und Monat."""
        labore = [labor] if labor else self.labore()
        return [(l, e) for l in labore
                for e in sorted(self.daten.get(l, []), key=eintrag_sortierschluessel)]

    def produkte(self, labor: Optional[str] = None) -> list:
        return sorted({e["produkt"].strip() for _, e in self.eintraege(labor)
                       if e.get("produkt", "").strip()})

    def jahre(self) -> list:
        return sorted({e["monat"][:4] for _, e in self.eintraege() if e.get("monat")},
                      reverse=True)

    def finden(self, eintrag_id: str):
        """-> (labor, eintrag) oder (None, None)."""
        for labor, eintraege in self.daten.items():
            for e in eintraege:
                if e.get("id") == eintrag_id:
                    return labor, e
        return None, None

    def duplikat(self, labor: str, eintrag: dict) -> Optional[dict]:
        """Anderer Eintrag mit gleicher Prüfnummer + Produkt + Konzentration."""
        pruef = eintrag.get("pruefnummer", "").strip()
        if not pruef:
            return None
        for e in self.daten.get(labor, []):
            if (e.get("id") != eintrag.get("id")
                    and e.get("pruefnummer", "").strip() == pruef
                    and e.get("produkt", "") == eintrag.get("produkt", "")
                    and e.get("konzentration", "") == eintrag.get("konzentration", "")):
                return e
        return None

    def eintrag_speichern(self, labor: str, eintrag: dict) -> dict:
        """Neuer Eintrag oder Ersetzen eines bestehenden (gleiche id)."""
        eintrag = _normalisieren(dict(eintrag))
        alt_labor, alt = self.finden(eintrag["id"])
        if alt is not None:
            self.daten[alt_labor].remove(alt)
        self.daten.setdefault(labor, []).append(eintrag)
        self.speichern()
        return eintrag

    def eintrag_loeschen(self, eintrag_id: str) -> Optional[dict]:
        labor, e = self.finden(eintrag_id)
        if e is None:
            return None
        self.daten[labor].remove(e)
        self.speichern()
        return e

    def eintrag_verschieben(self, eintrag_id: str, ziel: str) -> None:
        labor, e = self.finden(eintrag_id)
        if e is None or labor == ziel:
            return
        self.daten[labor].remove(e)
        self.daten.setdefault(ziel, []).append(e)
        self.speichern()


class Preisspeicher:
    """Preishistorie: {labor: {produkt: [{preis, datum, monat}, ...]}}"""

    def __init__(self, pfad: str = config.PREISE_FILE):
        self.pfad = pfad
        self.preise: dict = _lese_json(pfad, {})

    def speichern(self) -> None:
        _schreibe_json(self.pfad, self.preise)

    def aktualisieren(self, labor: str, produkt: str, preis: float, monat: str) -> bool:
        """Trägt den Preis ein, wenn er sich geändert hat. -> True wenn neu eingetragen."""
        if not labor or not produkt or not preis or preis <= 0:
            return False
        verlauf = self.preise.setdefault(labor, {}).setdefault(produkt, [])
        if verlauf and verlauf[-1].get("preis") == preis:
            return False
        verlauf.append({"preis": preis,
                        "datum": datetime.now().strftime(config.DATUMSFORMAT),
                        "monat": monat})
        self.speichern()
        return True

    def letzter_preis(self, labor: str, produkt: str) -> Optional[float]:
        verlauf = self.preise.get(labor, {}).get(produkt, [])
        return verlauf[-1]["preis"] if verlauf else None

    def loeschen(self, labor: str, produkt: str) -> None:
        if produkt in self.preise.get(labor, {}):
            del self.preise[labor][produkt]
            if not self.preise[labor]:
                del self.preise[labor]
            self.speichern()

    def labore(self) -> list:
        return sorted(self.preise.keys(), key=labor_sortierschluessel)

    def produkte(self) -> list:
        return sorted({p for lp in self.preise.values() for p in lp})

    def verlauf(self, labor_filter: str = "Alle", produkt_filter: str = "Alle"):
        """-> {(labor, produkt): [eintrag, ...]} gefiltert."""
        ergebnis = {}
        for labor in self.labore():
            if labor_filter != "Alle" and labor != labor_filter:
                continue
            for produkt, verlauf in sorted(self.preise[labor].items()):
                if produkt_filter != "Alle" and produkt != produkt_filter:
                    continue
                if verlauf:
                    ergebnis[(labor, produkt)] = verlauf
        return ergebnis
