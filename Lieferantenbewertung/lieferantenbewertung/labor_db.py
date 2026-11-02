"""
Anbindung an die Access-Datenbank (optional, über pyodbc).

Tabellen: tbl_Labore, tbl_Ansprechpartner, tbl_Bewertung, tbl_Aenderungslog.
Fehlende Tabellen und Spalten werden von :func:`erstelle_db` angelegt.

Der Pfad kommt aus ``config.ini`` (``[pfade] access_db``). Ist er leer, ist
die Anbindung deaktiviert und das Programm arbeitet nur mit den JSON-Dateien.
"""
from __future__ import annotations

import getpass
import os
from contextlib import contextmanager
from datetime import datetime

from . import config

# Spalten, die per UPDATE geändert werden dürfen (Schutz vor SQL-Injection,
# da Spaltennamen nicht als Parameter übergeben werden können)
LABOR_FELDER = {"Laborcode", "Laborname", "Adresse", "Telefon", "Notiz"}
AP_FELDER = {"Name", "Email", "Telefon", "Funktion"}

TABELLEN = {
    "tbl_Labore": """
        CREATE TABLE tbl_Labore (
            LaborID      AUTOINCREMENT PRIMARY KEY,
            Laborcode    TEXT(20),
            Laborname    TEXT(255),
            Adresse      LONGTEXT,
            Telefon      TEXT(50),
            Notiz        LONGTEXT,
            Aktiv        YESNO,
            ErstelltAm   DATETIME,
            ErstelltVon  TEXT(100)
        )""",
    "tbl_Ansprechpartner": """
        CREATE TABLE tbl_Ansprechpartner (
            APId        AUTOINCREMENT PRIMARY KEY,
            LaborID     LONG,
            Name        TEXT(255),
            Email       TEXT(255),
            Telefon     TEXT(50),
            Funktion    TEXT(255),
            Aktiv       YESNO,
            ErstelltAm  DATETIME
        )""",
    "tbl_Aenderungslog": """
        CREATE TABLE tbl_Aenderungslog (
            LogID         AUTOINCREMENT PRIMARY KEY,
            Tabelle       TEXT(50),
            ReferenzID    LONG,
            Laborcode     TEXT(20),
            Feld          TEXT(100),
            AlterWert     LONGTEXT,
            NeuerWert     LONGTEXT,
            Aktion        TEXT(20),
            GeaendertAm   DATETIME,
            GeaendertVon  TEXT(100)
        )""",
    "tbl_Bewertung": """
        CREATE TABLE tbl_Bewertung (
            BewertungID         AUTOINCREMENT PRIMARY KEY,
            EintragID           TEXT(32),
            Laborcode           TEXT(20),
            Monat               TEXT(7),
            Produkt             TEXT(255),
            Konzentration       TEXT(50),
            Pruefnummer         TEXT(50),
            Q_Verworfen         DOUBLE,
            Q_Gesamt            DOUBLE,
            Q_Gemessen          DOUBLE,
            Q_ProduktAnalyten   DOUBLE,
            Z_Versanddatum      TEXT(12),
            Z_Eingangsdatum     TEXT(12),
            K_Laborpreis        DOUBLE,
            K_Kostenlos         YESNO,
            S_FehlerAnzahl      DOUBLE,
            S_BehobeneAnzahl    DOUBLE,
            S_AnfrageDatum      TEXT(12),
            S_AntwortDatum      TEXT(12),
            S_Nachfragen        DOUBLE,
            Kommentar           LONGTEXT,
            GespeichertAm       DATETIME,
            GespeichertVon      TEXT(100)
        )""",
}

# Spalten, die in älteren Datenbanken in tbl_Bewertung noch fehlen
NACHRUEST_SPALTEN = {
    "EintragID": "TEXT(32)",
    "Konzentration": "TEXT(50)",
    "Pruefnummer": "TEXT(50)",
    "K_Kostenlos": "YESNO",
}


class DatenbankFehler(Exception):
    pass


def aktiviert() -> bool:
    return bool(config.ACCESS_DB)


def _benutzer() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unbekannt"


