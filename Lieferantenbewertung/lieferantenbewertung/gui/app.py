"""Hauptfenster der Lieferantenbewertung."""
from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .. import charts, config, labor_db, scoring
from ..storage import Datenspeicher, Preisspeicher, laenderkuerzel, neue_id
from . import dialoge
from .rund import RundButton, RundFrame, RundListe
from .widgets import (ACCENT, BG, BG2, BORDER, FONT, FONT_B, FONT_H, FONT_SM, STATUS_TEXTFARBEN,
                      TEXT, TEXT2, WHITE, ScrollFrame, button, combobox, eingabe, feld, fmt,
                      karte, tabelle, ttk_stil)

GEWICHT_SCHEMA = "linear"

FORMULAR_FELDER = ("monat", "jahr", "produkt", "konzentration", "pruefnummer",
                   "q_verworfen", "q_gemessen", "q_produkt", "z_versand", "z_eingang",
                   "k_laborpreis", "s_berichtet", "s_behoben", "s_anfrage", "s_antwort", "s_nachfragen")
ZAHL_FELDER = {"q_verworfen": "Verworfene Analyten", "q_gemessen": "Gemessene Analyten",
               "q_produkt": "Gesamte Analyten", "k_laborpreis": "Laborpreis",
               "s_berichtet": "Berichtete Fehler", "s_behoben": "Behobene Fehler",
               "s_nachfragen": "Nachfragen"}


