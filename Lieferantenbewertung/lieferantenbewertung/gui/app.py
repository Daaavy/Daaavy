"""
Hauptfenster der Lieferantenbewertung.

Aufbau:
    Seitenleiste links
        ÜBERSICHT – zentrale Seiten für alle Labore (Start, Vergleich, …)
        LABORE    – Klick öffnet die Laborseite mit laborspezifischen Reitern
    Inhalt rechts – jeweils eine Seite
"""
from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

from .. import config, labor_db, scoring
from ..storage import Datenspeicher, Preisspeicher, laenderkuerzel
from . import dialoge
from .rund import RundListe
from .seiten.labor import ERFASSEN, LaborSeite
from .seiten.zentral import ZENTRALE_SEITEN
from .widgets import (ACCENT, BG, BG2, BORDER, FONT_SM, TEXT, TEXT2, WHITE, button,
                      mausrad_installieren, ttk_stil)

SEITE = "seite:"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lieferantenbewertung")
        self.configure(bg=BG)
        self.geometry("1400x860")
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        self._icon_setzen()
        ttk_stil(self)

        self.store = Datenspeicher()
        self.preise = Preisspeicher()
        self.benchmarks = {}
        self.kennzahlen = {}
        self._labornamen = {}
        self.aktiv = SEITE + "StartSeite"

        self.db_ok = False
        self.db_meldung = "nicht konfiguriert"
        if labor_db.aktiviert():
            try:
                labor_db.erstelle_db()
                self.db_ok = True
                self.db_meldung = f"verbunden ({config.ACCESS_DB})"
                self._labornamen = {l["Laborcode"]: l.get("Laborname") or "" for l in labor_db.alle_labore()}
            except Exception as err:
                self.db_meldung = f"nicht erreichbar ({err})"

        self._aufbauen()
        mausrad_installieren(self)
        self._kennzahlen_berechnen()
        self.navigiere(self.aktiv)

    def _icon_setzen(self):
        for name in ("Download.ico", "chromatogram_icon.png"):
            pfad = os.path.join(config.app_dir(), name)
            if not os.path.exists(pfad):
                continue
            try:
                if name.endswith(".ico"):
                    self.iconbitmap(pfad)
                else:
                    self._icon = tk.PhotoImage(file=pfad)
                    self.iconphoto(True, self._icon)
                return
            except tk.TclError:
                pass

    # ══════════════════════════════════════════════════════════════════════
    # Aufbau
    # ══════════════════════════════════════════════════════════════════════
    def _aufbauen(self):
        sb = tk.Frame(self, bg=WHITE)
        sb.pack(side="bottom", fill="x")
        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x")
        self.lbl_status = tk.Label(sb, text="", font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w", padx=12, pady=3)
        self.lbl_status.pack(side="left", fill="x", expand=True)
        tk.Label(sb, text=f"Access-DB: {self.db_meldung}", font=FONT_SM, bg=WHITE,
                 fg=ACCENT if self.db_ok else TEXT2, padx=12).pack(side="right")

        # Seitenleiste
        leiste = tk.Frame(self, bg=WHITE, width=220)
        leiste.pack(side="left", fill="y")
        leiste.pack_propagate(False)
        tk.Label(leiste, text="Lieferanten-\nbewertung", font=("Segoe UI", 13, "bold"), bg=WHITE, fg=TEXT,
                 justify="left", anchor="w").pack(fill="x", padx=18, pady=(18, 10))
        button(leiste, "+ Labor anlegen", lambda: dialoge.labor_anlegen(self), font=FONT_SM
               ).pack(fill="x", padx=14, pady=(0, 14), side="bottom")
        self.nav = RundListe(leiste, auswahl=lambda ziel, _e=None: self.navigiere(ziel),
                             kontext=self._kontextmenue)
        self.nav.pack(fill="both", expand=True, padx=6)
        tk.Frame(self, bg=BORDER, width=1).pack(side="left", fill="y")

        # Seiten (übereinander gestapelt, die aktive liegt oben)
        self.stapel = tk.Frame(self, bg=BG)
        self.stapel.pack(side="left", fill="both", expand=True)
        self.stapel.grid_rowconfigure(0, weight=1)
        self.stapel.grid_columnconfigure(0, weight=1)
        self.seiten = {}
        for klasse in ZENTRALE_SEITEN:
            seite = klasse(self.stapel, self)
            seite.grid(row=0, column=0, sticky="nsew")
            self.seiten[SEITE + klasse.__name__] = seite
        self.labor_seite = LaborSeite(self.stapel, self)
        self.labor_seite.grid(row=0, column=0, sticky="nsew")

    # ══════════════════════════════════════════════════════════════════════
    # Navigation
    # ══════════════════════════════════════════════════════════════════════
    def labor_liste_aktualisieren(self):
        zeilen = [(None, "ÜBERSICHT")]
        zeilen += [(SEITE + k.__name__, k.titel) for k in ZENTRALE_SEITEN]
        zeilen.append((None, ""))
        zeilen.append((None, "LABORE"))
        land = None
        for code in self.store.labore():
            if laenderkuerzel(code) != land:
                land = laenderkuerzel(code)
                zeilen.append((None, f"  {land}"))
            zeilen.append((code, code))
        self.nav.setze(zeilen)
        self.nav.markiere(self.aktiv)

    def navigiere(self, ziel: str):
        if ziel.startswith(SEITE):
            self.aktiv = ziel
            seite = self.seiten[ziel]
            seite.tkraise()
            seite.aktualisieren()
            seite.nach_oben()
            self.title(f"Lieferantenbewertung – {seite.titel}")
            self.labor_liste_aktualisieren()
        else:
            self.labor_oeffnen(ziel)

    def labor_oeffnen(self, code: str, eintrag: dict = None, reiter: str = None) -> bool:
        """Zeigt die Laborseite; optional mit einem Eintrag im Bearbeitungsformular."""
        ls = self.labor_seite
        if code != ls.code and ls.code:
            if ls.eingabe.befuellt():
                antwort = dialoge.frage_laborwechsel(self, code)
                if antwort == "abbrechen":
                    self.nav.markiere(self.aktiv)
                    return False
                if antwort == "verwerfen":
                    ls.eingabe.leeren()
                else:
                    ls.eingabe.neu_beginnen()
            else:
                ls.eingabe.leeren()
        self.aktiv = code
        ls.tkraise()
        ls.anzeigen(code, reiter=ERFASSEN if eintrag else reiter)
        if eintrag:
            ls.eintrag_bearbeiten(eintrag)
        self.title(f"Lieferantenbewertung – {code}")
        self.nav.markiere(code)
        return True

    # Für Dialoge, die noch den alten Namen verwenden
    labor_waehlen = labor_oeffnen

    @property
    def formular(self):
        return self.labor_seite.eingabe.formular

    @property
    def k_kostenlos(self):
        return self.labor_seite.eingabe.k_kostenlos

    def labor_name(self, code: str) -> str:
        return self._labornamen.get(code, "")

    def _kontextmenue(self, ziel, event):
        if ziel.startswith(SEITE):
            return
        menu = tk.Menu(self, tearoff=0, bg=WHITE, fg=TEXT, activebackground=BG2,
                       activeforeground=ACCENT, font=FONT_SM)
        menu.add_command(label=f"  {ziel}", state="disabled")
        menu.add_separator()
        menu.add_command(label="  Öffnen", command=lambda: self.labor_oeffnen(ziel))
        menu.add_command(label="  Neue Bewertung", command=lambda: self.labor_oeffnen(ziel, reiter=ERFASSEN))
        menu.add_command(label="  Stammdaten bearbeiten", command=lambda: dialoge.labor_bearbeiten(self, ziel))
        menu.add_separator()
        menu.add_command(label="  Löschen", command=lambda: self.labor_loeschen(ziel))
        menu.tk_popup(event.x_root, event.y_root)

    # ══════════════════════════════════════════════════════════════════════
    # Daten
    # ══════════════════════════════════════════════════════════════════════
    def status(self, text: str) -> None:
        self.lbl_status.config(text=f"{datetime.now():%H:%M}  {text}")

    def db_ausfuehren(self, funktion, beschreibung: str) -> bool:
        """Führt eine Access-Aktion aus. Fehler werden gemeldet, die JSON-Daten bleiben gültig."""
        if not self.db_ok:
            return False
        try:
            funktion()
            return True
        except Exception as err:
            messagebox.showwarning("Access-DB", f"{beschreibung} fehlgeschlagen:\n{err}\n\n"
                                                "Die Daten wurden lokal (JSON) gespeichert.")
            return False

    def _kennzahlen_berechnen(self):
        self.benchmarks = scoring.benchmark_tabelle(self.store.daten)
        je_labor = {code: [e for _, e in self.store.eintraege(code)] for code in self.store.labore()}
        self.kennzahlen = scoring.labor_kennzahlen(je_labor, self.benchmarks)

    def alles_aktualisieren(self):
        """Nach jeder Datenänderung: Kennzahlen neu berechnen und sichtbare Seite neu zeichnen."""
        self._kennzahlen_berechnen()
        if self.aktiv.startswith(SEITE):
            self.seiten[self.aktiv].aktualisieren()
        elif self.aktiv in self.store.daten:
            self.labor_seite.aktualisieren()
        else:
            self.navigiere(SEITE + "StartSeite")
            return
        self.labor_liste_aktualisieren()

    def eintrag_ablegen(self, labor: str, eintrag: dict) -> dict:
        """Speichert in JSON, aktualisiert die Preishistorie und gleicht mit Access ab."""
        eintrag = self.store.eintrag_speichern(labor, eintrag)
        preis = (eintrag.get("kosten") or {}).get("laborpreis")
        if preis and eintrag.get("produkt"):
            self.preise.aktualisieren(labor, eintrag["produkt"], preis, eintrag["monat"])
        if self.db_ok:
            self.db_ausfuehren(lambda: labor_db.bewertung_speichern(labor, eintrag), "Speichern in Access")
        return eintrag

    def labor_loeschen(self, code):
        anzahl = len(self.store.daten.get(code, []))
        if not messagebox.askyesno("Labor löschen",
                                   f"Labor '{code}' mit {anzahl} Einträgen wirklich löschen?\n\n"
                                   "(Eine Sicherung bleibt in labordaten.json.bak erhalten.)"):
            return
        if self.db_ok:
            def db():
                lab = labor_db.labor_nach_code(code)
                if lab:
                    labor_db.labor_loeschen(lab["LaborID"])
            self.db_ausfuehren(db, "Labor in Access deaktivieren")
        self.store.labor_loeschen(code)
        if self.labor_seite.code == code:
            self.labor_seite.code = ""
            self.labor_seite.eingabe.leeren()
        self.navigiere(SEITE + "StartSeite")
        self._kennzahlen_berechnen()
        self.seiten[self.aktiv].aktualisieren()
        self.status(f"Labor {code} gelöscht.")


def main():
    App().mainloop()