def get_conn():
    if not aktiviert():
        raise DatenbankFehler("Keine Access-Datenbank konfiguriert (config.ini → [pfade] access_db).")
    if not os.path.exists(config.ACCESS_DB):
        raise DatenbankFehler(f"Datenbank nicht gefunden: {config.ACCESS_DB}")
    try:
        import pyodbc
    except ImportError as e:
        raise DatenbankFehler("Python-Paket 'pyodbc' ist nicht installiert.") from e
    return pyodbc.connect(
        r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={config.ACCESS_DB};"
    )


@contextmanager
def verbindung():
    """Verbindung mit automatischem Commit bzw. Rollback bei Fehlern."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def db_verfuegbar() -> bool:
    try:
        get_conn().close()
        return True
    except Exception:
        return False


def _zeilen_als_dicts(cur) -> list:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Struktur ──────────────────────────────────────────────────────────────────

def erstelle_db() -> None:
    """Legt fehlende Tabellen und Spalten an."""
    with verbindung() as conn:
        cur = conn.cursor()
        vorhanden = {row.table_name for row in cur.tables(tableType="TABLE")}
        for name, sql in TABELLEN.items():
            if name not in vorhanden:
                cur.execute(sql)
        if "tbl_Bewertung" in vorhanden:
            spalten = {row.column_name for row in cur.columns(table="tbl_Bewertung")}
            for spalte, typ in NACHRUEST_SPALTEN.items():
                if spalte not in spalten:
                    cur.execute(f"ALTER TABLE tbl_Bewertung ADD COLUMN {spalte} {typ}")


def log_aenderung(conn, tabelle, ref_id, laborcode, feld, alt, neu, aktion="UPDATE"):
    conn.execute("""
        INSERT INTO tbl_Aenderungslog
            (Tabelle, ReferenzID, Laborcode, Feld, AlterWert, NeuerWert, Aktion, GeaendertAm, GeaendertVon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (tabelle, ref_id or 0, laborcode, feld,
          "" if alt is None else str(alt), "" if neu is None else str(neu),
          aktion, datetime.now(), _benutzer()))


def _letzte_id(cur) -> int:
    cur.execute("SELECT @@IDENTITY")
    return cur.fetchone()[0]


# ── Labore ────────────────────────────────────────────────────────────────────

def labor_anlegen(laborcode, laborname="", adresse="", telefon="", notiz="") -> int:
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tbl_Labore (Laborcode, Laborname, Adresse, Telefon, Notiz, Aktiv, ErstelltAm, ErstelltVon)
            VALUES (?, ?, ?, ?, ?, True, ?, ?)
        """, (laborcode, laborname or laborcode, adresse, telefon, notiz, datetime.now(), _benutzer()))
        labor_id = _letzte_id(cur)
        log_aenderung(conn, "tbl_Labore", labor_id, laborcode, "ANLAGE",
                      "", f"{laborcode} / {laborname}", "INSERT")
        return labor_id


def labor_bearbeiten(labor_id, felder_neu: dict) -> None:
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("SELECT Laborcode, Laborname, Adresse, Telefon, Notiz FROM tbl_Labore WHERE LaborID=?",
                    (labor_id,))
        row = cur.fetchone()
        if not row:
            return
        alt = dict(zip(["Laborcode", "Laborname", "Adresse", "Telefon", "Notiz"], row))
        for feld, neu in felder_neu.items():
            if feld not in LABOR_FELDER:
                raise ValueError(f"Unbekanntes Feld: {feld}")
            if str(alt.get(feld) or "") != str(neu or ""):
                cur.execute(f"UPDATE tbl_Labore SET {feld}=? WHERE LaborID=?", (neu, labor_id))
                log_aenderung(conn, "tbl_Labore", labor_id, alt["Laborcode"], feld, alt.get(feld), neu)


def labor_loeschen(labor_id) -> None:
    """Deaktiviert ein Labor (wird nicht physisch gelöscht)."""
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("SELECT Laborcode FROM tbl_Labore WHERE LaborID=?", (labor_id,))
        row = cur.fetchone()
        if not row:
            return
        cur.execute("UPDATE tbl_Labore SET Aktiv=False WHERE LaborID=?", (labor_id,))
        log_aenderung(conn, "tbl_Labore", labor_id, row[0], "LÖSCHUNG", row[0], "", "DELETE")


def alle_labore() -> list:
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT LaborID, Laborcode, Laborname, Adresse, Telefon, Notiz
            FROM tbl_Labore WHERE Aktiv=True ORDER BY Laborcode
        """)
        return _zeilen_als_dicts(cur)