def _gewicht(k):
    return config.GEWICHTE[k]


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
        self.aktuelles_labor = ""
        self.bearbeitungs_id = None
        self._benchmarks = {}

        self.db_ok = False
        self.db_meldung = "Access-DB: nicht konfiguriert"
        if labor_db.aktiviert():
            try:
                labor_db.erstelle_db()
                self.db_ok = True
                self.db_meldung = "Access-DB: verbunden"
            except Exception as err:
                self.db_meldung = f"Access-DB: nicht erreichbar ({err})"

        self._aufbauen()
        self.alles_aktualisieren()

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
        # Statusleiste
        sb = tk.Frame(self, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
        sb.pack(side="bottom", fill="x")
        self.lbl_status = tk.Label(sb, text="", font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w", padx=12)
        self.lbl_status.pack(side="left", fill="x", expand=True)
        tk.Label(sb, text=self.db_meldung, font=FONT_SM, bg=WHITE,
                 fg=ACCENT if self.db_ok else TEXT2, padx=12).pack(side="right")

        self._sidebar()
        tk.Frame(self, bg=BORDER, width=1).pack(side="left", fill="y")

        haupt = tk.Frame(self, bg=BG)
        haupt.pack(side="left", fill="both", expand=True)
        kopf = tk.Frame(haupt, bg=WHITE, height=52)
        kopf.pack(fill="x")
        kopf.pack_propagate(False)
        tk.Frame(kopf, bg=BORDER, height=1).pack(side="bottom", fill="x")
        self.lbl_kopf = tk.Label(kopf, text="Lieferantenbewertung", font=("Segoe UI", 15, "bold"),
                                 bg=WHITE, fg=TEXT, anchor="w")
        self.lbl_kopf.pack(side="left", padx=24, pady=12)

        reiter = tk.Frame(haupt, bg=BG)
        reiter.pack(fill="x", padx=16, pady=(12, 0))
        self.nb = ttk.Notebook(haupt, style="Ohne.TNotebook")
        self.nb.pack(fill="both", expand=True)
        self.tab_eingabe = self._tab_eingabe()
        self.tab_verlauf = self._tab_verlauf()
        self.tab_uebersicht = self._tab_uebersicht()
        self.tab_diagramme = self._tab_diagramme()
        self.tab_preise = self._tab_preise()
        for frame, text in ((self.tab_eingabe, "Monatseingabe"), (self.tab_verlauf, "Verlauf & Score"),
                            (self.tab_uebersicht, "Übersicht"), (self.tab_diagramme, "Diagramme"),
                            (self.tab_preise, "Preisentwicklung")):
            self.nb.add(frame, text=text)
        self._reiter_knoepfe = {}
        for frame in self.nb.tabs():
            text = self.nb.tab(frame, "text")
            b = RundButton(reiter, text, lambda f=frame: self.nb.select(f), art="tab", font=FONT, padx=18, pady=7)
            b.pack(side="left", padx=(0, 6))
            self._reiter_knoepfe[frame] = b
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._reiter_gewechselt())
        self._reiter_gewechselt()

    def _sidebar(self):
        sb = tk.Frame(self, bg=WHITE, width=200)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        tk.Label(sb, text="LABORE", font=("Segoe UI", 7, "bold"), bg=WHITE, fg=TEXT2,
                 anchor="w", padx=16).pack(fill="x", pady=(16, 4))
        button(sb, "Labor löschen", self._labor_loeschen_auswahl, art="sekundaer", font=FONT_SM
               ).pack(fill="x", padx=12, pady=(0, 10), side="bottom")
        button(sb, "+ Labor anlegen", lambda: dialoge.labor_anlegen(self), font=FONT_SM
               ).pack(fill="x", padx=12, pady=(0, 4), side="bottom")
        self.liste = RundListe(sb, auswahl=self._liste_klick, kontext=self._labor_kontextmenue)
        self.liste.pack(fill="both", expand=True, padx=6)

    # ── Tab: Monatseingabe ────────────────────────────────────────────────
    def _tab_eingabe(self):
        p = tk.Frame(self.nb, bg=BG)
        self.formular = {k: tk.StringVar() for k in FORMULAR_FELDER}
        self.k_kostenlos = tk.BooleanVar(value=False)
        f = self.formular

        kopf = tk.Frame(p, bg=BG)
        kopf.pack(fill="x", padx=20, pady=(14, 4))
        tk.Label(kopf, text="Monatliche Dateneingabe", font=FONT_H, bg=BG, fg=TEXT).pack(side="left")
        self.lbl_modus = tk.Label(kopf, text="", font=FONT_SM, bg=BG, fg=ACCENT)
        self.lbl_modus.pack(side="left", padx=16)

        # Kopfdaten
        top = tk.Frame(p, bg=BG)
        top.pack(fill="x", padx=20, pady=6)

        def lbl(text):
            tk.Label(top, text=text, font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left", padx=(0, 4))
        lbl("Monat")
        combobox(top, f["monat"], dialoge.MONAT_WERTE, 4).pack(side="left", padx=(0, 12))
        lbl("Jahr")
        combobox(top, f["jahr"], dialoge.jahr_werte(), 6).pack(side="left", padx=(0, 20))
        lbl("Produkt / Analyt")
        self.cb_produkt = combobox(top, f["produkt"], (), 22, nur_lesen=False)
        self.cb_produkt.pack(side="left", padx=(0, 16))
        self.cb_produkt.bind("<ButtonPress-1>", lambda e: self.cb_produkt.configure(values=self.store.produkte()))
        f["produkt"].trace_add("write", lambda *_: self._preis_vorschlagen())
        lbl("Konzentration")
        eingabe(top, f["konzentration"], 10, bg=WHITE).pack(side="left", padx=(0, 16), ipady=3)
        lbl("Prüfnummer")
        eingabe(top, f["pruefnummer"], 14, bg=WHITE).pack(side="left", ipady=3)

        # Aktionen
        rf = RundFrame(p, radius=18, pad=4)
        rf.pack(fill="x", padx=12, pady=(6, 10))
        bf = rf.inhalt
        button(bf, "  Speichern  ", self.speichern, padx=20, pady=8).pack(side="left", padx=12, pady=8)
        button(bf, "Neu / Felder leeren", self.felder_leeren, art="sekundaer", pady=8).pack(side="left", pady=8)
        button(bf, "📋  Level-Eingabe", self._level_eingabe, art="sekundaer", fg=ACCENT, pady=8
               ).pack(side="left", padx=8, pady=8)
        self.lbl_vorschau = tk.Label(bf, text="", font=FONT_B, bg=WHITE, fg=TEXT2)
        self.lbl_vorschau.pack(side="right", padx=16)

        # Zweispaltig
        spalten = tk.Frame(p, bg=BG)
        spalten.pack(fill="both", expand=True, padx=12, pady=4)
        links = tk.Frame(spalten, bg=BG)
        links.pack(side="left", fill="both", expand=True, padx=(0, 6))
        rechts = tk.Frame(spalten, bg=BG)
        rechts.pack(side="left", fill="both", expand=True, padx=(6, 0))

        qa = int(config.QUALITAET_ANTEIL_FEHLERQUOTE * 100)
        c = karte(links, f"Qualität (Gewicht {_gewicht('qualitaet')})  —  Fehlerquote {qa} %  /  "
                         f"Analytauswahl {100 - qa} %")
        feld(c, "Anzahl verworfener Analyten", f["q_verworfen"])
        feld(c, "Anzahl gemessener Analyten", f["q_gemessen"])
        feld(c, "Anzahl gesamter Analyten im Produkt", f["q_produkt"])
        tk.Frame(c, bg=WHITE, height=6).pack()

        c = karte(links, f"Zuverlässigkeit (Gewicht {_gewicht('zuverlaessigkeit')})  —  Termintreue")
        feld(c, "Versanddatum (Proben versendet)", f["z_versand"], datum=True)
        feld(c, "Eingangsdatum der Werte", f["z_eingang"], datum=True)
        tk.Frame(c, bg=WHITE, height=6).pack()

        c = karte(rechts, f"Kosten (Gewicht {_gewicht('kosten')})")
        self.e_preis = feld(c, "Laborpreis (EUR)", f["k_laborpreis"])
        tk.Checkbutton(c, text="Kostenloses Labor (Score = 100 %)", variable=self.k_kostenlos,
                       font=FONT_SM, bg=WHITE, fg=TEXT2, activebackground=WHITE, cursor="hand2",
                       highlightthickness=0, bd=0,
                       command=self._kostenlos_umschalten).pack(anchor="w", padx=12, pady=(0, 8))

        c = karte(rechts, f"Service (Gewicht {_gewicht('service')})")
        feld(c, "Dem Labor berichtete Fehler", f["s_berichtet"], "1 fehlerhafter Analyt = 1 Fehler")
        feld(c, "Anzahl behobener Fehler", f["s_behoben"])
        feld(c, "Datum Anfrage (E-Mail gesendet)", f["s_anfrage"], datum=True)
        feld(c, "Datum Antwort erhalten", f["s_antwort"], datum=True)
        feld(c, "Anzahl Nachfragen", f["s_nachfragen"], "je −10 %")
        tk.Frame(c, bg=WHITE, height=6).pack()

        c = karte(links, "Kommentar")
        kr = RundFrame(c, bg=BG, radius=10, pad=6)
        kr.pack(fill="x", padx=12, pady=(4, 10))
        self.e_kommentar = tk.Text(kr.inhalt, font=FONT, height=4, relief="flat", bd=0,
                                   highlightthickness=0, bg=BG, wrap="word")
        self.e_kommentar.pack(fill="x")

        for var in self.formular.values():
            var.trace_add("write", lambda *_: self._vorschau())
        self.k_kostenlos.trace_add("write", lambda *_: self._vorschau())
        self.felder_leeren()
        return p

    # ── Tab: Verlauf ──────────────────────────────────────────────────────
    def _tab_verlauf(self):
        frame = tk.Frame(self.nb, bg=BG)
        top = tk.Frame(frame, bg=BG)
        top.pack(fill="x", padx=20, pady=12)
        tk.Label(top, text="Produkt:", font=FONT, bg=BG, fg=TEXT2).pack(side="left")
        self.verlauf_produkt = tk.StringVar(value="Alle")
        self.cb_verlauf_produkt = combobox(top, self.verlauf_produkt, ["Alle"], 22)
        self.cb_verlauf_produkt.pack(side="left", padx=6)
        self.verlauf_produkt.trace_add("write", lambda *_: self.verlauf_aktualisieren())
        self.score_frame = tk.Frame(frame, bg=BG)
        self.score_frame.pack(fill="x", padx=20, pady=(0, 8))

        bf = tk.Frame(frame, bg=BG)
        bf.pack(side="bottom", pady=(0, 10))
        button(bf, "Bearbeiten", self._verlauf_bearbeiten, font=FONT_SM).pack(side="left", padx=4)
        button(bf, "Zu anderem Labor verschieben…", self._verlauf_verschieben, art="sekundaer",
               font=FONT_SM).pack(side="left", padx=4)
        button(bf, "Löschen", self._verlauf_loeschen, art="gefahr", font=FONT_SM).pack(side="left", padx=4)

        self.tree_verlauf = tabelle(frame, {
            "Monat": (75, "center"), "Produkt": (140, "w"), "Konz.": (70, "center"),
            "Prüfnr.": (80, "center"), "Qualität": (80, "center"), "Zuverlässigkeit": (100, "center"),
            "Kosten": (80, "center"), "Service": (80, "center"), "Gesamt": (80, "center"),
            "Status": (110, "center")})
        self.tree_verlauf.bind("<Double-1>", lambda e: self._verlauf_bearbeiten())
        self.tree_verlauf.bind("<Delete>", lambda e: self._verlauf_loeschen())
        return frame

    # ── Tab: Übersicht ────────────────────────────────────────────────────
    def _tab_uebersicht(self):
        frame = tk.Frame(self.nb, bg=BG)
        top = tk.Frame(frame, bg=BG)
        top.pack(fill="x", padx=20, pady=(14, 8))
        tk.Label(top, text="Übersicht", font=FONT_H, bg=BG, fg=TEXT).pack(side="left")
        tk.Label(top, text="Produkt:", font=FONT, bg=BG, fg=TEXT2).pack(side="left", padx=(24, 4))
        self.uebersicht_produkt = tk.StringVar(value="Alle")
        self.cb_uebersicht_produkt = combobox(top, self.uebersicht_produkt, ["Alle"], 20)
        self.cb_uebersicht_produkt.pack(side="left")
        self.uebersicht_produkt.trace_add("write", lambda *_: self.uebersicht_aktualisieren())
        button(top, "📄  Übersicht als PDF", lambda: dialoge.pdf_export(self, "uebersicht"),
               art="sekundaer", fg=ACCENT).pack(side="right")
        button(top, "📋  Detail + Berechnung als PDF", lambda: dialoge.pdf_export(self, "detail"),
               art="sekundaer", fg=ACCENT).pack(side="right", padx=8)
        tk.Label(frame, text="Doppelklick auf eine Zeile öffnet den Eintrag zur Bearbeitung.",
                 font=FONT_SM, bg=BG, fg=TEXT2, anchor="w").pack(fill="x", padx=20, pady=(6, 2))
        self.tree_uebersicht = tabelle(frame, {
            "Prüfnr.": (80, "center"), "Labor": (70, "w"), "Monat": (75, "center"),
            "Produkt": (130, "w"), "Konz.": (65, "center"), "Qualität": (80, "center"),
            "Zuverl.": (80, "center"), "Kosten": (80, "center"), "Service": (80, "center"),
            "Gesamt": (80, "center"), "Status": (110, "center")}, hoehe=24)
        self.tree_uebersicht.bind("<Double-1>", lambda e: self._uebersicht_oeffnen())
        return frame

    # ── Tab: Diagramme ────────────────────────────────────────────────────
    def _tab_diagramme(self):
        frame = tk.Frame(self.nb, bg=BG)
        top = tk.Frame(frame, bg=BG)
        top.pack(fill="x", padx=20, pady=12)
        self.diag_labor = tk.StringVar(value="Alle")
        self.diag_produkt = tk.StringVar(value="Alle")
        tk.Label(top, text="Labor:", font=FONT, bg=BG, fg=TEXT2).pack(side="left")
        self.cb_diag_labor = combobox(top, self.diag_labor, ["Alle"], 18)
        self.cb_diag_labor.pack(side="left", padx=6)
        tk.Label(top, text="Produkt:", font=FONT, bg=BG, fg=TEXT2).pack(side="left", padx=(12, 0))
        self.cb_diag_produkt = combobox(top, self.diag_produkt, ["Alle"], 18)
        self.cb_diag_produkt.pack(side="left", padx=6)
        self.diag_labor.trace_add("write", lambda *_: self.diagramme_aktualisieren())
        self.diag_produkt.trace_add("write", lambda *_: self.diagramme_aktualisieren())
        rd = RundFrame(frame, radius=16, pad=10, fuellen=True)
        rd.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.diag_scroll = ScrollFrame(rd.inhalt)
        self.diag_scroll.pack(fill="both", expand=True)
        return frame

    # ── Tab: Preisentwicklung ─────────────────────────────────────────────
    def _tab_preise(self):
        frame = tk.Frame(self.nb, bg=BG)
        tk.Label(frame, text="Preisentwicklung", font=FONT_H, bg=BG, fg=TEXT, anchor="w"
                 ).pack(fill="x", padx=24, pady=(14, 0))

        ff = tk.Frame(frame, bg=BG)
        ff.pack(fill="x", padx=24, pady=10)
        self.pe_labor = tk.StringVar(value="Alle")
        self.pe_produkt = tk.StringVar(value="Alle")
        tk.Label(ff, text="Labor", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        self.cb_pe_labor = combobox(ff, self.pe_labor, ["Alle"], 16)
        self.cb_pe_labor.pack(side="left", padx=(4, 14))
        tk.Label(ff, text="Produkt", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        self.cb_pe_produkt = combobox(ff, self.pe_produkt, ["Alle"], 22)
        self.cb_pe_produkt.pack(side="left", padx=(4, 14))
        self.pe_labor.trace_add("write", lambda *_: self.preise_aktualisieren())
        self.pe_produkt.trace_add("write", lambda *_: self.preise_aktualisieren())

        rc = RundFrame(frame, radius=16, pad=8, fuellen=True, height=280)
        rc.pack(fill="x", padx=24, pady=(0, 10))
        self.pe_chart = rc.inhalt

        # Manuelle Pflege
        mf = tk.Frame(frame, bg=BG)
        mf.pack(fill="x", padx=24, pady=(0, 6))
        tk.Label(mf, text="Preis manuell eintragen:", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        self.pm_labor, self.pm_produkt, self.pm_preis = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.cb_pm_labor = combobox(mf, self.pm_labor, (), 10)
        self.cb_pm_labor.pack(side="left", padx=6)
        self.cb_pm_produkt = combobox(mf, self.pm_produkt, (), 18, nur_lesen=False)
        self.cb_pm_produkt.pack(side="left", padx=6)
        eingabe(mf, self.pm_preis, 8, bg=WHITE).pack(side="left", padx=6, ipady=3)
        tk.Label(mf, text="€", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        button(mf, "Eintragen", self._preis_manuell, font=FONT_SM).pack(side="left", padx=8)
        button(mf, "Ausgewählte Preisreihe löschen", self._preis_loeschen, art="gefahr",
               font=FONT_SM).pack(side="right")

        self.tree_preise = tabelle(frame, {"Labor": (160, "w"), "Produkt": (220, "w"),
                                           "Preis (€)": (100, "center"), "Datum": (110, "center"),
                                           "Monat": (100, "center")}, hoehe=8)
        self.tree_preise.bind("<<TreeviewSelect>>", self._preis_gewaehlt)
        return frame

    # ══════════════════════════════════════════════════════════════════════
    # Allgemein
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
            messagebox.showwarning("Access-DB",
                                   f"{beschreibung} fehlgeschlagen:\n{err}\n\n"
                                   "Die Daten wurden lokal (JSON) gespeichert.")
            return False

    def alles_aktualisieren(self):
        self._benchmarks = scoring.benchmark_tabelle(self.store.daten)
        self.labor_liste_aktualisieren()
        self.verlauf_aktualisieren()
        self.uebersicht_aktualisieren()
        self._tab_aktualisieren()
        self._vorschau()

    def _reiter_gewechselt(self):
        aktiv = self.nb.select()
        for frame, b in self._reiter_knoepfe.items():
            b.setze_art("tab_aktiv" if frame == aktiv else "tab")
        self._tab_aktualisieren()

    def _tab_aktualisieren(self):
        aktiv = self.nb.select()
        if aktiv == str(self.tab_diagramme):
            self.diagramme_aktualisieren()
        elif aktiv == str(self.tab_preise):
            self.preise_aktualisieren()

    def _scores(self, e):
        return scoring.berechne_scores(e, self._benchmarks)

    # ── Labor-Liste ───────────────────────────────────────────────────────
    def labor_liste_aktualisieren(self):
        zeilen, land = [], None
        for code in self.store.labore():
            if laenderkuerzel(code) != land:
                land = laenderkuerzel(code)
                zeilen.append((None, land))
            zeilen.append((code, code))
        self.liste.setze(zeilen)
        self.liste.markiere(self.aktuelles_labor)

    def _liste_klick(self, code, _event=None):
        if code != self.aktuelles_labor:
            self.labor_waehlen(code, nachfragen=True)

    def labor_waehlen(self, code: str, nachfragen: bool = False) -> bool:
        if nachfragen and self.aktuelles_labor and self._formular_befuellt():
            antwort = dialoge.frage_laborwechsel(self, code)
            if antwort == "abbrechen":
                self.liste.markiere(self.aktuelles_labor)
                return False
            if antwort == "verwerfen":
                self.felder_leeren()
            else:
                self._bearbeitung_setzen(None)  # Werte werden als neuer Eintrag übernommen
        elif nachfragen:
            self.felder_leeren()
        self.aktuelles_labor = code
        self.lbl_kopf.config(text=code)
        self.liste.markiere(code)
        self.verlauf_aktualisieren()
        self._preis_vorschlagen()
        self._vorschau()
        return True

    def _labor_kontextmenue(self, code, event):
        menu = tk.Menu(self, tearoff=0, bg=WHITE, fg=TEXT, activebackground=BG2,
                       activeforeground=ACCENT, font=FONT_SM)
        menu.add_command(label=f"  {code}", state="disabled")
        menu.add_separator()
        menu.add_command(label="  Details anzeigen", command=lambda: dialoge.labor_details(self, code))
        menu.add_command(label="  Stammdaten bearbeiten", command=lambda: dialoge.labor_bearbeiten(self, code))
        if self.db_ok:
            menu.add_command(label="  Änderungsprotokoll", command=lambda: dialoge.aenderungsprotokoll(self, code))
        menu.add_separator()
        menu.add_command(label="  Löschen", command=lambda: self._labor_loeschen(code))
        menu.tk_popup(event.x_root, event.y_root)

    def _labor_loeschen_auswahl(self):
        if self.aktuelles_labor:
            self._labor_loeschen(self.aktuelles_labor)

    def _labor_loeschen(self, code):
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
        if self.aktuelles_labor == code:
            self.aktuelles_labor = ""
            self.lbl_kopf.config(text="Lieferantenbewertung")
            self.felder_leeren()
        self.alles_aktualisieren()
        self.status(f"Labor {code} gelöscht.")

    # ══════════════════════════════════════════════════════════════════════
    # Formular
    # ══════════════════════════════════════════════════════════════════════
    def _bearbeitung_setzen(self, eintrag_id):
        self.bearbeitungs_id = eintrag_id
        if eintrag_id:
            labor, e = self.store.finden(eintrag_id)
            beschreibung = f"{e['produkt']} {e['konzentration']} {e['monat']}".strip() if e else ""
            self.lbl_modus.config(text=f"✎ Bearbeite bestehenden Eintrag: {beschreibung}")
        else:
            self.lbl_modus.config(text="")

    def _formular_befuellt(self) -> bool:
        ignorieren = {"monat", "jahr"}
        if any(v.get().strip() for k, v in self.formular.items() if k not in ignorieren):
            return True
        return bool(self.e_kommentar.get("1.0", "end").strip())

    def felder_leeren(self):
        for k, var in self.formular.items():
            var.set("")
        self.formular["monat"].set(f"{datetime.now().month:02d}")
        self.formular["jahr"].set(str(datetime.now().year))
        self.k_kostenlos.set(False)
        self.e_kommentar.delete("1.0", "end")
        self._bearbeitung_setzen(None)

    def _kostenlos_umschalten(self):
        if self.k_kostenlos.get():
            self.formular["k_laborpreis"].set("0")
            self.e_preis.config(state="disabled")
        else:
            self.e_preis.config(state="normal")

    def _preis_vorschlagen(self):
        """Füllt den Laborpreis mit dem zuletzt hinterlegten Preis, wenn das Feld leer ist."""
        produkt = self.formular["produkt"].get().strip()
        if self.aktuelles_labor and produkt and not self.formular["k_laborpreis"].get().strip():
            preis = self.preise.letzter_preis(self.aktuelles_labor, produkt)
            if preis is not None:
                self.formular["k_laborpreis"].set(f"{preis:.2f}")

    def _eintrag_aus_formular(self) -> dict:
        """Liest das Formular aus. Wirft ValueError bei ungültigen Zahlen."""
        f = self.formular
        z = {}
        for key, name in ZAHL_FELDER.items():
            text = f[key].get().strip()
            z[key] = scoring.parse_zahl(text)
            if text and z[key] is None:
                raise ValueError(f"'{text}' bei „{name}“ ist keine gültige Zahl.")
        return {
            "id": self.bearbeitungs_id or neue_id(),
            "monat": f"{f['jahr'].get()}-{f['monat'].get()}",
            "produkt": f["produkt"].get().strip(),
            "konzentration": f["konzentration"].get().strip(),
            "pruefnummer": f["pruefnummer"].get().strip(),
            "qualitaet": {"verworfen": z["q_verworfen"], "gemessen": z["q_gemessen"],
                          "produkt": z["q_produkt"]},
            "zuverlaessigkeit": {"versand": f["z_versand"].get().strip(),
                                 "eingang": f["z_eingang"].get().strip()},
            "kosten": {"laborpreis": 0.0 if self.k_kostenlos.get() else z["k_laborpreis"],
                       "kostenlos": self.k_kostenlos.get()},
            "service": {"berichtet": z["s_berichtet"], "behoben": z["s_behoben"],
                        "anfrage": f["s_anfrage"].get().strip(), "antwort": f["s_antwort"].get().strip(),
                        "nachfragen": z["s_nachfragen"]},
            "kommentar": self.e_kommentar.get("1.0", "end").strip(),
        }

    def _formular_fuellen(self, eintrag):
        f = self.formular

        def txt(wert):
            if wert is None or wert == "":
                return ""
            if isinstance(wert, float) and wert.is_integer():
                return str(int(wert))
            return str(wert)
        jahr, _, monat = eintrag.get("monat", "").partition("-")
        f["jahr"].set(jahr)
        f["monat"].set(monat)
        for key in ("produkt", "konzentration", "pruefnummer"):
            f[key].set(eintrag.get(key, ""))
        q, z, k, s = (eintrag.get(x) or {} for x in ("qualitaet", "zuverlaessigkeit", "kosten", "service"))
        f["q_verworfen"].set(txt(q.get("verworfen")))
        f["q_gemessen"].set(txt(q.get("gemessen")))
        f["q_produkt"].set(txt(q.get("produkt")))
        f["z_versand"].set(z.get("versand", ""))
        f["z_eingang"].set(z.get("eingang", ""))
        self.k_kostenlos.set(bool(k.get("kostenlos")))
        self._kostenlos_umschalten()
        f["k_laborpreis"].set(txt(k.get("laborpreis")))
        f["s_berichtet"].set(txt(s.get("berichtet")))
        f["s_behoben"].set(txt(s.get("behoben")))
        f["s_anfrage"].set(s.get("anfrage", ""))
        f["s_antwort"].set(s.get("antwort", ""))
        f["s_nachfragen"].set(txt(s.get("nachfragen")))
        self.e_kommentar.delete("1.0", "end")
        self.e_kommentar.insert("1.0", eintrag.get("kommentar", ""))
        self._bearbeitung_setzen(eintrag.get("id"))
        self.nb.select(self.tab_eingabe)

    def _vorschau(self):
        """Live-Anzeige des Scores während der Eingabe."""
        if not hasattr(self, "lbl_vorschau"):
            return
        try:
            e = self._eintrag_aus_formular()
        except (ValueError, tk.TclError):
            self.lbl_vorschau.config(text="Ungültige Zahl", fg=STATUS_TEXTFARBEN["bad"])
            return
        sc = self._scores(e)
        key, text = scoring.status(sc.gesamt)
        if sc.gesamt is None:
            self.lbl_vorschau.config(text="", fg=TEXT2)
        else:
            self.lbl_vorschau.config(
                text=f"Q {fmt(sc.qualitaet)} · Z {fmt(sc.zuverlaessigkeit)} · K {fmt(sc.kosten)} · "
                     f"S {fmt(sc.service)}   →   {sc.gesamt:.1f} {text}",
                fg=STATUS_TEXTFARBEN[key])

    def eintrag_ablegen(self, labor: str, eintrag: dict) -> dict:
        """Speichert in JSON, aktualisiert die Preishistorie und gleicht mit Access ab."""
        eintrag = self.store.eintrag_speichern(labor, eintrag)
        preis = (eintrag.get("kosten") or {}).get("laborpreis")
        if preis and eintrag.get("produkt"):
            self.preise.aktualisieren(labor, eintrag["produkt"], preis, eintrag["monat"])
        if self.db_ok:
            self.db_ausfuehren(lambda: labor_db.bewertung_speichern(labor, eintrag), "Speichern in Access")
        return eintrag

    def speichern(self):
        labor = self.aktuelles_labor
        if not labor:
            messagebox.showwarning("Kein Labor", "Bitte zuerst links ein Labor auswählen.")
            return
        try:
            eintrag = self._eintrag_aus_formular()
        except ValueError as err:
            messagebox.showwarning("Ungültige Eingabe", str(err))
            return
        hinweise = scoring.plausibilitaet(eintrag)
        if hinweise and not messagebox.askyesno(
                "Bitte prüfen", "\n".join(f"• {h}" for h in hinweise) + "\n\nTrotzdem speichern?"):
            return
        doppelt = self.store.duplikat(labor, eintrag)
        if doppelt:
            if not messagebox.askyesno(
                    "Überschreiben?",
                    f"Prüfnummer '{eintrag['pruefnummer']}' ({doppelt['produkt']} {doppelt['konzentration']}, "
                    f"{doppelt['monat']}) existiert bei {labor} bereits. Überschreiben?"):
                return
            if self.bearbeitungs_id and self.bearbeitungs_id != doppelt["id"]:
                self.store.eintrag_loeschen(self.bearbeitungs_id)
            eintrag["id"] = doppelt["id"]
        self.eintrag_ablegen(labor, eintrag)
        self._bearbeitung_setzen(None)  # nächster Klick auf Speichern legt einen neuen Eintrag an
        self.alles_aktualisieren()
        self.status(f"Gespeichert: {labor} · {eintrag['produkt']} {eintrag['konzentration']} · {eintrag['monat']}")

    def _level_eingabe(self):
        if not self.aktuelles_labor:
            messagebox.showwarning("Kein Labor", "Bitte zuerst links ein Labor auswählen.")
            return
        dialoge.level_eingabe(self, self.aktuelles_labor)

    # ══════════════════════════════════════════════════════════════════════
    # Verlauf
    # ══════════════════════════════════════════════════════════════════════
    def verlauf_aktualisieren(self):
        tree = self.tree_verlauf
        tree.delete(*tree.get_children())
        for w in self.score_frame.winfo_children():
            w.destroy()
        labor = self.aktuelles_labor
        if not labor:
            return
        produkte = ["Alle"] + self.store.produkte(labor)
        self.cb_verlauf_produkt.configure(values=produkte)
        if self.verlauf_produkt.get() not in produkte:
            self.verlauf_produkt.set("Alle")
            return  # trace ruft diese Methode erneut auf
        pf = self.verlauf_produkt.get()
        eintraege = [e for _, e in self.store.eintraege(labor) if pf == "Alle" or e["produkt"] == pf]
        scores = [self._scores(e) for e in eintraege]
        gew = scoring.gewichteter_schnitt([s.gesamt for s in scores], GEWICHT_SCHEMA)
        key, status_text = scoring.status(gew)
        for label, wert, farbe in (("Labor", labor, TEXT),
                                   ("Gewichteter Score", fmt(gew), ACCENT),
                                   ("Status", status_text, STATUS_TEXTFARBEN[key]),
                                   ("Einträge", str(len(eintraege)), TEXT)):
            rk = RundFrame(self.score_frame, radius=16, pad=10)
            rk.pack(side="left", padx=(0, 10))
            k = rk.inhalt
            tk.Label(k, text=label, font=FONT_SM, bg=WHITE, fg=TEXT2).pack()
            tk.Label(k, text=wert, font=("Segoe UI", 16, "bold"), bg=WHITE, fg=farbe).pack()
        for e, sc in zip(reversed(eintraege), reversed(scores)):  # neueste oben
            key, st = scoring.status(sc.gesamt)
            tree.insert("", "end", iid=e["id"], tags=(key,), values=(
                e["monat"], e["produkt"], e["konzentration"], e["pruefnummer"],
                fmt(sc.qualitaet), fmt(sc.zuverlaessigkeit), fmt(sc.kosten), fmt(sc.service),
                fmt(sc.gesamt), st))

    def _verlauf_auswahl(self):
        sel = self.tree_verlauf.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Eintrag in der Tabelle auswählen.")
            return None
        return sel[0]

    def _verlauf_bearbeiten(self):
        eid = self._verlauf_auswahl()
        if eid:
            _, e = self.store.finden(eid)
            if e:
                self._formular_fuellen(e)

    def _verlauf_verschieben(self):
        eid = self._verlauf_auswahl()
        if eid:
            dialoge.eintrag_verschieben(self, eid)

    def _verlauf_loeschen(self):
        auswahl = self.tree_verlauf.selection()
        if not auswahl:
            return self._verlauf_auswahl()
        labor = self.aktuelles_labor
        eintraege = [self.store.finden(eid)[1] for eid in auswahl]
        text = "\n".join(f"• {e['monat']}  {e['produkt']} {e['konzentration']}" for e in eintraege if e)
        if not messagebox.askyesno("Löschen", f"{len(auswahl)} Eintrag/Einträge löschen?\n\n{text}"):
            return
        for eid in auswahl:
            e = self.store.eintrag_loeschen(eid)
            if e and self.db_ok:
                self.db_ausfuehren(lambda e=e: labor_db.bewertung_loeschen(labor, e), "Löschen in Access")
            if eid == self.bearbeitungs_id:
                self._bearbeitung_setzen(None)
        self.alles_aktualisieren()
        self.status(f"{len(auswahl)} Eintrag/Einträge gelöscht.")

    # ══════════════════════════════════════════════════════════════════════
    # Übersicht
    # ══════════════════════════════════════════════════════════════════════
    def uebersicht_aktualisieren(self):
        tree = self.tree_uebersicht
        tree.delete(*tree.get_children())
        produkte = ["Alle"] + self.store.produkte()
        self.cb_uebersicht_produkt.configure(values=produkte)
        if self.uebersicht_produkt.get() not in produkte:
            self.uebersicht_produkt.set("Alle")
            return
        pf = self.uebersicht_produkt.get()
        for labor, e in self.store.eintraege():
            if pf != "Alle" and e["produkt"] != pf:
                continue
            sc = self._scores(e)
            key, st = scoring.status(sc.gesamt)
            tree.insert("", "end", iid=e["id"], tags=(key,), values=(
                e["pruefnummer"] or "–", labor, e["monat"], e["produkt"], e["konzentration"],
                fmt(sc.qualitaet), fmt(sc.zuverlaessigkeit), fmt(sc.kosten), fmt(sc.service),
                fmt(sc.gesamt), st))

    def _uebersicht_oeffnen(self):
        sel = self.tree_uebersicht.selection()
        if not sel:
            return
        labor, e = self.store.finden(sel[0])
        if e and (labor == self.aktuelles_labor or self.labor_waehlen(labor, nachfragen=True)):
            self._formular_fuellen(e)

    # ══════════════════════════════════════════════════════════════════════
    # Diagramme
    # ══════════════════════════════════════════════════════════════════════
    def _diagramm_einbetten(self, fig, parent):
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, pady=(0, 8))

    def diagramme_aktualisieren(self):
        labore = ["Alle"] + self.store.labore()
        produkte = ["Alle"] + self.store.produkte()
        self.cb_diag_labor.configure(values=labore)
        self.cb_diag_produkt.configure(values=produkte)
        if self.diag_labor.get() not in labore:
            self.diag_labor.set("Alle")
        if self.diag_produkt.get() not in produkte:
            self.diag_produkt.set("Alle")
        lf, pf = self.diag_labor.get(), self.diag_produkt.get()

        je_labor = {}
        for labor, e in self.store.eintraege(None if lf == "Alle" else lf):
            if pf == "Alle" or e["produkt"] == pf:
                je_labor.setdefault(labor, []).append(e)

        ziel = self.diag_scroll.inhalt
        for w in ziel.winfo_children():
            w.destroy()
        if not je_labor:
            tk.Label(ziel, text="Keine Daten für diese Auswahl.", font=FONT, bg=WHITE, fg=TEXT2).pack(pady=40)
            return
        kennzahlen = charts.labor_kennzahlen(je_labor, self._benchmarks, GEWICHT_SCHEMA)
        self._diagramm_einbetten(charts.score_diagramm(kennzahlen), ziel)
        fig = charts.preis_diagramm(je_labor)
        if fig is not None:
            self._diagramm_einbetten(fig, ziel)

    # ══════════════════════════════════════════════════════════════════════
    # Preise
    # ══════════════════════════════════════════════════════════════════════
    def preise_aktualisieren(self):
        labore = ["Alle"] + self.preise.labore()
        produkte = ["Alle"] + self.preise.produkte()
        self.cb_pe_labor.configure(values=labore)
        self.cb_pe_produkt.configure(values=produkte)
        self.cb_pm_labor.configure(values=self.store.labore())
        self.cb_pm_produkt.configure(values=sorted(set(self.store.produkte()) | set(self.preise.produkte())))
        if self.pe_labor.get() not in labore:
            self.pe_labor.set("Alle")
        if self.pe_produkt.get() not in produkte:
            self.pe_produkt.set("Alle")

        tree = self.tree_preise
        tree.delete(*tree.get_children())
        verlauf = self.preise.verlauf(self.pe_labor.get(), self.pe_produkt.get())
        for (labor, produkt), punkte in verlauf.items():
            for p in reversed(punkte):
                tree.insert("", "end", values=(labor, produkt, f"{p['preis']:.2f}",
                                               p.get("datum", "–"), p.get("monat", "–")))

        for w in self.pe_chart.winfo_children():
            w.destroy()
        if not verlauf:
            tk.Label(self.pe_chart, text="Noch keine Preisdaten. Preise werden beim Speichern automatisch eingetragen.",
                     font=FONT_SM, bg=WHITE, fg=TEXT2).pack(expand=True)
            return
        breite = self.pe_chart.winfo_width()
        fig = charts.preisentwicklung_diagramm(verlauf, max(6, breite / 96) if breite > 10 else 10)
        self._diagramm_einbetten(fig, self.pe_chart)

    def _preis_gewaehlt(self, event=None):
        sel = self.tree_preise.selection()
        if sel:
            werte = self.tree_preise.item(sel[0])["values"]
            self.pm_labor.set(werte[0])
            self.pm_produkt.set(werte[1])
            self.pm_preis.set(werte[2])

    def _preis_manuell(self):
        labor, produkt = self.pm_labor.get().strip(), self.pm_produkt.get().strip()
        preis = scoring.parse_zahl(self.pm_preis.get())
        if not labor or not produkt or not preis or preis <= 0:
            messagebox.showwarning("Fehler", "Bitte Labor, Produkt und einen Preis > 0 angeben.")
            return
        if self.preise.aktualisieren(labor, produkt, preis, datetime.now().strftime("%Y-%m")):
            self.status(f"Preis {preis:.2f} € für {labor} / {produkt} eingetragen.")
        else:
            self.status("Preis unverändert – nichts eingetragen.")
        self.preise_aktualisieren()

    def _preis_loeschen(self):
        sel = self.tree_preise.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Zeile auswählen.")
            return
        labor, produkt = self.tree_preise.item(sel[0])["values"][:2]
        labor, produkt = str(labor), str(produkt)
        if messagebox.askyesno("Löschen", f"Gesamte Preishistorie für {labor} / {produkt} löschen?"):
            self.preise.loeschen(labor, produkt)
            self.preise_aktualisieren()


def main():
    App().mainloop()
