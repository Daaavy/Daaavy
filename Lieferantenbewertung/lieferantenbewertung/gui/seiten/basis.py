"""Gemeinsame Bausteine für alle Seiten."""
from __future__ import annotations

import tkinter as tk

from ..rund import RundButton, RundFrame
from ..widgets import (BG, FONT, FONT_H, FONT_SM, STATUS_TEXTFARBEN, TEXT, TEXT2, WHITE,
                       ScrollFrame, combobox)


class Seite(tk.Frame):
    """Basisklasse. ``self.inhalt`` ist der Bereich für Inhalte (ggf. scrollbar)."""

    titel = ""

    def __init__(self, parent, app, scroll=False):
        super().__init__(parent, bg=BG)
        self.app = app
        self._scroll = None
        if scroll:
            self._scroll = ScrollFrame(self, bg=BG)
            self._scroll.pack(fill="both", expand=True)
            self.inhalt = self._scroll.inhalt
        else:
            self.inhalt = self

    def aktualisieren(self):
        """Wird aufgerufen, wenn die Seite angezeigt wird oder sich Daten ändern."""

    def nach_oben(self):
        if self._scroll:
            self._scroll.nach_oben()


def leeren(frame: tk.Misc) -> None:
    for w in frame.winfo_children():
        w.destroy()


def seitenkopf(parent, titel, untertitel="") -> tk.Frame:
    """Titel links; gibt einen Frame rechts für Buttons zurück."""
    kopf = tk.Frame(parent, bg=BG)
    kopf.pack(fill="x", padx=24, pady=(18, 6))
    links = tk.Frame(kopf, bg=BG)
    links.pack(side="left")
    tk.Label(links, text=titel, font=FONT_H, bg=BG, fg=TEXT, anchor="w").pack(anchor="w")
    if untertitel:
        tk.Label(links, text=untertitel, font=FONT_SM, bg=BG, fg=TEXT2, anchor="w").pack(anchor="w")
    rechts = tk.Frame(kopf, bg=BG)
    rechts.pack(side="right")
    return rechts


def abschnitt(parent, titel, padx=24) -> None:
    tk.Label(parent, text=titel.upper(), font=("Segoe UI", 8, "bold"), bg=BG, fg=TEXT2,
             anchor="w").pack(fill="x", padx=padx, pady=(14, 6))


def kachel(parent, label, wert, farbe=TEXT, unter="", breite=None) -> RundFrame:
    rk = RundFrame(parent, radius=16, pad=12)
    rk.pack(side="left", padx=(0, 10))
    k = rk.inhalt
    tk.Label(k, text=label, font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w", width=breite).pack(anchor="w")
    tk.Label(k, text=wert, font=("Segoe UI", 18, "bold"), bg=WHITE, fg=farbe, anchor="w").pack(anchor="w")
    if unter:
        tk.Label(k, text=unter, font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w").pack(anchor="w")
    return rk


def status_pille(parent, score, text=None, bg=BG) -> tk.Label:
    """Farbige, runde Statusanzeige ("Freigegeben", …)."""
    from ... import scoring
    key, status_text = scoring.status(score)
    farben = {"ok": ("#DDEFF6", "#1F6E8C"), "warn": ("#FDF0DA", "#A0661A"),
              "bad": ("#F8DEDC", "#9A3B36"), "none": ("#EEEEEE", TEXT2)}
    fill, fg = farben[key]
    rf = RundFrame(parent, bg=fill, rand=fill, radius=12, pad=3)
    tk.Label(rf.inhalt, text=text or status_text, font=("Segoe UI", 9, "bold"), bg=fill, fg=fg,
             padx=8).pack()
    return rf


def filter_feld(parent, label, var, werte, breite=16, bg=BG):
    tk.Label(parent, text=label, font=FONT_SM, bg=bg, fg=TEXT2).pack(side="left", padx=(0, 4))
    cb = combobox(parent, var, werte, breite, bg=WHITE)
    cb.pack(side="left", padx=(0, 16))
    return cb


def werte_setzen(cb, var, werte) -> bool:
    """Setzt die Auswahlwerte; -> True, wenn der aktuelle Wert dadurch zurückgesetzt wurde."""
    cb.configure(values=werte)
    if var.get() not in werte:
        var.set(werte[0])
        return True
    return False


def diagramm_einbetten(fig, parent, **pack):
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    canvas = FigureCanvasTkAgg(fig, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(**(pack or {"fill": "both", "expand": True}))
    return canvas


def score_farbe(score) -> str:
    from ... import scoring
    return STATUS_TEXTFARBEN[scoring.status(score)[0]]


class Reiter(tk.Frame):
    """Runde Reiterleiste mit gestapelten Seiten."""

    def __init__(self, parent, bg=BG, bei_wechsel=None):
        super().__init__(parent, bg=bg)
        self.leiste = tk.Frame(self, bg=bg)
        self.leiste.pack(fill="x", padx=24, pady=(4, 8))
        self.stapel = tk.Frame(self, bg=bg)
        self.stapel.pack(fill="both", expand=True)
        self.stapel.grid_rowconfigure(0, weight=1)
        self.stapel.grid_columnconfigure(0, weight=1)
        self._seiten, self._knoepfe = {}, {}
        self.aktiv = None
        self._bei_wechsel = bei_wechsel

    def hinzufuegen(self, name, seite: tk.Frame) -> None:
        seite.grid(in_=self.stapel, row=0, column=0, sticky="nsew")
        self._seiten[name] = seite
        b = RundButton(self.leiste, name, lambda n=name: self.zeige(n), art="tab", font=FONT, padx=16, pady=6)
        b.pack(side="left", padx=(0, 6))
        self._knoepfe[name] = b
        if self.aktiv is None:
            self.zeige(name)

    def zeige(self, name) -> None:
        self.aktiv = name
        self._seiten[name].tkraise()
        for n, b in self._knoepfe.items():
            b.setze_art("tab_aktiv" if n == name else "tab")
        if self._bei_wechsel:
            self._bei_wechsel(name)