def labor_nach_code(laborcode):
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT LaborID, Laborcode, Laborname, Adresse, Telefon, Notiz
            FROM tbl_Labore WHERE Aktiv=True AND Laborcode=?
        """, (laborcode,))
        rows = _zeilen_als_dicts(cur)
        return rows[0] if rows else None


# ── Ansprechpartner ───────────────────────────────────────────────────────────

def ap_anlegen(labor_id, laborcode, name, email="", telefon="", funktion="") -> None:
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tbl_Ansprechpartner (LaborID, Name, Email, Telefon, Funktion, Aktiv, ErstelltAm)
            VALUES (?, ?, ?, ?, ?, True, ?)
        """, (labor_id, name, email, telefon, funktion, datetime.now()))
        ap_id = _letzte_id(cur)
        log_aenderung(conn, "tbl_Ansprechpartner", ap_id, laborcode,
                      "AP-ANLAGE", "", f"{name} / {email}", "INSERT")


def ap_bearbeiten(ap_id, laborcode, felder_neu: dict) -> None:
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("SELECT Name, Email, Telefon, Funktion FROM tbl_Ansprechpartner WHERE APId=?", (ap_id,))
        row = cur.fetchone()
        if not row:
            return
        alt = dict(zip(["Name", "Email", "Telefon", "Funktion"], row))
        for feld, neu in felder_neu.items():
            if feld not in AP_FELDER:
                raise ValueError(f"Unbekanntes Feld: {feld}")
            if str(alt.get(feld) or "") != str(neu or ""):
                cur.execute(f"UPDATE tbl_Ansprechpartner SET {feld}=? WHERE APId=?", (neu, ap_id))
                log_aenderung(conn, "tbl_Ansprechpartner", ap_id, laborcode, f"AP.{feld}", alt.get(feld), neu)


def ap_loeschen(ap_id, laborcode) -> None:
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("SELECT Name FROM tbl_Ansprechpartner WHERE APId=?", (ap_id,))
        row = cur.fetchone()
        cur.execute("UPDATE tbl_Ansprechpartner SET Aktiv=False WHERE APId=?", (ap_id,))
        log_aenderung(conn, "tbl_Ansprechpartner", ap_id, laborcode,
                      "AP-LÖSCHUNG", row[0] if row else "?", "", "DELETE")


