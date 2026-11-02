"""
Score-Berechnung – reine Funktionen ohne Oberfläche, damit sie testbar sind.

Alle Scores liegen zwischen 0 und 100. ``None`` bedeutet "keine Daten" und
wird bei Durchschnitten herausgerechnet (nicht als 0 gezählt).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from . import config

Zahl = Optional[float]


# ── Eingabe-Hilfen ────────────────────────────────────────────────────────────

def parse_zahl(wert) -> Zahl:
    """'1,5' / '1.5' / 1.5 -> 1.5; leer oder ungültig -> None."""
    if wert is None or isinstance(wert, bool):
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    text = str(wert).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_datum(text) -> Optional[date]:
    try:
        return datetime.strptime(str(text).strip(), config.DATUMSFORMAT).date()
    except (TypeError, ValueError):
        return None


def _zahl(d: dict, key: str) -> Zahl:
    return parse_zahl(d.get(key))


# ── Einzelbausteine ───────────────────────────────────────────────────────────

def netto_tage(von, bis, puffer: int = 0) -> Optional[int]:
    """Werktage (ohne Sa/So) zwischen zwei Daten abzüglich Puffer.

    Gibt None zurück, wenn ein Datum fehlt/ungültig ist oder ``bis`` vor ``von`` liegt.
    """
    d1, d2 = parse_datum(von), parse_datum(bis)
    if d1 is None or d2 is None or d2 < d1:
        return None
    kalendertage = (d2 - d1).days
    wochenende = sum(1 for i in range(kalendertage)
                     if (d1 + timedelta(days=i)).weekday() >= 5)
    return max(0, kalendertage - wochenende - puffer)


def termintreue_score(tage: int) -> float:
    if tage <= 14:
        return 100.0
    if tage <= 21:
        return 70.0
    if tage <= 28:
        return 30.0
    return 0.0


def reaktionszeit_score(tage: int, nachfragen: float = 0) -> float:
    if tage <= 3:
        s = 100.0
    elif tage <= 7:
        s = 70.0
    else:
        s = max(0.0, 100.0 - (tage - 7) * 10)
    return max(0.0, s - (nachfragen or 0) * 10)


def _begrenzen(wert: float) -> float:
    return max(0.0, min(100.0, wert))


# ── Kategorien ────────────────────────────────────────────────────────────────

def qualitaet_score(q: dict) -> Zahl:
    gesamt = _zahl(q, "produkt")
    if not gesamt or gesamt <= 0:
        return None
    verworfen = _zahl(q, "verworfen")
    gemessen = _zahl(q, "gemessen")

    fehlerquote = _begrenzen(100 - (verworfen or 0) / gesamt * 100)
    if gemessen is None:
        return fehlerquote
    analytauswahl = _begrenzen(gemessen / gesamt * 100)
    return (fehlerquote * config.QUALITAET_ANTEIL_FEHLERQUOTE
            + analytauswahl * config.QUALITAET_ANTEIL_ANALYTAUSWAHL)


def zuverlaessigkeit_score(z: dict) -> Zahl:
    tage = netto_tage(z.get("versand", ""), z.get("eingang", ""),
                      puffer=config.TERMINTREUE_PUFFER)
    return None if tage is None else termintreue_score(tage)


def kosten_score(k: dict, benchmark: Zahl) -> Zahl:
    if k.get("kostenlos"):
        return 100.0
    preis = _zahl(k, "laborpreis")
    if not preis or preis <= 0 or not benchmark or benchmark <= 0:
        return None
    return min(100.0, benchmark / preis * 100)


def service_score(s: dict) -> Zahl:
    teile = []
    berichtet = _zahl(s, "berichtet")
    behoben = _zahl(s, "behoben")
    if berichtet and berichtet > 0:
        # Behebungsrate = behobene / berichtete Fehler
        teile.append(_begrenzen((behoben or 0) / berichtet * 100))
    tage = netto_tage(s.get("anfrage", ""), s.get("antwort", ""))
    if tage is not None:
        teile.append(reaktionszeit_score(tage, _zahl(s, "nachfragen") or 0))
    return sum(teile) / len(teile) if teile else None


# ── Gesamt ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Scores:
    qualitaet: Zahl
    zuverlaessigkeit: Zahl
    kosten: Zahl
    service: Zahl

    def als_dict(self) -> dict:
        return {"qualitaet": self.qualitaet, "zuverlaessigkeit": self.zuverlaessigkeit,
                "kosten": self.kosten, "service": self.service}

    @property
    def gesamt(self) -> Zahl:
        werte = {k: v for k, v in self.als_dict().items() if v is not None}
        gewichte = sum(config.GEWICHTE[k] for k in werte)
        if not gewichte:
            return None
        return sum(config.GEWICHTE[k] * v for k, v in werte.items()) / gewichte


def berechne_scores(eintrag: dict, benchmarks: Optional[dict] = None) -> Scores:
    """Berechnet alle Kategorie-Scores eines Eintrags.

    ``benchmarks``: {produkt: Durchschnittspreis}, siehe :func:`benchmark_tabelle`.
    """
    benchmark = (benchmarks or {}).get(eintrag.get("produkt", ""))
    return Scores(
        qualitaet=qualitaet_score(eintrag.get("qualitaet") or {}),
        zuverlaessigkeit=zuverlaessigkeit_score(eintrag.get("zuverlaessigkeit") or {}),
        kosten=kosten_score(eintrag.get("kosten") or {}, benchmark),
        service=service_score(eintrag.get("service") or {}),
    )


def benchmark_tabelle(daten: dict) -> dict:
    """Durchschnittlicher Laborpreis (> 0) je Produkt über alle Labore."""
    preise = defaultdict(list)
    for eintraege in daten.values():
        for e in eintraege:
            p = _zahl(e.get("kosten") or {}, "laborpreis")
            if p and p > 0:
                preise[e.get("produkt", "")].append(p)
    return {prod: sum(ps) / len(ps) for prod, ps in preise.items()}


def gewicht_rollierend(index: int, anzahl: int, schema: str = "linear") -> float:
    i = index + 1
    if schema == "linear":
        return float(i)
    if schema == "sqrt":
        return i ** 0.5
    return 0.7 if index < anzahl // 2 else 1.3


def gewichteter_schnitt(scores: list, schema: str = "linear") -> Zahl:
    """Neuere Werte (weiter hinten in der Liste) zählen stärker."""
    gueltig = [(i, s) for i, s in enumerate(scores) if s is not None]
    if not gueltig:
        return None
    n = len(scores)
    tw = sum(gewicht_rollierend(i, n, schema) for i, _ in gueltig)
    ws = sum(gewicht_rollierend(i, n, schema) * s for i, s in gueltig)
    return ws / tw


def durchschnitt(werte: Iterable[Zahl]) -> Zahl:
    liste = [w for w in werte if w is not None]
    return sum(liste) / len(liste) if liste else None


def status(score: Zahl) -> tuple:
    """-> (schluessel, text) mit schluessel in ok / warn / bad / none."""
    if score is None:
        return "none", "Keine Daten"
    if score >= config.GRENZE_FREIGEGEBEN:
        return "ok", "Freigegeben"
    if score >= config.GRENZE_BEOBACHTUNG:
        return "warn", "Beobachtung"
    return "bad", "Gesperrt"


# ── Plausibilitätsprüfung ─────────────────────────────────────────────────────

def plausibilitaet(eintrag: dict) -> list:
    """Liefert eine Liste von Hinweistexten zu unstimmigen Eingaben."""
    hinweise = []
    q = eintrag.get("qualitaet") or {}
    z = eintrag.get("zuverlaessigkeit") or {}
    s = eintrag.get("service") or {}
    gesamt, gemessen, verworfen = _zahl(q, "produkt"), _zahl(q, "gemessen"), _zahl(q, "verworfen")

    if not eintrag.get("produkt", "").strip():
        hinweise.append("Kein Produkt angegeben.")
    if gesamt is not None and gemessen is not None and gemessen > gesamt:
        hinweise.append("Mehr gemessene als gesamte Analyten im Produkt.")
    if gesamt is not None and verworfen is not None and verworfen > gesamt:
        hinweise.append("Mehr verworfene als gesamte Analyten im Produkt.")
    for name, (von, bis) in {
        "Eingangsdatum": (z.get("versand"), z.get("eingang")),
        "Antwortdatum": (s.get("anfrage"), s.get("antwort")),
    }.items():
        d1, d2 = parse_datum(von), parse_datum(bis)
        if d1 and d2 and d2 < d1:
            hinweise.append(f"{name} liegt vor dem Startdatum – Score kann nicht berechnet werden.")
    for feld in ("versand", "eingang"):
        if z.get(feld) and parse_datum(z[feld]) is None:
            hinweise.append(f"Datum '{z[feld]}' ist ungültig (Format TT.MM.JJJJ).")
    for feld in ("anfrage", "antwort"):
        if s.get(feld) and parse_datum(s[feld]) is None:
            hinweise.append(f"Datum '{s[feld]}' ist ungültig (Format TT.MM.JJJJ).")
    berichtet, behoben = _zahl(s, "berichtet"), _zahl(s, "behoben")
    if berichtet is not None and behoben is not None and behoben > berichtet:
        hinweise.append("Mehr behobene als berichtete Fehler.")
    return hinweise
