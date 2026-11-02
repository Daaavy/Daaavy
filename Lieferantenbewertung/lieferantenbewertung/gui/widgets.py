"""Farben, Schriften und wiederverwendbare Bausteine für die Oberfläche."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from .. import config

# ── Farben & Schriften ────────────────────────────────────────────────────────
BG = "#F7F9FC"
BG2 = "#EEF3F9"
WHITE = "#FFFFFF"
ACCENT = "#4A7FC1"
TEXT = "#1A1A1A"
TEXT2 = "#888888"
BORDER = "#E2E8F0"
DANGER = "#B04A4A"

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_H = ("Segoe UI", 16, "bold")
FONT_SM = ("Segoe UI", 9)
FONT_XS = ("Segoe UI", 8)

STATUS_ZEILENFARBEN = {"ok": "#E0EDF8", "warn": "#FFF4E0", "bad": "#F5E1E1", "none": WHITE}
STATUS_TEXTFARBEN = {"ok": "#2E86AB", "warn": "#C08020", "bad": "#B04A4A", "none": TEXT2}

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


def ttk_stil(root: tk.Misc) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TNotebook", background=WHITE, borderwidth=0)
    style.configure("TNotebook.Tab", font=FONT_SM, padding=[14, 8], background=WHITE,
                    foreground=TEXT2, borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", WHITE)], foreground=[("selected", ACCENT)])
    style.configure("Treeview", font=FONT, rowheight=28, background=WHITE,
                    fieldbackground=WHITE, foreground=TEXT)
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=BG2, foreground=TEXT2)
    style.configure("TCombobox", fieldbackground=WHITE, background=WHITE, foreground=TEXT,
                    bordercolor=BORDER, arrowcolor=ACCENT, padding=(6, 4))
    style.map("TCombobox", fieldbackground=[("readonly", WHITE)],
              bordercolor=[("focus", ACCENT), ("!focus", BORDER)])
    root.option_add("*TCombobox*Listbox.background", WHITE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", BG2)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT)
    root.option_add("*TCombobox*Listbox.font", FONT)


# ── Buttons & Eingaben ────────────────────────────────────────────────────────

def button(parent, text, command, art="primaer", **kw) -> tk.Button:
    """art: primaer (blau) | sekundaer (weiß mit Rahmen) | gefahr"""
    if art == "primaer":
        opts = dict(bg=ACCENT, fg=WHITE, font=FONT_B, activebackground="#3A6BAA", activeforeground=WHITE)
    else:
        opts = dict(bg=WHITE, fg=DANGER if art == "gefahr" else TEXT2, font=FONT,
                    highlightthickness=1, highlightbackground=BORDER, activebackground=BG2)
    opts.update(relief="flat", padx=14, pady=6, cursor="hand2", bd=0)
    opts.update(kw)
    return tk.Button(parent, text=text, command=command, **opts)


def eingabe(parent, var, breite=14, bg=BG) -> tk.Entry:
    return tk.Entry(parent, textvariable=var, font=FONT, width=breite, relief="flat",
                    highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER, bg=bg)


def feld(parent, label, var, hinweis="", breite=14, datum=False, bg=WHITE) -> tk.Entry:
    """Label über einem Eingabefeld (optional mit Kalender-Button und Hinweis)."""
    f = tk.Frame(parent, bg=bg)
    f.pack(fill="x", padx=12, pady=4)
    tk.Label(f, text=label, font=FONT_SM, bg=bg, fg=TEXT, anchor="w").pack(fill="x")
    zeile = tk.Frame(f, bg=bg)
    zeile.pack(fill="x", pady=(2, 0))
    e = eingabe(zeile, var, breite, bg=BG)
    e.pack(side="left", ipady=4)
    if datum:
        kalender_button(zeile, var).pack(side="left", padx=4)
    if hinweis:
        tk.Label(zeile, text=hinweis, font=FONT_XS, bg=bg, fg=TEXT2).pack(side="left", padx=6)
    return e


def zeile(parent, label, var, breite=12, datum=False, label_breite=28, bg=WHITE) -> tk.Entry:
    """Label links, Eingabe rechts in einer Zeile."""
    f = tk.Frame(parent, bg=bg)
    f.pack(fill="x", pady=4)
    tk.Label(f, text=label, font=FONT_SM, bg=bg, fg=TEXT2, width=label_breite, anchor="w").pack(side="left")
    e = eingabe(f, var, breite)
    e.pack(side="left", ipady=4)
    if datum:
        kalender_button(f, var).pack(side="left", padx=4)
    return e


def karte(parent, titel) -> tk.Frame:
    f = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
    f.pack(fill="x", pady=(0, 8))
    tk.Label(f, text=titel, font=FONT_SM, bg=WHITE, fg=TEXT2, anchor="w", padx=12, pady=6).pack(fill="x")
    tk.Frame(f, bg=BORDER, height=1).pack(fill="x")
    return f


def combobox(parent, var, werte=(), breite=18, nur_lesen=True) -> ttk.Combobox:
    return ttk.Combobox(parent, textvariable=var, values=list(werte), width=breite, font=FONT,
                        state="readonly" if nur_lesen else "normal")


def tabelle(parent, spalten: dict, hoehe=16) -> ttk.Treeview:
    """spalten: {Name: (breite, ausrichtung)} – mit vertikaler Scrollbar."""
    rahmen = tk.Frame(parent, bg=BG)
    rahmen.pack(fill="both", expand=True, padx=20, pady=(0, 8))
    tree = ttk.Treeview(rahmen, columns=list(spalten), show="headings", height=hoehe)
    for name, (breite, anker) in spalten.items():
        tree.heading(name, text=name)
        tree.column(name, width=breite, anchor=anker)
    sb = ttk.Scrollbar(rahmen, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="left", fill="y")
    for key, farbe in STATUS_ZEILENFARBEN.items():
        tree.tag_configure(key, background=farbe)
    return tree


def fmt(v) -> str:
    return f"{v:.1f}" if v is not None else "–"


# ── Dialogfenster ─────────────────────────────────────────────────────────────

def dialog(parent, titel, groesse=None, modal=True) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(titel)
    win.configure(bg=WHITE)
    win.transient(parent.winfo_toplevel())
    if groesse:
        win.geometry(groesse)
    kopf = tk.Frame(win, bg=ACCENT)
    kopf.pack(fill="x")
    tk.Label(kopf, text=titel, font=("Segoe UI", 12, "bold"), bg=ACCENT, fg=WHITE,
             padx=20, pady=10).pack(side="left")
    win.bind("<Escape>", lambda e: win.destroy())
    if modal:
        win.wait_visibility()
        win.grab_set()
    return win


def zentrieren(win: tk.Toplevel, bezug: tk.Misc) -> None:
    win.update_idletasks()
    x = bezug.winfo_rootx() + bezug.winfo_width() // 2 - win.winfo_width() // 2
    y = bezug.winfo_rooty() + bezug.winfo_height() // 2 - win.winfo_height() // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


class ScrollFrame(tk.Frame):
    """Frame mit vertikaler Scrollbar; Inhalte in ``.inhalt`` packen."""

    def __init__(self, parent, bg=WHITE):
        super().__init__(parent, bg=bg)
        canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inhalt = tk.Frame(canvas, bg=bg)
        self.inhalt.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        fenster = canvas.create_window((0, 0), window=self.inhalt, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(fenster, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _rad(event):
            canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")
        self.inhalt.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _rad))
        self.inhalt.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))


# ── Kalender ──────────────────────────────────────────────────────────────────

def kalender_button(parent, var) -> tk.Button:
    return tk.Button(parent, text="📅", font=FONT_SM, bg=BG2, fg=TEXT, relief="flat",
                     padx=4, pady=1, cursor="hand2",
                     command=lambda: kalender_popup(parent, var))


def kalender_popup(parent, var: tk.StringVar) -> None:
    """Kleiner Kalender; schreibt das gewählte Datum als TT.MM.JJJJ in ``var``."""
    popup = tk.Toplevel(parent)
    popup.title("Datum wählen")
    popup.resizable(False, False)
    popup.configure(bg=WHITE)
    popup.transient(parent.winfo_toplevel())
    popup.bind("<Escape>", lambda e: popup.destroy())

    try:
        gewaehlt = datetime.strptime(var.get().strip(), config.DATUMSFORMAT).date()
    except ValueError:
        gewaehlt = None
    basis = gewaehlt or datetime.now().date()
    heute = datetime.now().date()
    zustand = {"jahr": basis.year, "monat": basis.month}

    kopf = tk.Frame(popup, bg=WHITE)
    kopf.pack(fill="x", padx=8, pady=8)
    raster = tk.Frame(popup, bg=WHITE)
    raster.pack(padx=8, pady=(0, 8))
    lbl = tk.Label(kopf, font=FONT_B, bg=WHITE, fg=TEXT, width=18)

    def blaettern(delta):
        m = zustand["monat"] + delta
        zustand["jahr"] += (m - 1) // 12
        zustand["monat"] = (m - 1) % 12 + 1
        zeichnen()

    def waehlen(tag):
        var.set(f"{tag:02d}.{zustand['monat']:02d}.{zustand['jahr']}")
        popup.destroy()

    def zeichnen():
        for w in raster.winfo_children():
            w.destroy()
        j, m = zustand["jahr"], zustand["monat"]
        lbl.config(text=f"{MONATE[m - 1]} {j}")
        for spalte, wt in enumerate(["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]):
            tk.Label(raster, text=wt, font=FONT_SM, bg=WHITE, fg=TEXT2, width=3).grid(row=0, column=spalte)
        for r, woche in enumerate(calendar.Calendar().monthdayscalendar(j, m), start=1):
            for spalte, tag in enumerate(woche):
                if not tag:
                    continue
                ist_gewaehlt = gewaehlt is not None and (j, m, tag) == (gewaehlt.year, gewaehlt.month, gewaehlt.day)
                ist_heute = (j, m, tag) == (heute.year, heute.month, heute.day)
                tk.Button(raster, text=str(tag), font=FONT_B if ist_heute else FONT_SM,
                          bg=ACCENT if ist_gewaehlt else WHITE, fg=WHITE if ist_gewaehlt else TEXT,
                          relief="flat", width=3, cursor="hand2",
                          command=lambda t=tag: waehlen(t)).grid(row=r, column=spalte, padx=1, pady=1)

    tk.Button(kopf, text="<", font=FONT_B, bg=BG2, fg=TEXT, relief="flat", padx=10,
              command=lambda: blaettern(-1)).pack(side="left")
    lbl.pack(side="left", expand=True)
    tk.Button(kopf, text=">", font=FONT_B, bg=BG2, fg=TEXT, relief="flat", padx=10,
              command=lambda: blaettern(1)).pack(side="right")
    tk.Button(popup, text="Heute", font=FONT_SM, bg=WHITE, fg=ACCENT, relief="flat", cursor="hand2",
              command=lambda: var.set(heute.strftime(config.DATUMSFORMAT)) or popup.destroy()
              ).pack(pady=(0, 8))
    zeichnen()
    zentrieren(popup, parent.winfo_toplevel())
    popup.wait_visibility()
    popup.grab_set()