def aps_fuer_labor(labor_id) -> list:
    with verbindung() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT APId, Name, Email, Telefon, Funktion
            FROM tbl_Ansprechpartner
            WHERE LaborID=? AND Aktiv=True ORDER BY Name
        """, (labor_id,))
        return _zeilen_als_dicts(cur)


def aenderungslog(laborcode=None, limit=100) -> list:
    limit = int(limit)
    sql = (f"SELECT TOP {limit} GeaendertAm, Laborcode, Tabelle, Feld, AlterWert, NeuerWert, "
           f"Aktion, GeaendertVon FROM tbl_Aenderungslog")
    with verbindung() as conn:
        cur = conn.cursor()
        if laborcode:
            cur.execute(sql + " WHERE Laborcode=? ORDER BY GeaendertAm DESC", (laborcode,))
        else:
            cur.execute(sql + " ORDER BY GeaendertAm DESC")
        return _zeilen_als_dicts(cur)


# ── Bewertungen ───────────────────────────────────────────────────────────────

def _bewertung_werte(labor: str, e: dict) -> tuple:
    q, z, k, s = (e.get(x) or {} for x in ("qualitaet", "zuverlaessigkeit", "kosten", "service"))
    return (
        e.get("id", ""), labor, e.get("monat", ""), e.get("produkt", ""),
        e.get("konzentration", ""), e.get("pruefnummer", ""),
        q.get("verworfen"), q.get("gesamt"), q.get("gemessen"), q.get("produkt"),
        z.get("versand", ""), z.get("eingang", ""),
        k.get("laborpreis"), bool(k.get("kostenlos")),
        s.get("berichtet"), s.get("behoben"),
        s.get("anfrage", ""), s.get("antwort", ""), s.get("nachfragen"),
        e.get("kommentar", ""), datetime.now(), _benutzer(),
    )


_SPALTEN = ("EintragID", "Laborcode", "Monat", "Produkt", "Konzentration", "Pruefnummer",
            "Q_Verworfen", "Q_Gesamt", "Q_Gemessen", "Q_ProduktAnalyten",
            "Z_Versanddatum", "Z_Eingangsdatum", "K_Laborpreis", "K_Kostenlos",
            "S_FehlerAnzahl", "S_BehobeneAnzahl", "S_AnfrageDatum", "S_AntwortDatum",
            "S_Nachfragen", "Kommentar", "GespeichertAm", "GespeichertVon")


def _bewertung_suchen(cur, labor: str, e: dict):
    """Sucht zuerst über die Eintrags-ID, sonst über die fachlichen Schlüssel
    (für Datensätze, die vor Version 2 angelegt wurden)."""
    if e.get("id"):
        cur.execute("SELECT BewertungID FROM tbl_Bewertung WHERE EintragID=?", (e["id"],))
        row = cur.fetchone()
        if row:
            return row[0]
    cur.execute("""
        SELECT BewertungID FROM tbl_Bewertung
        WHERE Laborcode=? AND Monat=? AND Produkt=?
          AND (EintragID IS NULL OR EintragID='')
          AND IIf(Konzentration IS NULL, '', Konzentration)=?
          AND IIf(Pruefnummer IS NULL, '', Pruefnummer)=?
    """, (labor, e.get("monat", ""), e.get("produkt", ""),
          e.get("konzentration", ""), e.get("pruefnummer", "")))
    row = cur.fetchone()
    return row[0] if row else None


def bewertung_speichern(labor: str, eintrag: dict) -> None:
    """Legt eine Bewertung an oder aktualisiert sie (Schlüssel: Eintrags-ID)."""
    werte = _bewertung_werte(labor, eintrag)
    with verbindung() as conn:
        cur = conn.cursor()
        vorhandene_id = _bewertung_suchen(cur, labor, eintrag)
        if vorhandene_id:
            zuweisung = ", ".join(f"{s}=?" for s in _SPALTEN)
            cur.execute(f"UPDATE tbl_Bewertung SET {zuweisung} WHERE BewertungID=?",
                        werte + (vorhandene_id,))
            log_aenderung(conn, "tbl_Bewertung", vorhandene_id, labor,
                          "BEWERTUNG", "", f"{eintrag.get('monat')} / {eintrag.get('produkt')}", "UPDATE")
        else:
            platzhalter = ", ".join("?" for _ in _SPALTEN)
            cur.execute(f"INSERT INTO tbl_Bewertung ({', '.join(_SPALTEN)}) VALUES ({platzhalter})", werte)
            neue_id = _letzte_id(cur)
            log_aenderung(conn, "tbl_Bewertung", neue_id, labor,
                          "BEWERTUNG", "", f"{eintrag.get('monat')} / {eintrag.get('produkt')}", "INSERT")


def bewertung_loeschen(labor: str, eintrag: dict) -> None:
    with verbindung() as conn:
        cur = conn.cursor()
        bewertung_id = _bewertung_suchen(cur, labor, eintrag)
        if not bewertung_id:
            return
        cur.execute("DELETE FROM tbl_Bewertung WHERE BewertungID=?", (bewertung_id,))
        log_aenderung(conn, "tbl_Bewertung", bewertung_id, labor, "BEWERTUNG",
                      f"{eintrag.get('monat')} / {eintrag.get('produkt')}", "", "DELETE")


def alle_bewertungen(labor=None) -> list:
    with verbindung() as conn:
        cur = conn.cursor()
        if labor:
            cur.execute("SELECT * FROM tbl_Bewertung WHERE Laborcode=? ORDER BY Monat DESC", (labor,))
        else:
            cur.execute("SELECT * FROM tbl_Bewertung ORDER BY Monat DESC")
        return _zeilen_als_dicts(cur)
