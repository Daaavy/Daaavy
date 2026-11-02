"""Laborseite: alles, was genau ein Labor betrifft."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from ... import charts, labor_db, scoring
from .. import dialoge
from ..rund import RundFrame
from ..widgets import (ACCENT, BG, FONT, FONT_B, FONT_SM, TEXT, TEXT2, WHITE, ScrollFrame, button,
                       fmt, tabelle)
from .basis import (Reiter, abschnitt, diagramm_einbetten, filter_feld, kachel, leeren, score_farbe,
                    status_pille, werte_setzen)
from .eingabe import Eingabe

ALLE = "Alle"
UEBERBLICK, ERFASSEN, EINTRAEGE, PREISE, STAMMDATEN = (
    "Überblick", "Bewertung erfassen", "Einträge", "Preise", "Stammdaten")


class LaborSeite(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.code = ""

        # Kopf
        kopf = tk.Frame(self, bg=BG)
        kopf.pack(fill="x", padx=24, pady=(18, 4))
        links = tk.Frame(kopf, bg=BG)
        links.pack(side="left")
        zeile = tk.Frame(links, bg=BG)
        zeile.pack(anchor="w")
        self.lbl_code = tk.Label(zeile, text="", font=("Segoe UI", 22, "bold"), bg=BG, fg=TEXT)
        self.lbl_code.pack(side="left")
        self.pille_rahmen = tk.Frame(zeile, bg=BG)
        self.pille_rahmen.pack(side="left", padx=12)
        self.lbl_unter = tk.Label(links, text="", font=FONT_SM, bg=BG, fg=TEXT2)
        self.lbl_unter.pack(anchor="w")
        rechts = tk.Frame(kopf, bg=BG)
        rechts.pack(side="right")
        score = tk.Frame(rechts, bg=BG)
        score.pack(side="right", padx=20)
        self.lbl_score = tk.Label(score, text="", font=("Segoe UI", 26, "bold"), bg=BG)
        self.lbl_score.pack(anchor="e")
        tk.Label(score, text="Gesamtscore (neuere Werte zählen mehr)", font=FONT_SM, bg=BG,
                 fg=TEXT2).pack(anchor="e")

        # Reiter
        self.reiter = Reiter(self, bei_wechsel=self._reiter_gewechselt)
        self.reiter.pack(fill="both", expand=True)
        self.ueberblick = ScrollFrame(self.reiter.stapel, bg=BG)
        self.eingabe = Eingabe(self.reiter.stapel, app, lambda: self.code,
                               nach_speichern=lambda: None)
        self.eintraege = tk.Frame(self.reiter.stapel, bg=BG)
        self.preise = tk.Frame(self.reiter.stapel, bg=BG)
        self.stammdaten = ScrollFrame(self.reiter.stapel, bg=BG)
        self._eintraege_aufbauen()
        self._preise_aufbauen()
        for name, frame in ((UEBERBLICK, self.ueberblick), (ERFASSEN, self.eingabe),
                            (EINTRAEGE, self.eintraege), (PREISE, self.preise),
                            (STAMMDATEN, self.stammdaten)):
            self.reiter.hinzufuegen(name, frame)

    # ── Steuerung ─────────────────────────────────────────────────────────
    def anzeigen(self, code, reiter=None):
        neu = code != self.code
        self.code = code
        if reiter:
            self.reiter.zeige(reiter)
        elif neu:
            self.reiter.zeige(UEBERBLICK)
        self.aktualisieren()

    def neue_bewertung(self):
        """Leeres Formular öffnen (nachfragen, falls noch Werte eingetragen sind)."""
        if not self.eingabe.geaendert() or messagebox.askyesno(
                "Neue Bewertung", "Das Formular enthält noch Werte. Leeren und neu beginnen?"):
            self.eingabe.leeren()
        self.reiter.zeige(ERFASSEN)

    def eintrag_bearbeiten(self, eintrag):
        self.eingabe.fuellen(eintrag)
        self.reiter.zeige(ERFASSEN)

    def _reiter_gewechselt(self, name):
        if self.code:
            self._reiter_aktualisieren(name)

    def aktualisieren(self):
        if not self.code:
            return
        k = self.app.kennzahlen.get(self.code) or {"g": None, "n": 0, "letzter_monat": ""}
        self.lbl_code.config(text=self.code)
        leeren(self.pille_rahmen)
        status_pille(self.pille_rahmen, k["g"]).pack()
        unter = f"{k['n']} Bewertungen"
        if k.get("letzter_monat"):
            unter += f"  ·  letzte Bewertung {k['letzter_monat']}"
        name = self.app.labor_name(self.code)
        self.lbl_unter.config(text=f"{name}  ·  {unter}" if name else unter)
        self.lbl_score.config(text=fmt(k["g"]), fg=score_farbe(k["g"]))
        self.eingabe.preis_vorschlagen()
        self.eingabe.vorschau()
        self._reiter_aktualisieren(self.reiter.aktiv)

    def _reiter_aktualisieren(self, name):
        {UEBERBLICK: self._ueberblick_neu, EINTRAEGE: self._eintraege_neu,
         PREISE: self._preise_neu, STAMMDATEN: self._stammdaten_neu}.get(name, lambda: None)()

    # ── Überblick ─────────────────────────────────────────────────────────
    def _ueberblick_neu(self):
        p = self.ueberblick.inhalt
        leeren(p)
        eintraege = [e for _, e in self.app.store.eintraege(self.code)]
        if not eintraege:
            rf = RundFrame(p, radius=16, pad=20)
            rf.pack(fill="x", padx=24, pady=10)
            tk.Label(rf.inhalt, text="Für dieses Labor gibt es noch keine Bewertungen.", font=FONT_B,
                     bg=WHITE, fg=TEXT).pack(anchor="w")
            button(rf.inhalt, "＋  Erste Bewertung erfassen", self.neue_bewertung).pack(anchor="w", pady=(10, 0))
            return
        k = scoring.labor_kennzahlen({self.code: eintraege}, self.app.benchmarks)[self.code]

        reihe = tk.Frame(p, bg=BG)
        reihe.pack(fill="x", padx=24, pady=(4, 0))
        for label, key in (("Qualität", "q"), ("Zuverlässigkeit", "z"), ("Kosten", "k"), ("Service", "s")):
            kachel(reihe, label, fmt(k[key]), score_farbe(k[key]), breite=13)
        grund = scoring.hauptgrund(eintraege, self.app.benchmarks)
        if grund:
            rf = RundFrame(p, radius=16, pad=12)
            rf.pack(fill="x", padx=24, pady=(10, 0))
            tk.Label(rf.inhalt, text=f"Größter Punktabzug: {grund['name']}  (ca. {grund['verlust']:.0f} Punkte)",
                     font=FONT_B, bg=WHITE, fg=TEXT, anchor="w").pack(fill="x")
            tk.Label(rf.inhalt, text=grund["text"], font=FONT, bg=WHITE, fg=TEXT2, anchor="w",
                     justify="left", wraplength=1000).pack(fill="x", pady=(2, 0))

        diagramme = tk.Frame(p, bg=BG)
        diagramme.pack(fill="x", padx=24, pady=(12, 0))
        links = RundFrame(diagramme, radius=16, pad=8)
        links.pack(side="left", fill="both", padx=(0, 10))
        diagramm_einbetten(charts.kategorie_diagramm(k, 4.6), links.inhalt, fill="both")
        rechts = RundFrame(diagramme, radius=16, pad=8)
        rechts.pack(side="left", fill="both", expand=True)
        diagramm_einbetten(charts.labor_verlauf_diagramm(k, 7.5), rechts.inhalt, fill="both", expand=True)

        abschnitt(p, "Nach Produkt")
        tree = tabelle(p, {"Produkt": (180, "w"), "Bewertungen": (90, "center"), "Qualität": (80, "center"),
                           "Zuverl.": (80, "center"), "Kosten": (80, "center"), "Service": (80, "center"),
                           "Gesamt": (80, "center"), "Status": (110, "center")},
                       hoehe=max(2, len(self.app.store.produkte(self.code))), fest=True, padx=24)
        je_produkt = {}
        for e in eintraege:
            je_produkt.setdefault(e["produkt"] or "(kein Produkt)", []).append(e)
        for produkt, liste in sorted(je_produkt.items()):
            sc = [scoring.berechne_scores(e, self.app.benchmarks) for e in liste]
            g = scoring.durchschnitt(s.gesamt for s in sc)
            key, st = scoring.status(g)
            tree.insert("", "end", tags=(key,), values=(
                produkt, len(liste), fmt(scoring.durchschnitt(s.qualitaet for s in sc)),
                fmt(scoring.durchschnitt(s.zuverlaessigkeit for s in sc)),
                fmt(scoring.durchschnitt(s.kosten for s in sc)),
                fmt(scoring.durchschnitt(s.service for s in sc)), fmt(g), st))

        hinweise = [(e, h) for e in eintraege for h in scoring.plausibilitaet(e)]
        if hinweise:
            abschnitt(p, "Datenhinweise")
            rf = RundFrame(p, radius=16, pad=10)
            rf.pack(fill="x", padx=24, pady=(0, 20))
            for e, h in hinweise:
                z = tk.Label(rf.inhalt, text=f"→  {e['produkt']} {e['konzentration']} · {e['monat']}:  {h}",
                             font=FONT, bg=WHITE, fg=ACCENT, anchor="w", cursor="hand2")
                z.pack(fill="x", pady=1)
                z.bind("<Button-1>", lambda ev, e=e: self.eintrag_bearbeiten(e))
        else:
            tk.Frame(p, bg=BG, height=20).pack()

    # ── Einträge ──────────────────────────────────────────────────────────
    def _eintraege_aufbauen(self):
        p = self.eintraege
        f = tk.Frame(p, bg=BG)
        f.pack(fill="x", padx=24, pady=(4, 8))
        self.e_produkt = tk.StringVar(value=ALLE)
        self.cb_e_produkt = filter_feld(f, "Produkt", self.e_produkt, [ALLE], 20)
        self.e_produkt.trace_add("write", lambda *_: self._eintraege_tabelle())
        bf = tk.Frame(p, bg=BG)
        bf.pack(side="bottom", fill="x", padx=24, pady=(0, 12))
        button(bf, "Bearbeiten", self._bearbeiten, font=FONT_SM).pack(side="left", padx=(0, 6))
        button(bf, "Zu anderem Labor verschieben…", self._verschieben, art="sekundaer",
               font=FONT_SM).pack(side="left", padx=6)
        button(bf, "Löschen", self._loeschen, art="gefahr", font=FONT_SM).pack(side="left", padx=6)
        tk.Label(bf, text="Tipp: Doppelklick zum Bearbeiten, Entf zum Löschen", font=FONT_SM, bg=BG,
                 fg=TEXT2).pack(side="right")
        self.tree = tabelle(p, {
            "Monat": (75, "center"), "Produkt": (140, "w"), "Konz.": (70, "center"), "Prüfnr.": (80, "center"),
            "Qualität": (80, "center"), "Zuverlässigkeit": (100, "center"), "Kosten": (80, "center"),
            "Service": (80, "center"), "Gesamt": (80, "center"), "Status": (110, "center")}, padx=24)
        self.tree.bind("<Double-1>", lambda e: self._bearbeiten())
        self.tree.bind("<Delete>", lambda e: self._loeschen())

    def _eintraege_neu(self):
        if not werte_setzen(self.cb_e_produkt, self.e_produkt, [ALLE] + self.app.store.produkte(self.code)):
            self._eintraege_tabelle()

    def _eintraege_tabelle(self):
        self.tree.delete(*self.tree.get_children())
        pf = self.e_produkt.get()
        for _, e in reversed(self.app.store.eintraege(self.code)):  # neueste oben
            if pf != ALLE and e["produkt"] != pf:
                continue
            sc = scoring.berechne_scores(e, self.app.benchmarks)
            key, st = scoring.status(sc.gesamt)
            self.tree.insert("", "end", iid=e["id"], tags=(key,), values=(
                e["monat"], e["produkt"], e["konzentration"], e["pruefnummer"],
                fmt(sc.qualitaet), fmt(sc.zuverlaessigkeit), fmt(sc.kosten), fmt(sc.service),
                fmt(sc.gesamt), st))

    def _auswahl(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Eintrag in der Tabelle auswählen.")
        return sel

    def _bearbeiten(self):
        sel = self._auswahl()
        if sel:
            _, e = self.app.store.finden(sel[0])
            if e:
                self.eintrag_bearbeiten(e)

    def _verschieben(self):
        sel = self._auswahl()
        if sel:
            dialoge.eintrag_verschieben(self.app, sel[0])

    def _loeschen(self):
        sel = self._auswahl()
        if not sel:
            return
        eintraege = [self.app.store.finden(eid)[1] for eid in sel]
        text = "\n".join(f"• {e['monat']}  {e['produkt']} {e['konzentration']}" for e in eintraege if e)
        if not messagebox.askyesno("Löschen", f"{len(sel)} Eintrag/Einträge löschen?\n\n{text}"):
            return
        for eid in sel:
            e = self.app.store.eintrag_loeschen(eid)
            if e and self.app.db_ok:
                self.app.db_ausfuehren(lambda e=e: labor_db.bewertung_loeschen(self.code, e), "Löschen in Access")
            if eid == self.eingabe.bearbeitungs_id:
                self.eingabe.neu_beginnen()
        self.app.alles_aktualisieren()
        self.app.status(f"{len(sel)} Eintrag/Einträge gelöscht.")

    # ── Preise ────────────────────────────────────────────────────────────
    def _preise_aufbauen(self):
        p = self.preise
        rc = RundFrame(p, radius=16, pad=8, fuellen=True, height=290)
        rc.pack(fill="x", padx=24, pady=(4, 10))
        self.preis_chart = rc.inhalt
        self.preis_tree = tabelle(p, {"Produkt": (240, "w"), "Preis (€)": (100, "center"),
                                      "Datum": (110, "center"), "Monat": (100, "center")}, padx=24)
        tk.Label(p, text="Preise anderer Labore vergleichen: links unter Übersicht → Preise",
                 font=FONT_SM, bg=BG, fg=TEXT2, anchor="w").pack(fill="x", padx=28, pady=(0, 10))

    def _preise_neu(self):
        verlauf = self.app.preise.verlauf(self.code)
        self.preis_tree.delete(*self.preis_tree.get_children())
        for (_, produkt), punkte in verlauf.items():
            for pkt in reversed(punkte):
                self.preis_tree.insert("", "end", values=(produkt, f"{pkt['preis']:.2f}",
                                                          pkt.get("datum", "–"), pkt.get("monat", "–")))
        leeren(self.preis_chart)
        if not verlauf:
            tk.Label(self.preis_chart, text="Für dieses Labor sind noch keine Preise hinterlegt.",
                     font=FONT_SM, bg=WHITE, fg=TEXT2).pack(expand=True)
            return
        breite = self.preis_chart.winfo_width()
        diagramm_einbetten(charts.preisentwicklung_diagramm(verlauf, max(6, breite / 96) if breite > 10 else 12),
                           self.preis_chart)

    # ── Stammdaten ────────────────────────────────────────────────────────
    def _stammdaten_neu(self):
        p = self.stammdaten.inhalt
        leeren(p)
        app, code = self.app, self.code
        rf = RundFrame(p, radius=16, pad=16)
        rf.pack(fill="x", padx=24, pady=(4, 10))
        f = rf.inhalt

        def zeile(label, wert):
            z = tk.Frame(f, bg=WHITE)
            z.pack(fill="x", pady=3)
            tk.Label(z, text=label, font=FONT_SM, bg=WHITE, fg=TEXT2, width=18, anchor="w").pack(side="left")
            tk.Label(z, text=wert or "–", font=FONT, bg=WHITE, fg=TEXT, anchor="w", justify="left",
                     wraplength=600).pack(side="left")

        zeile("Laborcode", code)
        zeile("Produkte", ", ".join(app.store.produkte(code)))
        lab, aps = None, []
        if app.db_ok:
            try:
                lab = labor_db.labor_nach_code(code)
                aps = labor_db.aps_fuer_labor(lab["LaborID"]) if lab else []
            except Exception as err:
                zeile("Access-DB", f"Fehler: {err}")
        if lab:
            for feld in ("Laborname", "Adresse", "Telefon", "Notiz"):
                zeile(feld, lab.get(feld))
        elif not app.db_ok:
            tk.Label(f, text="Name, Adresse und Ansprechpartner werden in der Access-Datenbank gepflegt "
                             "(config.ini → access_db).", font=FONT_SM, bg=WHITE, fg=TEXT2,
                     anchor="w").pack(fill="x", pady=(8, 0))

        if aps:
            abschnitt(p, "Ansprechpartner")
            for ap in aps:
                a = RundFrame(p, radius=14, pad=10)
                a.pack(fill="x", padx=24, pady=(0, 6))
                tk.Label(a.inhalt, text=f"{ap['Name']}  ·  {ap.get('Funktion') or ''}", font=FONT_B,
                         bg=WHITE, fg=TEXT).pack(anchor="w")
                tk.Label(a.inhalt, text=f"{ap.get('Email') or ''}   {ap.get('Telefon') or ''}", font=FONT_SM,
                         bg=WHITE, fg=TEXT2).pack(anchor="w")

        bf = tk.Frame(p, bg=BG)
        bf.pack(fill="x", padx=24, pady=(10, 20))
        if app.db_ok:
            button(bf, "Stammdaten bearbeiten", lambda: (dialoge.labor_bearbeiten(app, code), self.aktualisieren())
                   ).pack(side="left", padx=(0, 8))
            button(bf, "Änderungsprotokoll", lambda: dialoge.aenderungsprotokoll(app, code),
                   art="sekundaer").pack(side="left", padx=(0, 8))
        button(bf, "Labor löschen", lambda: app.labor_loeschen(code), art="gefahr").pack(side="right")
