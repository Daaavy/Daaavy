"""Zentrale Seiten: betreffen alle Labore (Start, Vergleich, Bewertungen, Preise, Berichte)."""
from __future__ import annotations

import os
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

from ... import charts, config, pdf_export, scoring
from ..rund import RundFrame
from ..widgets import (ACCENT, BG, FONT, FONT_B, FONT_SM, STATUS_TEXTFARBEN, TEXT, TEXT2, WHITE,
                       button, combobox, eingabe, fmt, tabelle)
from .basis import (Seite, abschnitt, diagramm_einbetten, filter_feld, kachel, leeren, score_farbe,
                    seitenkopf, werte_setzen)

ALLE = "Alle"


def _klickbar(widget, befehl):
    """Macht ein Widget und alle Kinder klickbar."""
    widget.configure(cursor="hand2")
    widget.bind("<Button-1>", lambda e: befehl())
    for kind in widget.winfo_children():
        _klickbar(kind, befehl)


# ══════════════════════════════════════════════════════════════════════════════
# Start
# ══════════════════════════════════════════════════════════════════════════════

class StartSeite(Seite):
    titel = "Start"

    def __init__(self, parent, app):
        super().__init__(parent, app, scroll=True)

    def aktualisieren(self):
        leeren(self.inhalt)
        app, p = self.app, self.inhalt
        kz = app.kennzahlen
        anzahl = sum(k["n"] for k in kz.values())
        seitenkopf(p, "Start", f"Stand {datetime.now():%d.%m.%Y}  ·  {len(kz)} Labore  ·  {anzahl} Bewertungen")

        status_zahl = {"ok": 0, "warn": 0, "bad": 0, "none": 0}
        for k in kz.values():
            status_zahl[scoring.status(k["g"])[0]] += 1
        reihe = tk.Frame(p, bg=BG)
        reihe.pack(fill="x", padx=24, pady=(6, 0))
        kachel(reihe, "Labore", str(len(kz)), breite=12)
        kachel(reihe, "Bewertungen", str(anzahl), breite=12)
        kachel(reihe, "Freigegeben", str(status_zahl["ok"]), STATUS_TEXTFARBEN["ok"], breite=12)
        kachel(reihe, "Beobachtung", str(status_zahl["warn"]), STATUS_TEXTFARBEN["warn"], breite=12)
        kachel(reihe, "Gesperrt", str(status_zahl["bad"]), STATUS_TEXTFARBEN["bad"], breite=12)

        # Ampel aller Labore
        abschnitt(p, "Alle Labore auf einen Blick  –  Klick öffnet das Labor")
        raster = tk.Frame(p, bg=BG)
        raster.pack(fill="x", padx=24)
        spalten = 7
        for i, code in enumerate(app.store.labore()):
            k = kz.get(code)
            raster.grid_columnconfigure(i % spalten, weight=1, uniform="kachel")
            rf = RundFrame(raster, radius=16, pad=10, rand=score_farbe(k["g"]) if k and k["g"] is not None else None
                           or "#E2E8F0")
            rf.grid(row=i // spalten, column=i % spalten, padx=(0, 8), pady=(0, 8), sticky="ew")
            t = rf.inhalt
            tk.Label(t, text=code, font=FONT_B, bg=WHITE, fg=TEXT, anchor="w").pack(anchor="w")
            tk.Label(t, text=fmt(k["g"]) if k else "–", font=("Segoe UI", 17, "bold"), bg=WHITE,
                     fg=score_farbe(k["g"] if k else None), anchor="w").pack(anchor="w")
            tk.Label(t, text=scoring.status(k["g"] if k else None)[1], font=FONT_SM, bg=WHITE,
                     fg=TEXT2, anchor="w").pack(anchor="w")
            _klickbar(rf, lambda c=code: app.labor_oeffnen(c))

        # Zwei Spalten: Handlungsbedarf | Datenhinweise
        zeile = tk.Frame(p, bg=BG)
        zeile.pack(fill="both", expand=True, padx=24, pady=(10, 20))
        zeile.grid_columnconfigure(0, weight=1, uniform="sp")
        zeile.grid_columnconfigure(1, weight=1, uniform="sp")
        self._handlungsbedarf(zeile).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._datenhinweise(zeile).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    def _liste_karte(self, parent, titel, untertitel):
        rf = RundFrame(parent, radius=16, pad=12)
        tk.Label(rf.inhalt, text=titel, font=FONT_B, bg=WHITE, fg=TEXT, anchor="w").pack(fill="x")
        tk.Label(rf.inhalt, text=untertitel, font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w").pack(fill="x", pady=(0, 8))
        return rf

    def _zeile(self, parent, links, rechts, farbe, befehl):
        z = RundFrame(parent, bg=BG, rand=BG, radius=12, pad=6)
        z.pack(fill="x", pady=2)
        tk.Label(z.inhalt, text=links, font=FONT, bg=BG, fg=TEXT, anchor="w", justify="left",
                 wraplength=600).pack(side="left", fill="x", expand=True)
        tk.Label(z.inhalt, text=rechts, font=FONT_B, bg=BG, fg=farbe).pack(side="right", padx=(8, 4))
        _klickbar(z, befehl)

    def _handlungsbedarf(self, parent):
        app = self.app
        rf = self._liste_karte(parent, "Labore unter Beobachtung",
                               f"Score unter {config.GRENZE_FREIGEGEBEN} – und was am meisten Punkte kostet")
        kritisch = sorted(((k["g"], code, k) for code, k in app.kennzahlen.items()
                           if k["g"] is not None and k["g"] < config.GRENZE_FREIGEGEBEN))
        if not kritisch:
            tk.Label(rf.inhalt, text="Alle Labore sind freigegeben. 👍", font=FONT, bg=WHITE,
                     fg=TEXT2).pack(anchor="w")
        for g, code, k in kritisch:
            grund = scoring.hauptgrund([e for _, e in app.store.eintraege(code)], app.benchmarks)
            text = code
            if grund:
                text = (f"{code}  ·  {grund['name']}: {grund['text']}\n"
                        f"Kostet ca. {grund['verlust']:.0f} Punkte.")
            self._zeile(rf.inhalt, text, f"{g:.1f}  {scoring.status(g)[1]}", score_farbe(g),
                        lambda c=code: app.labor_oeffnen(c))
        return rf

    def _datenhinweise(self, parent):
        app = self.app
        rf = self._liste_karte(parent, "Datenhinweise", "Unstimmige Eingaben – Klick öffnet den Eintrag zur Korrektur")
        hinweise = [(labor, e, h) for labor, e in app.store.eintraege() for h in scoring.plausibilitaet(e)]
        if not hinweise:
            tk.Label(rf.inhalt, text="Keine Auffälligkeiten gefunden.", font=FONT, bg=WHITE,
                     fg=TEXT2).pack(anchor="w")
        for labor, e, h in hinweise[:15]:
            text = f"{labor} · {e['produkt']} {e['konzentration']} · {e['monat']}\n{h}"
            self._zeile(rf.inhalt, text, "→", ACCENT,
                        lambda l=labor, e=e: app.labor_oeffnen(l, eintrag=e))
        if len(hinweise) > 15:
            tk.Label(rf.inhalt, text=f"… und {len(hinweise) - 15} weitere", font=FONT_SM, bg=WHITE,
                     fg=TEXT2).pack(anchor="w", pady=(4, 0))
        return rf


# ══════════════════════════════════════════════════════════════════════════════
# Vergleich
# ══════════════════════════════════════════════════════════════════════════════

class VergleichSeite(Seite):
    titel = "Vergleich"

    def __init__(self, parent, app):
        super().__init__(parent, app, scroll=True)
        p = self.inhalt
        seitenkopf(p, "Vergleich", "Alle Labore im direkten Vergleich – Doppelklick in der Rangliste öffnet das Labor")
        f = tk.Frame(p, bg=BG)
        f.pack(fill="x", padx=24, pady=(4, 6))
        self.jahr, self.produkt = tk.StringVar(value=ALLE), tk.StringVar(value=ALLE)
        self.cb_jahr = filter_feld(f, "Jahr", self.jahr, [ALLE], 8)
        self.cb_produkt = filter_feld(f, "Produkt", self.produkt, [ALLE], 20)
        self.jahr.trace_add("write", lambda *_: self._neu())
        self.produkt.trace_add("write", lambda *_: self._neu())

        abschnitt(p, "Rangliste")
        self.tree = tabelle(p, {"Rang": (50, "center"), "Labor": (90, "w"), "Bewertungen": (90, "center"),
                                "Qualität": (80, "center"), "Zuverl.": (80, "center"),
                                "Kosten": (80, "center"), "Service": (80, "center"),
                                "Gesamt": (80, "center"), "Status": (110, "center")},
                            hoehe=10, fest=True, padx=24)
        self.tree.bind("<Double-1>", lambda e: self._oeffnen())
        abschnitt(p, "Diagramme")
        rf = RundFrame(p, radius=16, pad=10)
        rf.pack(fill="x", padx=24, pady=(0, 20))
        self.diagramme = rf.inhalt

    def aktualisieren(self):
        a = werte_setzen(self.cb_jahr, self.jahr, [ALLE] + self.app.store.jahre())
        b = werte_setzen(self.cb_produkt, self.produkt, [ALLE] + self.app.store.produkte())
        if not (a or b):
            self._neu()

    def _neu(self):
        jahr, produkt = self.jahr.get(), self.produkt.get()
        je_labor = {}
        for labor, e in self.app.store.eintraege():
            if (jahr == ALLE or e["monat"].startswith(jahr)) and (produkt == ALLE or e["produkt"] == produkt):
                je_labor.setdefault(labor, []).append(e)
        kz = scoring.labor_kennzahlen(je_labor, self.app.benchmarks)

        self.tree.delete(*self.tree.get_children())
        rangfolge = sorted(kz.items(), key=lambda x: -(x[1]["g"] if x[1]["g"] is not None else -1))
        for rang, (code, k) in enumerate(rangfolge, start=1):
            key, st = scoring.status(k["g"])
            self.tree.insert("", "end", iid=code, tags=(key,), values=(
                rang, code, k["n"], fmt(k["q"]), fmt(k["z"]), fmt(k["k"]), fmt(k["s"]), fmt(k["g"]), st))
        self.tree.configure(height=max(3, min(len(rangfolge), 15)))

        leeren(self.diagramme)
        if not kz:
            tk.Label(self.diagramme, text="Keine Daten für diese Auswahl.", font=FONT, bg=WHITE,
                     fg=TEXT2).pack(pady=30)
            return
        diagramm_einbetten(charts.score_diagramm(kz), self.diagramme, fill="x")
        fig = charts.preis_diagramm(je_labor)
        if fig is not None:
            diagramm_einbetten(fig, self.diagramme, fill="x", pady=(10, 0))

    def _oeffnen(self):
        sel = self.tree.selection()
        if sel:
            self.app.labor_oeffnen(sel[0])


# ══════════════════════════════════════════════════════════════════════════════
# Alle Bewertungen
# ══════════════════════════════════════════════════════════════════════════════

class BewertungenSeite(Seite):
    titel = "Alle Bewertungen"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        seitenkopf(self, "Alle Bewertungen", "Doppelklick öffnet den Eintrag beim jeweiligen Labor zur Bearbeitung")
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=24, pady=(4, 8))
        self.filter = {k: tk.StringVar(value=ALLE) for k in ("labor", "produkt", "jahr", "status")}
        self.cbs = {
            "labor": filter_feld(f, "Labor", self.filter["labor"], [ALLE], 10),
            "produkt": filter_feld(f, "Produkt", self.filter["produkt"], [ALLE], 18),
            "jahr": filter_feld(f, "Jahr", self.filter["jahr"], [ALLE], 8),
            "status": filter_feld(f, "Status", self.filter["status"],
                                  [ALLE, "Freigegeben", "Beobachtung", "Gesperrt", "Keine Daten"], 12),
        }
        self.lbl_anzahl = tk.Label(f, text="", font=FONT_SM, bg=BG, fg=TEXT2)
        self.lbl_anzahl.pack(side="right")
        for v in self.filter.values():
            v.trace_add("write", lambda *_: self._neu())
        self.tree = tabelle(self, {
            "Labor": (70, "w"), "Monat": (75, "center"), "Produkt": (130, "w"), "Konz.": (65, "center"),
            "Prüfnr.": (80, "center"), "Qualität": (80, "center"), "Zuverl.": (80, "center"),
            "Kosten": (80, "center"), "Service": (80, "center"), "Gesamt": (80, "center"),
            "Status": (110, "center")}, padx=24)
        self.tree.bind("<Double-1>", lambda e: self._oeffnen())

    def aktualisieren(self):
        s = self.app.store
        geaendert = [werte_setzen(self.cbs["labor"], self.filter["labor"], [ALLE] + s.labore()),
                     werte_setzen(self.cbs["produkt"], self.filter["produkt"], [ALLE] + s.produkte()),
                     werte_setzen(self.cbs["jahr"], self.filter["jahr"], [ALLE] + s.jahre())]
        if not any(geaendert):
            self._neu()

    def _neu(self):
        f = {k: v.get() for k, v in self.filter.items()}
        self.tree.delete(*self.tree.get_children())
        anzahl = 0
        for labor, e in self.app.store.eintraege(None if f["labor"] == ALLE else f["labor"]):
            if f["produkt"] != ALLE and e["produkt"] != f["produkt"]:
                continue
            if f["jahr"] != ALLE and not e["monat"].startswith(f["jahr"]):
                continue
            sc = scoring.berechne_scores(e, self.app.benchmarks)
            key, st = scoring.status(sc.gesamt)
            if f["status"] != ALLE and st != f["status"]:
                continue
            anzahl += 1
            self.tree.insert("", "end", iid=e["id"], tags=(key,), values=(
                labor, e["monat"], e["produkt"], e["konzentration"], e["pruefnummer"] or "–",
                fmt(sc.qualitaet), fmt(sc.zuverlaessigkeit), fmt(sc.kosten), fmt(sc.service),
                fmt(sc.gesamt), st))
        self.lbl_anzahl.config(text=f"{anzahl} Bewertungen")

    def _oeffnen(self):
        sel = self.tree.selection()
        if sel:
            labor, e = self.app.store.finden(sel[0])
            if e:
                self.app.labor_oeffnen(labor, eintrag=e)


# ══════════════════════════════════════════════════════════════════════════════
# Preise
# ══════════════════════════════════════════════════════════════════════════════

class PreiseSeite(Seite):
    titel = "Preise"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        seitenkopf(self, "Preise", "Preisentwicklung aller Labore – Preise werden beim Speichern automatisch übernommen")
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=24, pady=(4, 8))
        self.labor, self.produkt = tk.StringVar(value=ALLE), tk.StringVar(value=ALLE)
        self.cb_labor = filter_feld(f, "Labor", self.labor, [ALLE], 10)
        self.cb_produkt = filter_feld(f, "Produkt", self.produkt, [ALLE], 20)
        self.labor.trace_add("write", lambda *_: self._neu())
        self.produkt.trace_add("write", lambda *_: self._neu())

        rc = RundFrame(self, radius=16, pad=8, fuellen=True, height=290)
        rc.pack(fill="x", padx=24, pady=(0, 10))
        self.chart = rc.inhalt

        mf = tk.Frame(self, bg=BG)
        mf.pack(fill="x", padx=24, pady=(0, 8))
        tk.Label(mf, text="Preis manuell eintragen:", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        self.pm_labor, self.pm_produkt, self.pm_preis = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.cb_pm_labor = combobox(mf, self.pm_labor, (), 10, bg=WHITE)
        self.cb_pm_labor.pack(side="left", padx=6)
        self.cb_pm_produkt = combobox(mf, self.pm_produkt, (), 18, nur_lesen=False, bg=WHITE)
        self.cb_pm_produkt.pack(side="left", padx=6)
        eingabe(mf, self.pm_preis, 8, bg=WHITE).pack(side="left", padx=6)
        tk.Label(mf, text="€", font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left")
        button(mf, "Eintragen", self._manuell, font=FONT_SM).pack(side="left", padx=8)
        button(mf, "Ausgewählte Preisreihe löschen", self._loeschen, art="gefahr", font=FONT_SM).pack(side="right")

        self.tree = tabelle(self, {"Labor": (160, "w"), "Produkt": (220, "w"), "Preis (€)": (100, "center"),
                                   "Datum": (110, "center"), "Monat": (100, "center")}, hoehe=8, padx=24)
        self.tree.bind("<<TreeviewSelect>>", self._gewaehlt)

    def aktualisieren(self):
        pr = self.app.preise
        self.cb_pm_labor.configure(values=self.app.store.labore())
        self.cb_pm_produkt.configure(values=sorted(set(self.app.store.produkte()) | set(pr.produkte())))
        a = werte_setzen(self.cb_labor, self.labor, [ALLE] + pr.labore())
        b = werte_setzen(self.cb_produkt, self.produkt, [ALLE] + pr.produkte())
        if not (a or b):
            self._neu()

    def _neu(self):
        verlauf = self.app.preise.verlauf(self.labor.get(), self.produkt.get())
        self.tree.delete(*self.tree.get_children())
        for (labor, produkt), punkte in verlauf.items():
            for pkt in reversed(punkte):
                self.tree.insert("", "end", values=(labor, produkt, f"{pkt['preis']:.2f}",
                                                    pkt.get("datum", "–"), pkt.get("monat", "–")))
        leeren(self.chart)
        if not verlauf:
            tk.Label(self.chart, text="Noch keine Preisdaten.", font=FONT_SM, bg=WHITE, fg=TEXT2).pack(expand=True)
            return
        breite = self.chart.winfo_width()
        diagramm_einbetten(charts.preisentwicklung_diagramm(verlauf, max(6, breite / 96) if breite > 10 else 12),
                           self.chart)

    def _gewaehlt(self, _e=None):
        sel = self.tree.selection()
        if sel:
            w = self.tree.item(sel[0])["values"]
            self.pm_labor.set(w[0])
            self.pm_produkt.set(w[1])
            self.pm_preis.set(w[2])

    def _manuell(self):
        labor, produkt = self.pm_labor.get().strip(), self.pm_produkt.get().strip()
        preis = scoring.parse_zahl(self.pm_preis.get())
        if not labor or not produkt or not preis or preis <= 0:
            messagebox.showwarning("Fehler", "Bitte Labor, Produkt und einen Preis > 0 angeben.")
            return
        if self.app.preise.aktualisieren(labor, produkt, preis, datetime.now().strftime("%Y-%m")):
            self.app.status(f"Preis {preis:.2f} € für {labor} / {produkt} eingetragen.")
        else:
            self.app.status("Preis unverändert – nichts eingetragen.")
        self.aktualisieren()

    def _loeschen(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Zeile auswählen.")
            return
        labor, produkt = (str(x) for x in self.tree.item(sel[0])["values"][:2])
        if messagebox.askyesno("Löschen", f"Gesamte Preishistorie für {labor} / {produkt} löschen?"):
            self.app.preise.loeschen(labor, produkt)
            self.aktualisieren()


# ══════════════════════════════════════════════════════════════════════════════
# Berichte
# ══════════════════════════════════════════════════════════════════════════════

class BerichteSeite(Seite):
    titel = "Berichte"

    def __init__(self, parent, app):
        super().__init__(parent, app, scroll=True)
        p = self.inhalt
        seitenkopf(p, "Berichte", "PDF-Berichte über alle Labore")
        f = tk.Frame(p, bg=BG)
        f.pack(fill="x", padx=24, pady=(4, 10))
        self.jahr, self.produkt = tk.StringVar(), tk.StringVar(value=ALLE)
        self.cb_jahr = filter_feld(f, "Jahr", self.jahr, [], 8)
        self.cb_produkt = filter_feld(f, "Produkt", self.produkt, [ALLE], 20)

        for titel, text, modus in (
                ("Übersicht", "Je Produkt eine Tabelle mit den Durchschnittsscores aller Labore "
                              "und dem Status. Gut für die Management-Bewertung.", "uebersicht"),
                ("Detail + Berechnung", "Alle Einzelmessungen mit Rohdaten und Scores je Labor, "
                                        "dazu eine Seite mit den Berechnungsformeln.", "detail")):
            rf = RundFrame(p, radius=16, pad=14)
            rf.pack(fill="x", padx=24, pady=(0, 10))
            tk.Label(rf.inhalt, text=titel, font=FONT_B, bg=WHITE, fg=TEXT, anchor="w").pack(fill="x")
            tk.Label(rf.inhalt, text=text, font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w", justify="left",
                     wraplength=700).pack(fill="x", pady=(2, 10))
            button(rf.inhalt, f"📄  {titel} als PDF speichern", lambda m=modus: self._export(m)).pack(anchor="w")

        abschnitt(p, "Datenablage")
        rf = RundFrame(p, radius=16, pad=14)
        rf.pack(fill="x", padx=24, pady=(0, 20))
        self.ablage = rf.inhalt

    def aktualisieren(self):
        werte_setzen(self.cb_jahr, self.jahr, self.app.store.jahre() or [str(datetime.now().year)])
        werte_setzen(self.cb_produkt, self.produkt, [ALLE] + self.app.store.produkte())
        leeren(self.ablage)
        for label, wert in (("Bewertungen", self.app.store.pfad), ("Preise", self.app.preise.pfad),
                            ("Access-DB", self.app.db_meldung)):
            z = tk.Frame(self.ablage, bg=WHITE)
            z.pack(fill="x", pady=2)
            tk.Label(z, text=label, font=FONT_SM, bg=WHITE, fg=TEXT2, width=14, anchor="w").pack(side="left")
            tk.Label(z, text=wert, font=FONT, bg=WHITE, fg=TEXT, anchor="w").pack(side="left")
        if sys.platform == "win32":
            button(self.ablage, "Datenordner öffnen",
                   lambda: os.startfile(os.path.dirname(os.path.abspath(self.app.store.pfad))),
                   art="sekundaer").pack(anchor="w", pady=(8, 0))

    def _export(self, modus):
        art = "Übersicht" if modus == "uebersicht" else "Detail"
        pfad = filedialog.asksaveasfilename(
            parent=self, title="PDF speichern", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=f"Lieferantenbewertung_{art}_{self.jahr.get()}.pdf")
        if not pfad:
            return
        funktion = pdf_export.erstelle_uebersicht if modus == "uebersicht" else pdf_export.erstelle_detail
        try:
            funktion(pfad, self.app.store.daten, self.jahr.get(), self.produkt.get())
        except ImportError:
            messagebox.showerror("Fehler", "Für den PDF-Export wird das Paket 'reportlab' benötigt.")
            return
        except Exception as err:
            messagebox.showerror("Fehler", str(err))
            return
        self.app.status(f"PDF gespeichert: {pfad}")


ZENTRALE_SEITEN = [StartSeite, VergleichSeite, BewertungenSeite, PreiseSeite, BerichteSeite]
