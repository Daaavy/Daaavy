"""Eingabemaske für eine Bewertung (gehört zur Laborseite)."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox

from ... import config, scoring
from ...storage import neue_id
from .. import dialoge
from ..rund import RundFrame
from ..widgets import (ACCENT, BG, FONT, FONT_B, FONT_SM, STATUS_TEXTFARBEN, TEXT2, WHITE, button,
                       combobox, eingabe, feld, fmt, karte)

FORMULAR_FELDER = ("monat", "jahr", "produkt", "konzentration", "pruefnummer",
                   "q_verworfen", "q_gemessen", "q_produkt", "z_versand", "z_eingang",
                   "k_laborpreis", "s_berichtet", "s_behoben", "s_anfrage", "s_antwort", "s_nachfragen")
ZAHL_FELDER = {"q_verworfen": "Verworfene Analyten", "q_gemessen": "Gemessene Analyten",
               "q_produkt": "Gesamte Analyten", "k_laborpreis": "Laborpreis",
               "s_berichtet": "Berichtete Fehler", "s_behoben": "Behobene Fehler",
               "s_nachfragen": "Nachfragen"}


def _txt(wert):
    if wert is None or wert == "":
        return ""
    if isinstance(wert, float) and wert.is_integer():
        return str(int(wert))
    return str(wert)


class Eingabe(tk.Frame):
    """Formular. ``labor_fn`` liefert den aktuellen Laborcode."""

    def __init__(self, parent, app, labor_fn, nach_speichern=None):
        super().__init__(parent, bg=BG)
        self.app, self.labor_fn, self.nach_speichern = app, labor_fn, nach_speichern
        self.bearbeitungs_id = None
        self.formular = {k: tk.StringVar() for k in FORMULAR_FELDER}
        self.k_kostenlos = tk.BooleanVar(value=False)
        self._aufbauen()
        for var in self.formular.values():
            var.trace_add("write", lambda *_: self.vorschau())
        self.k_kostenlos.trace_add("write", lambda *_: self.vorschau())
        self.formular["produkt"].trace_add("write", lambda *_: self.preis_vorschlagen())
        self.leeren()

    def _aufbauen(self):
        f = self.formular

        # Kopfdaten
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=24, pady=(2, 6))

        def lbl(text):
            tk.Label(top, text=text, font=FONT_SM, bg=BG, fg=TEXT2).pack(side="left", padx=(0, 4))
        lbl("Monat")
        combobox(top, f["monat"], dialoge.MONAT_WERTE, 4, bg=WHITE).pack(side="left", padx=(0, 12))
        lbl("Jahr")
        combobox(top, f["jahr"], dialoge.jahr_werte(), 6, bg=WHITE).pack(side="left", padx=(0, 20))
        lbl("Produkt / Analyt")
        self.cb_produkt = combobox(top, f["produkt"], (), 22, nur_lesen=False, bg=WHITE)
        self.cb_produkt.pack(side="left", padx=(0, 16))
        self.cb_produkt.bind("<ButtonPress-1>",
                             lambda e: self.cb_produkt.configure(values=self.app.store.produkte()))
        lbl("Konzentration")
        eingabe(top, f["konzentration"], 10, bg=WHITE).pack(side="left", padx=(0, 16))
        lbl("Prüfnummer")
        eingabe(top, f["pruefnummer"], 14, bg=WHITE).pack(side="left")

        # Aktionen + Live-Score
        rf = RundFrame(self, radius=18, pad=4)
        rf.pack(fill="x", padx=24, pady=(6, 10))
        bf = rf.inhalt
        button(bf, "  Speichern  ", self.speichern, padx=20, pady=8).pack(side="left", padx=(8, 8), pady=6)
        button(bf, "Neu / Felder leeren", self.leeren, art="sekundaer", pady=8).pack(side="left", pady=6)
        button(bf, "📋  Mehrere Level erfassen", self._level, art="sekundaer", fg=ACCENT, pady=8
               ).pack(side="left", padx=8, pady=6)
        self.lbl_vorschau = tk.Label(bf, text="", font=FONT_B, bg=WHITE, fg=TEXT2)
        self.lbl_vorschau.pack(side="right", padx=16)
        self.lbl_modus = tk.Label(self, text="", font=FONT_B, bg=BG, fg=ACCENT, anchor="w")

        spalten = tk.Frame(self, bg=BG)
        self._spalten = spalten
        spalten.pack(fill="both", expand=True, padx=24, pady=4)
        links = tk.Frame(spalten, bg=BG)
        links.pack(side="left", fill="both", expand=True, padx=(0, 6))
        rechts = tk.Frame(spalten, bg=BG)
        rechts.pack(side="left", fill="both", expand=True, padx=(6, 0))
        g = config.GEWICHTE
        qa = int(config.QUALITAET_ANTEIL_FEHLERQUOTE * 100)

        c = karte(links, f"Qualität (Gewicht {g['qualitaet']})  —  Fehlerquote {qa} %  /  Analytauswahl {100 - qa} %")
        feld(c, "Anzahl verworfener Analyten", f["q_verworfen"])
        feld(c, "Anzahl gemessener Analyten", f["q_gemessen"])
        feld(c, "Anzahl gesamter Analyten im Produkt", f["q_produkt"])

        c = karte(links, f"Zuverlässigkeit (Gewicht {g['zuverlaessigkeit']})  —  Termintreue")
        feld(c, "Versanddatum (Proben versendet)", f["z_versand"], datum=True)
        feld(c, "Eingangsdatum der Werte", f["z_eingang"], datum=True)

        c = karte(links, "Kommentar")
        kr = RundFrame(c, bg=BG, radius=10, pad=6)
        kr.pack(fill="x", padx=12, pady=(4, 8))
        self.e_kommentar = tk.Text(kr.inhalt, font=FONT, height=3, relief="flat", bd=0,
                                   highlightthickness=0, bg=BG, wrap="word")
        self.e_kommentar.pack(fill="x")

        c = karte(rechts, f"Kosten (Gewicht {g['kosten']})")
        self.e_preis = feld(c, "Laborpreis (EUR)", f["k_laborpreis"])
        self.lbl_preis_hinweis = tk.Label(c, text="", font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w",
                                          justify="left", wraplength=300)
        self.lbl_preis_hinweis.pack(fill="x", padx=12)
        tk.Checkbutton(c, text="Kostenloses Labor (Score = 100 %)", variable=self.k_kostenlos,
                       font=FONT_SM, bg=WHITE, fg=TEXT2, activebackground=WHITE, cursor="hand2",
                       highlightthickness=0, bd=0, command=self._kostenlos_umschalten
                       ).pack(anchor="w", padx=12, pady=(0, 8))

        c = karte(rechts, f"Service (Gewicht {g['service']})")
        feld(c, "Dem Labor berichtete Fehler", f["s_berichtet"], "1 Analyt = 1 Fehler")
        feld(c, "Anzahl behobener Fehler", f["s_behoben"])
        feld(c, "Datum Anfrage (E-Mail gesendet)", f["s_anfrage"], datum=True)
        feld(c, "Datum Antwort erhalten", f["s_antwort"], datum=True)
        feld(c, "Anzahl Nachfragen", f["s_nachfragen"], "je −10 %")

    # ── Zustand ───────────────────────────────────────────────────────────
    def _bearbeitung_setzen(self, eintrag_id):
        self.bearbeitungs_id = eintrag_id
        if eintrag_id:
            _, e = self.app.store.finden(eintrag_id)
            beschreibung = f"{e['produkt']} {e['konzentration']} · {e['monat']}" if e else ""
            self.lbl_modus.config(text=f"✎  Du bearbeitest einen bestehenden Eintrag: {beschreibung}")
            self.lbl_modus.pack(fill="x", padx=28, pady=(0, 6), before=self._spalten)
        else:
            self.lbl_modus.pack_forget()

    def befuellt(self) -> bool:
        if any(v.get().strip() for k, v in self.formular.items() if k not in ("monat", "jahr")):
            return True
        return bool(self.e_kommentar.get("1.0", "end").strip())

    def leeren(self):
        for var in self.formular.values():
            var.set("")
        self.formular["monat"].set(f"{datetime.now().month:02d}")
        self.formular["jahr"].set(str(datetime.now().year))
        self.k_kostenlos.set(False)
        self._kostenlos_umschalten()
        self.e_kommentar.delete("1.0", "end")
        self._bearbeitung_setzen(None)

    def neu_beginnen(self):
        """Werte behalten, aber als neuen Eintrag speichern."""
        self._bearbeitung_setzen(None)

    def _kostenlos_umschalten(self):
        if self.k_kostenlos.get():
            self.formular["k_laborpreis"].set("0")
            self.e_preis.config(state="disabled")
        else:
            self.e_preis.config(state="normal")

    def hinterlegter_preis(self):
        """Zuletzt hinterlegter Preis für Labor + Produkt (oder None)."""
        labor, produkt = self.labor_fn(), self.formular["produkt"].get().strip()
        return self.app.preise.letzter_preis(labor, produkt) if labor and produkt else None

    def preis_vorschlagen(self):
        """Zeigt den hinterlegten Preis grau im leeren Preisfeld an."""
        preis = self.hinterlegter_preis()
        self.e_preis.platzhalter(f"{preis:.2f}" if preis is not None else "")
        self.lbl_preis_hinweis.config(
            text="Grau = hinterlegter Preis. Er wird übernommen, wenn du nichts einträgst."
            if preis is not None else "")

    # ── Formular <-> Eintrag ──────────────────────────────────────────────
    def eintrag(self) -> dict:
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
            "qualitaet": {"verworfen": z["q_verworfen"], "gemessen": z["q_gemessen"], "produkt": z["q_produkt"]},
            "zuverlaessigkeit": {"versand": f["z_versand"].get().strip(), "eingang": f["z_eingang"].get().strip()},
            "kosten": {"laborpreis": 0.0 if self.k_kostenlos.get() else
                       (z["k_laborpreis"] if z["k_laborpreis"] is not None else self.hinterlegter_preis()),
                       "kostenlos": self.k_kostenlos.get()},
            "service": {"berichtet": z["s_berichtet"], "behoben": z["s_behoben"],
                        "anfrage": f["s_anfrage"].get().strip(), "antwort": f["s_antwort"].get().strip(),
                        "nachfragen": z["s_nachfragen"]},
            "kommentar": self.e_kommentar.get("1.0", "end").strip(),
        }

    def fuellen(self, eintrag: dict):
        f = self.formular
        jahr, _, monat = eintrag.get("monat", "").partition("-")
        f["jahr"].set(jahr)
        f["monat"].set(monat)
        for key in ("produkt", "konzentration", "pruefnummer"):
            f[key].set(eintrag.get(key, ""))
        q, z, k, s = (eintrag.get(x) or {} for x in ("qualitaet", "zuverlaessigkeit", "kosten", "service"))
        f["q_verworfen"].set(_txt(q.get("verworfen")))
        f["q_gemessen"].set(_txt(q.get("gemessen")))
        f["q_produkt"].set(_txt(q.get("produkt")))
        f["z_versand"].set(z.get("versand", ""))
        f["z_eingang"].set(z.get("eingang", ""))
        self.k_kostenlos.set(bool(k.get("kostenlos")))
        self._kostenlos_umschalten()
        f["k_laborpreis"].set(_txt(k.get("laborpreis")))
        f["s_berichtet"].set(_txt(s.get("berichtet")))
        f["s_behoben"].set(_txt(s.get("behoben")))
        f["s_anfrage"].set(s.get("anfrage", ""))
        f["s_antwort"].set(s.get("antwort", ""))
        f["s_nachfragen"].set(_txt(s.get("nachfragen")))
        self.e_kommentar.delete("1.0", "end")
        self.e_kommentar.insert("1.0", eintrag.get("kommentar", ""))
        self._bearbeitung_setzen(eintrag.get("id"))

    def vorschau(self):
        if not hasattr(self, "lbl_vorschau") or not hasattr(self, "e_kommentar"):
            return
        try:
            e = self.eintrag()
        except (ValueError, tk.TclError):
            self.lbl_vorschau.config(text="Ungültige Zahl", fg=STATUS_TEXTFARBEN["bad"])
            return
        sc = scoring.berechne_scores(e, self.app.benchmarks)
        key, text = scoring.status(sc.gesamt)
        if sc.gesamt is None:
            self.lbl_vorschau.config(text="Score erscheint während der Eingabe", fg=TEXT2)
        else:
            self.lbl_vorschau.config(
                text=f"Q {fmt(sc.qualitaet)} · Z {fmt(sc.zuverlaessigkeit)} · K {fmt(sc.kosten)} · "
                     f"S {fmt(sc.service)}   →   {sc.gesamt:.1f} {text}", fg=STATUS_TEXTFARBEN[key])

    # ── Aktionen ──────────────────────────────────────────────────────────
    def speichern(self):
        labor = self.labor_fn()
        if not labor:
            return
        try:
            eintrag = self.eintrag()
        except ValueError as err:
            messagebox.showwarning("Ungültige Eingabe", str(err))
            return
        hinweise = scoring.plausibilitaet(eintrag)
        if hinweise and not messagebox.askyesno(
                "Bitte prüfen", "\n".join(f"• {h}" for h in hinweise) + "\n\nTrotzdem speichern?"):
            return
        doppelt = self.app.store.duplikat(labor, eintrag)
        if doppelt:
            if not messagebox.askyesno(
                    "Überschreiben?",
                    f"Prüfnummer '{eintrag['pruefnummer']}' ({doppelt['produkt']} {doppelt['konzentration']}, "
                    f"{doppelt['monat']}) existiert bei {labor} bereits. Überschreiben?"):
                return
            if self.bearbeitungs_id and self.bearbeitungs_id != doppelt["id"]:
                self.app.store.eintrag_loeschen(self.bearbeitungs_id)
            eintrag["id"] = doppelt["id"]
        self.app.eintrag_ablegen(labor, eintrag)
        self._bearbeitung_setzen(None)  # nächster Klick auf Speichern legt einen neuen Eintrag an
        self.app.alles_aktualisieren()
        self.app.status(f"Gespeichert: {labor} · {eintrag['produkt']} {eintrag['konzentration']} · {eintrag['monat']}")
        if self.nach_speichern:
            self.nach_speichern()

    def _level(self):
        if self.labor_fn():
            dialoge.level_eingabe(self.app, self.labor_fn())
