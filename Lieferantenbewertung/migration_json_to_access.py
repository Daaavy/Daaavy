"""
Überträgt alle Einträge aus labordaten.json in die Access-Datenbank.

Kann gefahrlos mehrfach ausgeführt werden: vorhandene Einträge werden
aktualisiert (Schlüssel ist die Eintrags-ID), nicht doppelt angelegt.
"""
import sys

from lieferantenbewertung import config, labor_db
from lieferantenbewertung.storage import Datenspeicher


def beenden(code=0):
    if sys.stdin and sys.stdin.isatty():
        input("\nEnter drücken zum Beenden...")
    sys.exit(code)


def main():
    print("=" * 60)
    print("Migration: labordaten.json -> Access-DB")
    print("=" * 60)

    store = Datenspeicher()
    eintraege = store.eintraege()
    print(f"JSON: {len(eintraege)} Einträge in {len(store.daten)} Laboren ({config.DATA_FILE})")
    if not eintraege:
        print("Nichts zu übertragen.")
        beenden(0)

    print("\nPrüfe Datenbank...")
    try:
        labor_db.erstelle_db()
    except Exception as e:
        print(f"FEHLER: {e}")
        print("\nMögliche Ursachen:")
        print("  - Pfad in config.ini ([pfade] access_db) fehlt oder ist falsch")
        print("  - Microsoft Access Driver bzw. pyodbc nicht installiert")
        print("  - Datenbankdatei gesperrt")
        beenden(1)
    print(f"Datenbank OK: {config.ACCESS_DB}")

    print("\nÜbertrage Daten...")
    ok = fehler = 0
    for labor, e in eintraege:
        beschreibung = f"{labor} / {e['monat']} / {e['produkt']} {e['konzentration']}".strip()
        try:
            labor_db.bewertung_speichern(labor, e)
            print(f"  OK:     {beschreibung}")
            ok += 1
        except Exception as err:
            print(f"  FEHLER: {beschreibung}: {err}")
            fehler += 1

    print(f"\n{'=' * 60}\nFertig: {ok} übertragen, {fehler} Fehler")
    beenden(1 if fehler else 0)


if __name__ == "__main__":
    main()
