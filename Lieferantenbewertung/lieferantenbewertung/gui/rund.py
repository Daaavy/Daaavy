"""
Abgerundete Bausteine für tkinter.

tkinter kann von sich aus keine runden Ecken. Diese Widgets zeichnen deshalb
ihren Hintergrund selbst auf ein Canvas und legen das eigentliche Widget
(Entry, Combobox, Frame …) darüber.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import farben as F


def _hintergrund(widget) -> str:
    try:
        return widget.cget("bg")
    except tk.TclError:
        return F.WHITE


def rund_rechteck(canvas: tk.Canvas, x1, y1, x2, y2, r, **kw):
    """Zeichnet ein Rechteck mit abgerundeten Ecken (geglättetes Polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    punkte = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
              x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
              x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(punkte, smooth=True, splinesteps=16, **kw)


# ── Karte / Container ─────────────────────────────────────────────────────────

class RundFrame(tk.Canvas):
    """Container mit runden Ecken. Inhalte in ``.inhalt`` packen.

    fuellen=False: Höhe richtet sich nach dem Inhalt.
    fuellen=True:  Inhalt wird auf die Größe des Containers gezogen
                   (für Tabellen/Diagramme mit expand=True).
    """

    def __init__(self, parent, bg=F.WHITE, rand=F.BORDER, radius=14, pad=8,
                 fuellen=False, **kw):
        super().__init__(parent, bg=_hintergrund(parent), highlightthickness=0, bd=0, **kw)
        self._fill, self._rand, self._r, self._pad, self._fuellen = bg, rand, radius, pad, fuellen
        self.inhalt = tk.Frame(self, bg=bg)
        self._fenster = self.create_window(pad, pad, window=self.inhalt, anchor="nw")
        self.bind("<Configure>", self._groesse)
        if not fuellen:
            self.inhalt.bind("<Configure>", self._inhalt_groesse)

    def _inhalt_groesse(self, _e=None):
        h = self.inhalt.winfo_reqheight() + 2 * self._pad
        w = self.inhalt.winfo_reqwidth() + 2 * self._pad
        if int(float(self.cget("height"))) != h or int(float(self.cget("width"))) != w:
            self.configure(height=h, width=w)

    def _groesse(self, e):
        p = self._pad
        opts = {"width": max(1, e.width - 2 * p)}
        if self._fuellen:
            opts["height"] = max(1, e.height - 2 * p)
        self.itemconfigure(self._fenster, **opts)
        self.delete("rahmen")
        rund_rechteck(self, 1, 1, e.width - 2, e.height - 2, self._r, fill=self._fill,
                      outline=self._rand, tags="rahmen")
        self.tag_lower("rahmen")


# ── Button ────────────────────────────────────────────────────────────────────

BUTTON_ARTEN = {
    #             Füllung     Hover       Text        Rand
    "primaer":   (F.ACCENT,   F.ACCENT_DUNKEL, F.WHITE, ""),
    "sekundaer": (F.WHITE,    F.BG2,      F.TEXT2,    F.BORDER),
    "gefahr":    (F.WHITE,    "#FBECEC",  F.DANGER,   F.BORDER),
    "tab":       (F.BG,       F.BG2,      F.TEXT2,    ""),
    "tab_aktiv": (F.ACCENT,   F.ACCENT,   F.WHITE,    ""),
    "tag":       (F.WHITE,    F.BG2,      F.TEXT,     ""),
    "tag_aktiv": (F.ACCENT,   F.ACCENT,   F.WHITE,    ""),
}


class RundButton(tk.Canvas):
    """Button in Pillenform."""

    def __init__(self, parent, text, command=None, art="primaer", font=None, fg=None,
                 padx=16, pady=7, radius=None, breite=None, **_ignoriert):
        super().__init__(parent, bg=_hintergrund(parent), highlightthickness=0, bd=0, cursor="hand2")
        self._text, self.command, self._radius = text, command, radius
        self._font = tkfont.Font(font=font or (F.FONT_B if art == "primaer" else F.FONT))
        self._fg_extra = fg
        self._hover = False
        self.art = art
        w = breite or self._font.measure(text) + 2 * padx
        h = self._font.metrics("linespace") + 2 * pady
        super().configure(width=w, height=h)
        self.bind("<Configure>", lambda e: self._zeichnen())
        self.bind("<Enter>", lambda e: self._hover_setzen(True))
        self.bind("<Leave>", lambda e: self._hover_setzen(False))
        self.bind("<ButtonRelease-1>", self._klick)

    def _hover_setzen(self, wert):
        self._hover = wert
        self._zeichnen()

    def setze_art(self, art):
        self.art = art
        self._zeichnen()

    def _zeichnen(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2:
            w, h = int(float(self.cget("width"))), int(float(self.cget("height")))
        fill, hover, fg, rand = BUTTON_ARTEN[self.art]
        if self._fg_extra and self.art in ("sekundaer", "gefahr"):
            fg = self._fg_extra
        r = self._radius if self._radius is not None else h / 2
        rund_rechteck(self, 1, 1, w - 2, h - 2, r, fill=hover if self._hover else fill,
                      outline=rand or (hover if self._hover else fill))
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)

    def _klick(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.command:
            self.command()

    def cget(self, key):
        return self._text if key == "text" else super().cget(key)


# ── Eingabefelder mit runden Ecken ────────────────────────────────────────────

class _Gerahmt(tk.Canvas):
    """Canvas mit rundem Rahmen um ein inneres Widget.

    Konfiguration (configure, bind, get, …) wird an das innere Widget
    weitergereicht; pack/grid wirken auf den Rahmen.
    """
    widget = None

    def _rahmen_init(self, parent, inneres, radius=9, padx=8, pady=5, fill=F.BG):
        self._r, self._px, self._py, self._fill, self._rand = radius, padx, pady, fill, F.BORDER
        self.widget = inneres
        self._fenster = self.create_window(0, 0, window=inneres, anchor="center")
        tk.Canvas.configure(self, width=inneres.winfo_reqwidth() + 2 * padx,
                            height=inneres.winfo_reqheight() + 2 * pady)
        tk.Canvas.bind(self, "<Configure>", lambda e: self._zeichnen())
        tk.Canvas.bind(self, "<Button-1>", lambda e: inneres.focus_set())
        inneres.bind("<FocusIn>", lambda e: self._randfarbe(F.ACCENT), add="+")
        inneres.bind("<FocusOut>", lambda e: self._randfarbe(F.BORDER), add="+")

    def _randfarbe(self, farbe):
        self._rand = farbe
        self._zeichnen()

    def _zeichnen(self):
        w, h = self.winfo_width(), self.winfo_height()
        self.coords(self._fenster, w / 2, h / 2)
        self.itemconfigure(self._fenster, width=max(1, w - 2 * self._px))
        self.delete("rahmen")
        rund_rechteck(self, 1, 1, w - 2, h - 2, self._r, fill=self._fill, outline=self._rand, tags="rahmen")
        self.tag_lower("rahmen")

    # Weiterleitung an das innere Widget
    def configure(self, cnf=None, **kw):
        if self.widget is None:
            return tk.Canvas.configure(self, cnf, **kw)
        return self.widget.configure(cnf, **kw)

    config = configure

    def cget(self, key):
        return tk.Canvas.cget(self, key) if self.widget is None else self.widget.cget(key)

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, wert):
        self.configure(**{key: wert})

    def bind(self, *a, **kw):
        return tk.Canvas.bind(self, *a, **kw) if self.widget is None else self.widget.bind(*a, **kw)

    def focus_set(self):
        self.widget.focus_set()

    def get(self, *a):
        return self.widget.get(*a)


class RundEingabe(_Gerahmt):
    def __init__(self, parent, var, breite=14, fill=F.BG, font=None):
        super().__init__(parent, bg=_hintergrund(parent), highlightthickness=0, bd=0)
        e = tk.Entry(self, textvariable=var, font=font or F.FONT, width=breite, relief="flat", bd=0,
                     highlightthickness=0, bg=fill, disabledbackground=fill, fg=F.TEXT,
                     insertbackground=F.TEXT)
        self._rahmen_init(parent, e, fill=fill)


class RundCombobox(_Gerahmt):
    def __init__(self, parent, var, werte=(), breite=18, nur_lesen=True, fill=F.BG):
        super().__init__(parent, bg=_hintergrund(parent), highlightthickness=0, bd=0)
        cb = ttk.Combobox(self, textvariable=var, values=list(werte), width=breite, font=F.FONT,
                          style="Rund.TCombobox", state="readonly" if nur_lesen else "normal")
        self._rahmen_init(parent, cb, padx=6, pady=3, fill=fill)


def combobox_stil(style: ttk.Style):
    """Combobox ohne eigenen Rahmen, damit der runde Rahmen sichtbar ist."""
    flach = dict(bordercolor=F.BG, lightcolor=F.BG, darkcolor=F.BG, background=F.BG,
                 fieldbackground=F.BG, arrowcolor=F.ACCENT, foreground=F.TEXT, padding=(4, 2),
                 relief="flat", borderwidth=0, arrowsize=13)
    style.configure("Rund.TCombobox", **flach)
    style.map("Rund.TCombobox", fieldbackground=[("readonly", F.BG)], background=[("readonly", F.BG)],
              bordercolor=[("focus", F.BG)], lightcolor=[("focus", F.BG)], darkcolor=[("focus", F.BG)],
              selectbackground=[("readonly", F.BG)], selectforeground=[("readonly", F.TEXT)])


# ── Liste mit runder Auswahl (Seitenleiste) ───────────────────────────────────

class RundListe(tk.Canvas):
    """Einfache Liste mit Überschriften und abgerundeter Markierung.

    zeilen: [(code oder None, text), …] – None = nicht auswählbare Überschrift
    """
    ZEILE = 30

    def __init__(self, parent, auswahl=None, kontext=None, bg=F.WHITE):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._bg = bg
        self.zeilen, self.markiert, self._hover = [], None, None
        self._auswahl, self._kontext = auswahl, kontext
        self.bind("<Configure>", lambda e: self._zeichnen())
        self.bind("<Motion>", self._bewegung)
        self.bind("<Leave>", lambda e: self._hover_setzen(None))
        self.bind("<Button-1>", lambda e: self._klick(e, self._auswahl))
        self.bind("<Button-3>", lambda e: self._klick(e, self._kontext))

    def setze(self, zeilen):
        self.zeilen = list(zeilen)
        self._zeichnen()

    def markiere(self, code):
        self.markiert = code
        self._zeichnen()
        codes = [c for c, _ in self.zeilen]
        if code in codes:
            gesamt = max(1, len(self.zeilen) * self.ZEILE)
            oben = codes.index(code) * self.ZEILE
            sicht_oben, sicht_unten = (v * gesamt for v in self.yview())
            if oben < sicht_oben or oben + self.ZEILE > sicht_unten:
                self.yview_moveto(max(0, (oben - self.ZEILE * 2) / gesamt))

    def _index_bei(self, y):
        i = int(self.canvasy(y) // self.ZEILE)
        return i if 0 <= i < len(self.zeilen) else None

    def _bewegung(self, e):
        i = self._index_bei(e.y)
        self._hover_setzen(self.zeilen[i][0] if i is not None else None)

    def _hover_setzen(self, code):
        if code != self._hover:
            self._hover = code
            self._zeichnen()

    def _klick(self, e, callback):
        i = self._index_bei(e.y)
        if i is not None and self.zeilen[i][0] and callback:
            callback(self.zeilen[i][0], e)

    def _mausrad(self, schritte):
        if len(self.zeilen) * self.ZEILE > self.winfo_height():
            self.yview_scroll(schritte, "units")

    def _zeichnen(self):
        self.delete("all")
        w = self.winfo_width()
        z = self.ZEILE
        for i, (code, text) in enumerate(self.zeilen):
            y = i * z
            if code is None:
                self.create_text(14, y + z / 2 + 3, text=text, anchor="w", fill=F.TEXT2,
                                 font=("Segoe UI", 7, "bold"))
                continue
            aktiv = code == self.markiert
            if aktiv or code == self._hover:
                rund_rechteck(self, 6, y + 3, w - 6, y + z - 3, (z - 6) / 2,
                              fill=F.ACCENT if aktiv else F.BG2, outline="")
            self.create_text(20, y + z / 2, text=text, anchor="w",
                             fill=F.WHITE if aktiv else F.TEXT, font=F.FONT_B if aktiv else F.FONT)
        self.configure(scrollregion=(0, 0, w, len(self.zeilen) * z), yscrollincrement=z)
