"""Dialogfenster: Labor anlegen/bearbeiten/Details, Level-Eingabe, Verschieben, PDF-Export."""
from __future__ import annotations

import copy
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

from .. import labor_db, scoring
from .. import pdf_export as pdf
from ..storage import neue_id
from .widgets import (BG, BG2, BORDER, FONT, FONT_B, FONT_SM, TEXT, TEXT2, WHITE,
                      ScrollFrame, button, combobox, dialog, eingabe, zeile)

MONAT_WERTE = [f"{i:02d}" for i in range(1, 13)]


def jahr_werte():
    jetzt = datetime.now().year
    return [str(j) for j in range(2022, jetzt + 3)]


def knopfleiste(parent, ok_text, ok_cmd, abbrechen_cmd) -> tk.Frame:
    bf = tk.Frame(parent, bg=WHITE)
    bf.pack(fill="x", padx=20, pady=(4, 14), side="bottom")
    button(bf, ok_text, ok_cmd).pack(side="right")
    button(bf, "Abbrechen", abbrechen_cmd, art="sekundaer").pack(side="right", padx=8)
    return bf


# ── Labor anlegen ─────────────────────────────────────────────────────────────

def labor_anlegen(app) -> None:
    win = dialog(app, "Neues Labor anlegen", "360x200")
    f = tk.Frame(win, bg=WHITE)
    f.pack(fill="x", padx=20, pady=16)
    tk.Label(f, text="Laborcode (z. B. DE92)", font=FONT_SM, bg=WHITE, fg=TEXT2).pack(anchor="w")
    v_code = tk.StringVar()
    e = eingabe(f, v_code, 28)
    e.pack(fill="x", ipady=5, pady=(4, 0))
    e.focus_set()

    def speichern(*_):
        code = v_code.get().strip().upper()
        if not code:
            messagebox.showwarning("Fehler", "Bitte einen Laborcode eingeben.", parent=win)
            return
        try:
            app.store.labor_anlegen(code)
        except ValueError as err:
            messagebox.showwarning("Fehler", str(err), parent=win)
            return
        if app.db_ok:
            app.db_ausfuehren(lambda: labor_db.labor_nach_code(code) or labor_db.labor_anlegen(code),
                              "Labor in Access anlegen")
        win.destroy()
        app.labor_liste_aktualisieren()
        app.labor_waehlen(code)

    e.bind("<Return>", speichern)
    knopfleiste(win, "Anlegen", speichern, win.destroy)


# ── Labor-Details / Bearbeiten (nur mit Access) ───────────────────────────────

def labor_details(app, laborcode: str) -> None:
    win = dialog(app, f"Details – {laborcode}", "520x480", modal=False)
    inhalt = tk.Frame(win, bg=WHITE)
    inhalt.pack(fill="both", expand=True, padx=20, pady=16)

    def zeige(label, wert):
        f = tk.Frame(inhalt, bg=WHITE)
        f.pack(fill="x", pady=3)
        tk.Label(f, text=label, font=FONT_SM, bg=WHITE, fg=TEXT2, width=18, anchor="w").pack(side="left")
        tk.Label(f, text=wert or "–", font=FONT, bg=WHITE, fg=TEXT, anchor="w",
                 wraplength=320, justify="left").pack(side="left")

    eintraege = app.store.daten.get(laborcode, [])
    zeige("Laborcode", laborcode)
    zeige("Einträge", str(len(eintraege)))
    zeige("Produkte", ", ".join(app.store.produkte(laborcode)))

    lab, aps = None, []
    if app.db_ok:
        try:
            lab = labor_db.labor_nach_code(laborcode)
            aps = labor_db.aps_fuer_labor(lab["LaborID"]) if lab else []
        except Exception as err:
            zeige("Access-DB", f"Fehler: {err}")
    if lab:
        tk.Label(inhalt, text="Stammdaten", font=FONT_B, bg=WHITE, fg=TEXT).pack(anchor="w", pady=(12, 4))
        for feld in ("Laborname", "Adresse", "Telefon", "Notiz"):
            zeige(feld, lab.get(feld))
        if aps:
            tk.Label(inhalt, text="Ansprechpartner", font=FONT_B, bg=WHITE, fg=TEXT).pack(anchor="w", pady=(12, 4))
            for ap in aps:
                af = tk.Frame(inhalt, bg=BG2, highlightthickness=1, highlightbackground=BORDER)
                af.pack(fill="x", pady=3)
                tk.Label(af, text=f"{ap['Name']}  ·  {ap.get('Funktion') or ''}", font=FONT_B,
                         bg=BG2, fg=TEXT, padx=10).pack(anchor="w", pady=(4, 0))
                tk.Label(af, text=f"{ap.get('Email') or ''}   {ap.get('Telefon') or ''}", font=FONT_SM,
                         bg=BG2, fg=TEXT2, padx=10).pack(anchor="w", pady=(0, 4))
    elif app.db_ok:
        tk.Label(inhalt, text="Keine Stammdaten in der Access-DB.", font=FONT_SM,
                 bg=WHITE, fg=TEXT2).pack(anchor="w", pady=8)

    button(win, "Schließen", win.destroy, art="sekundaer").pack(side="right", padx=20, pady=12)


def labor_bearbeiten(app, laborcode: str) -> None:
    if not app.db_ok:
        messagebox.showinfo("Hinweis", "Stammdaten können nur mit Verbindung zur Access-DB bearbeitet werden.")
        return
    try:
        lab = labor_db.labor_nach_code(laborcode)
        if not lab:
            if not messagebox.askyesno("Labor fehlt", f"'{laborcode}' ist nicht in der Access-DB. Jetzt anlegen?"):
                return
            labor_db.labor_anlegen(laborcode)
            lab = labor_db.labor_nach_code(laborcode)
        aps = labor_db.aps_fuer_labor(lab["LaborID"])
    except Exception as err:
        messagebox.showerror("Fehler", f"Access-DB: {err}")
        return

    win = dialog(app, f"Bearbeiten – {laborcode}", "580x600")
    sf = ScrollFrame(win)
    sf.pack(fill="both", expand=True)
    inhalt = sf.inhalt

    tk.Label(inhalt, text="Stammdaten", font=FONT_B, bg=WHITE, fg=TEXT).pack(anchor="w", padx=20, pady=(14, 4))
    felder = {}
    for name in ("Laborname", "Telefon", "Notiz"):
        felder[name] = tk.StringVar(value=lab.get(name) or "")
        f = tk.Frame(inhalt, bg=WHITE)
        f.pack(fill="x", padx=20)
        zeile(f, name, felder[name], breite=36, label_breite=14)
    f = tk.Frame(inhalt, bg=WHITE)
    f.pack(fill="x", padx=20, pady=4)
    tk.Label(f, text="Adresse", font=FONT_SM, bg=WHITE, fg=TEXT2, width=14, anchor="nw").pack(side="left")
    adresse = tk.Text(f, font=FONT, width=36, height=3, relief="flat", highlightthickness=1,
                      highlightbackground=BORDER, bg=BG)
    adresse.insert("1.0", lab.get("Adresse") or "")
    adresse.pack(side="left", fill="x", expand=True)

    tk.Label(inhalt, text="Ansprechpartner", font=FONT_B, bg=WHITE, fg=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
    ap_rahmen = tk.Frame(inhalt, bg=WHITE)
    ap_rahmen.pack(fill="x", padx=20)
    ap_zeilen = []  # dicts mit id, vars, geloescht

    def ap_zeile(ap=None):
        ap = ap or {}
        rahmen = tk.Frame(ap_rahmen, bg=BG2, highlightthickness=1, highlightbackground=BORDER)
        rahmen.pack(fill="x", pady=4)
        eintrag = {"id": ap.get("APId"), "geloescht": False,
                   "vars": {k: tk.StringVar(value=ap.get(k) or "") for k in ("Name", "Funktion", "Email", "Telefon")}}
        for paar in (("Name", "Funktion"), ("Email", "Telefon")):
            r = tk.Frame(rahmen, bg=BG2)
            r.pack(fill="x", padx=8, pady=3)
            for k in paar:
                tk.Label(r, text=k, font=FONT_SM, bg=BG2, fg=TEXT2, width=8, anchor="w").pack(side="left")
                eingabe(r, eintrag["vars"][k], 20, bg=WHITE).pack(side="left", padx=(0, 12), ipady=3)

        def entfernen():
            eintrag["geloescht"] = True
            rahmen.destroy()
        tk.Button(rahmen, text="✕ entfernen", font=FONT_SM, bg=BG2, fg=TEXT2, relief="flat",
                  cursor="hand2", command=entfernen).pack(anchor="e", padx=8, pady=(0, 4))
        ap_zeilen.append(eintrag)

    for ap in aps:
        ap_zeile(ap)
    button(inhalt, "+ Ansprechpartner", ap_zeile, art="sekundaer").pack(anchor="w", padx=20, pady=(4, 16))

    def speichern():
        name = felder["Laborname"].get().strip()
        if not name:
            messagebox.showwarning("Fehler", "Laborname darf nicht leer sein.", parent=win)
            return
        try:
            labor_db.labor_bearbeiten(lab["LaborID"], {
                "Laborname": name, "Adresse": adresse.get("1.0", "end").strip(),
                "Telefon": felder["Telefon"].get().strip(), "Notiz": felder["Notiz"].get().strip()})
            for ap in ap_zeilen:
                werte = {k: v.get().strip() for k, v in ap["vars"].items()}
                if ap["geloescht"]:
                    if ap["id"]:
                        labor_db.ap_loeschen(ap["id"], laborcode)
                elif ap["id"]:
                    labor_db.ap_bearbeiten(ap["id"], laborcode, werte)
                elif werte["Name"]:
                    labor_db.ap_anlegen(lab["LaborID"], laborcode, werte["Name"], werte["Email"],
                                        werte["Telefon"], werte["Funktion"])
        except Exception as err:
            messagebox.showerror("Fehler", str(err), parent=win)
            return
        messagebox.showinfo("Gespeichert", "Änderungen gespeichert und protokolliert.", parent=win)
        win.destroy()

    knopfleiste(win, "Speichern", speichern, win.destroy)


def aenderungsprotokoll(app, laborcode: str) -> None:
    try:
        zeilen = labor_db.aenderungslog(laborcode, limit=200)
    except Exception as err:
        messagebox.showerror("Fehler", f"Access-DB: {err}")
        return
    from .widgets import tabelle
    win = dialog(app, f"Änderungsprotokoll – {laborcode}", "900x500", modal=False)
    tree = tabelle(win, {"Zeitpunkt": (140, "w"), "Tabelle": (130, "w"), "Feld": (110, "w"),
                         "Alt": (160, "w"), "Neu": (160, "w"), "Aktion": (70, "center"),
                         "Benutzer": (90, "w")})
    for z in zeilen:
        zeit = z["GeaendertAm"].strftime("%d.%m.%Y %H:%M") if z.get("GeaendertAm") else ""
        tree.insert("", "end", values=(zeit, z["Tabelle"], z["Feld"], z["AlterWert"],
                                       z["NeuerWert"], z["Aktion"], z["GeaendertVon"]))


# ── Eintrag verschieben ───────────────────────────────────────────────────────

def eintrag_verschieben(app, eintrag_id: str) -> None:
    labor, eintrag = app.store.finden(eintrag_id)
    if eintrag is None:
        return
    ziele = [l for l in app.store.labore() if l != labor]
    if not ziele:
        messagebox.showinfo("Verschieben", "Es gibt kein anderes Labor.")
        return
    win = dialog(app, "Eintrag verschieben", "400x200")
    f = tk.Frame(win, bg=WHITE)
    f.pack(fill="x", padx=20, pady=12)
    tk.Label(f, text=f"{eintrag['produkt']} {eintrag['konzentration']}  ·  {eintrag['monat']}  ·  aktuell bei {labor}",
             font=FONT, bg=WHITE, fg=TEXT).pack(anchor="w", pady=(0, 8))
    tk.Label(f, text="Verschieben zu Labor:", font=FONT_SM, bg=WHITE, fg=TEXT2).pack(anchor="w")
    ziel = tk.StringVar(value=ziele[0])
    combobox(f, ziel, ziele, 26).pack(anchor="w", pady=(4, 0))

    def ok():
        app.store.eintrag_verschieben(eintrag_id, ziel.get())
        if app.db_ok:
            app.db_ausfuehren(lambda: (labor_db.bewertung_loeschen(labor, eintrag),
                                       labor_db.bewertung_speichern(ziel.get(), eintrag)),
                              "Eintrag in Access verschieben")
        win.destroy()
        app.alles_aktualisieren()
        app.status(f"Eintrag nach {ziel.get()} verschoben.")

    knopfleiste(win, "Verschieben", ok, win.destroy)


# ── Level-Eingabe ─────────────────────────────────────────────────────────────

def level_eingabe(app, labor: str, n_level: int = 3) -> None:
    """Mehrere Level (L1, L2, …) desselben Produkts in einem Rutsch erfassen."""
    win = dialog(app, f"Level-Eingabe  ·  {labor}")
    win.geometry("1100x720")
    sf = ScrollFrame(win)
    sf.pack(fill="both", expand=True)
    inhalt = sf.inhalt
    f = app.formular  # vorbelegen mit den Werten aus der Monatseingabe

    sec1 = tk.Frame(inhalt, bg=WHITE)
    sec1.pack(fill="x", padx=30, pady=(16, 0))
    tk.Label(sec1, text="Gemeinsame Felder (gelten für alle Level)", font=FONT_B,
             bg=WHITE, fg=TEXT).pack(anchor="w", pady=(0, 6))
    tk.Frame(sec1, bg=BORDER, height=1).pack(fill="x", pady=(0, 10))
    spalten = tk.Frame(sec1, bg=WHITE)
    spalten.pack(fill="x")
    links = tk.Frame(spalten, bg=WHITE)
    links.pack(side="left", fill="both", expand=True, padx=(0, 20))
    rechts = tk.Frame(spalten, bg=WHITE)
    rechts.pack(side="left", fill="both", expand=True)

    v = {k: tk.StringVar(value=f[k].get()) for k in
         ("monat", "jahr", "produkt", "q_produkt", "q_gemessen", "z_versand", "z_eingang",
          "k_laborpreis", "s_berichtet", "s_behoben", "s_anfrage", "s_antwort", "s_nachfragen")}
    kostenlos = tk.BooleanVar(value=app.k_kostenlos.get())

    mf = tk.Frame(links, bg=WHITE)
    mf.pack(fill="x", pady=4)
    tk.Label(mf, text="Monat / Jahr", font=FONT_SM, bg=WHITE, fg=TEXT2, width=28, anchor="w").pack(side="left")
    combobox(mf, v["monat"], MONAT_WERTE, 5).pack(side="left", padx=(0, 6))
    combobox(mf, v["jahr"], jahr_werte(), 7).pack(side="left")
    pf = tk.Frame(links, bg=WHITE)
    pf.pack(fill="x", pady=4)
    tk.Label(pf, text="Produkt / Analyt", font=FONT_SM, bg=WHITE, fg=TEXT2, width=28, anchor="w").pack(side="left")
    combobox(pf, v["produkt"], app.store.produkte(), 22, nur_lesen=False).pack(side="left")
    zeile(links, "Gesamte Analyten im Produkt", v["q_produkt"], 6)
    zeile(links, "Gemessene Analyten", v["q_gemessen"], 6)
    zeile(links, "Versanddatum", v["z_versand"], datum=True)
    zeile(links, "Eingangsdatum der Werte", v["z_eingang"], datum=True)

    kf = tk.Frame(rechts, bg=WHITE)
    kf.pack(fill="x", pady=4)
    tk.Label(kf, text="Laborpreis (EUR)", font=FONT_SM, bg=WHITE, fg=TEXT2, width=28, anchor="w").pack(side="left")
    eingabe(kf, v["k_laborpreis"], 10).pack(side="left", ipady=4, padx=(0, 8))
    tk.Checkbutton(kf, text="Kostenlos", variable=kostenlos, font=FONT_SM, bg=WHITE,
                   activebackground=WHITE).pack(side="left")
    zeile(rechts, "Berichtete Fehler", v["s_berichtet"], 6)
    zeile(rechts, "Behobene Fehler", v["s_behoben"], 6)
    zeile(rechts, "Datum Anfrage", v["s_anfrage"], datum=True)
    zeile(rechts, "Datum Antwort", v["s_antwort"], datum=True)
    zeile(rechts, "Anzahl Nachfragen", v["s_nachfragen"], 6)

    # Level-Tabelle
    sec2 = tk.Frame(inhalt, bg=WHITE)
    sec2.pack(fill="x", padx=30, pady=(16, 0))
    kopf = tk.Frame(sec2, bg=WHITE)
    kopf.pack(fill="x", pady=(0, 6))
    tk.Label(kopf, text="Level-spezifisch", font=FONT_B, bg=WHITE, fg=TEXT).pack(side="left")
    anzahl = tk.StringVar(value=str(n_level))
    tk.Label(kopf, text="Anzahl Level:", font=FONT_SM, bg=WHITE, fg=TEXT2).pack(side="left", padx=(30, 4))
    eingabe(kopf, anzahl, 4).pack(side="left", ipady=3)
    tk.Frame(sec2, bg=BORDER, height=1).pack(fill="x", pady=(0, 6))

    breiten = [("Konzentration", 14), ("Prüfnummer", 14), ("Verworfene Analyten", 18), ("Kommentar", 40)]
    hk = tk.Frame(sec2, bg=BG2)
    hk.pack(fill="x")
    for text, b in breiten:
        tk.Label(hk, text=text, font=FONT_SM, bg=BG2, fg=TEXT2, width=b, anchor="w").pack(side="left", padx=6, pady=5)
    zeilen_rahmen = tk.Frame(sec2, bg=WHITE)
    zeilen_rahmen.pack(fill="x")
    level_zeilen = []

    def zeilen_erzeugen(*_):
        try:
            n = max(1, min(20, int(anzahl.get())))
        except ValueError:
            return
        alt = [{k: var.get() for k, var in z.items()} for z in level_zeilen]
        for w in zeilen_rahmen.winfo_children():
            w.destroy()
        level_zeilen.clear()
        for i in range(n):
            werte = alt[i] if i < len(alt) else {"konz": f"L{i + 1}"}
            r = tk.Frame(zeilen_rahmen, bg=WHITE if i % 2 == 0 else BG)
            r.pack(fill="x", pady=1)
            vars_ = {k: tk.StringVar(value=werte.get(k, "")) for k in ("konz", "pruef", "verw", "komm")}
            for (k, (_, b)) in zip(("konz", "pruef", "verw", "komm"), breiten):
                eingabe(r, vars_[k], b).pack(side="left", padx=6, pady=3, ipady=3)
            level_zeilen.append(vars_)

    button(kopf, "Übernehmen", zeilen_erzeugen, art="sekundaer", pady=2).pack(side="left", padx=8)
    zeilen_erzeugen()

    def zahl(name, var):
        text = var.get().strip()
        z = scoring.parse_zahl(text)
        if text and z is None:
            raise ValueError(f"'{text}' bei {name} ist keine Zahl.")
        return z

    def alle_speichern():
        produkt = v["produkt"].get().strip()
        if not produkt:
            messagebox.showwarning("Fehler", "Bitte ein Produkt angeben.", parent=win)
            return
        try:
            gemeinsam = {
                "monat": f"{v['jahr'].get()}-{v['monat'].get()}",
                "produkt": produkt,
                "zuverlaessigkeit": {"versand": v["z_versand"].get().strip(),
                                     "eingang": v["z_eingang"].get().strip()},
                "kosten": {"laborpreis": 0.0 if kostenlos.get() else zahl("Laborpreis", v["k_laborpreis"]),
                           "kostenlos": kostenlos.get()},
                "service": {"berichtet": zahl("Berichtete Fehler", v["s_berichtet"]),
                            "behoben": zahl("Behobene Fehler", v["s_behoben"]),
                            "anfrage": v["s_anfrage"].get().strip(),
                            "antwort": v["s_antwort"].get().strip(),
                            "nachfragen": zahl("Nachfragen", v["s_nachfragen"])},
            }
            gesamt = zahl("Gesamte Analyten", v["q_produkt"])
            gemessen = zahl("Gemessene Analyten", v["q_gemessen"])
            eintraege = []
            for i, z in enumerate(level_zeilen, start=1):
                if not any(z[k].get().strip() for k in ("pruef", "verw", "komm")):
                    continue  # leere Zeile überspringen
                e = dict(copy.deepcopy(gemeinsam), id=neue_id(), konzentration=z["konz"].get().strip(),
                         pruefnummer=z["pruef"].get().strip(), kommentar=z["komm"].get().strip(),
                         qualitaet={"verworfen": zahl(f"Verworfene (Zeile {i})", z["verw"]),
                                    "gemessen": gemessen, "produkt": gesamt})
                eintraege.append(e)
        except ValueError as err:
            messagebox.showwarning("Ungültige Eingabe", str(err), parent=win)
            return
        if not eintraege:
            messagebox.showwarning("Fehler", "Keine Level-Zeile ausgefüllt.", parent=win)
            return

        hinweise = sorted({h for e in eintraege for h in scoring.plausibilitaet(e)})
        if hinweise and not messagebox.askyesno(
                "Bitte prüfen", "\n".join(f"• {h}" for h in hinweise) + "\n\nTrotzdem speichern?", parent=win):
            return
        doppelt = [e for e in eintraege if app.store.duplikat(labor, e)]
        if doppelt and not messagebox.askyesno(
                "Überschreiben?",
                f"{len(doppelt)} Level mit gleicher Prüfnummer existieren bereits und werden überschrieben.",
                parent=win):
            return
        for e in eintraege:
            alt = app.store.duplikat(labor, e)
            if alt:
                e["id"] = alt["id"]
            app.eintrag_ablegen(labor, e)
        win.destroy()
        app.alles_aktualisieren()
        app.status(f"{len(eintraege)} Level für {labor} gespeichert.")

    knopfleiste(win, "Alle speichern", alle_speichern, win.destroy)


# ── PDF-Export ────────────────────────────────────────────────────────────────

def pdf_export(app, modus: str = "uebersicht") -> None:
    titel = "Übersicht exportieren" if modus == "uebersicht" else "Detail + Berechnung exportieren"
    win = dialog(app, titel, "400x230")
    gf = tk.Frame(win, bg=WHITE)
    gf.pack(fill="x", padx=20, pady=16)
    jahre = app.store.jahre() or [str(datetime.now().year)]
    jahr = tk.StringVar(value=jahre[0])
    produkt = tk.StringVar(value="Alle")
    for label, var, werte in (("Jahr", jahr, jahre), ("Produkt", produkt, ["Alle"] + app.store.produkte())):
        r = tk.Frame(gf, bg=WHITE)
        r.pack(fill="x", pady=4)
        tk.Label(r, text=label, font=FONT, bg=WHITE, fg=TEXT2, width=12, anchor="w").pack(side="left")
        combobox(r, var, werte, 22).pack(side="left")

    def exportieren():
        art = "Übersicht" if modus == "uebersicht" else "Detail"
        pfad = filedialog.asksaveasfilename(
            parent=win, title="PDF speichern", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=f"Lieferantenbewertung_{art}_{jahr.get()}.pdf")
        if not pfad:
            return
        try:
            funktion = pdf.erstelle_uebersicht if modus == "uebersicht" else pdf.erstelle_detail
            funktion(pfad, app.store.daten, jahr.get(), produkt.get())
        except ImportError:
            messagebox.showerror("Fehler", "Für den PDF-Export wird das Paket 'reportlab' benötigt.", parent=win)
            return
        except Exception as err:
            messagebox.showerror("Fehler", str(err), parent=win)
            return
        win.destroy()
        app.status(f"PDF gespeichert: {pfad}")

    knopfleiste(win, "Exportieren", exportieren, win.destroy)


# ── Laborwechsel mit ungespeicherten Daten ────────────────────────────────────

def frage_laborwechsel(app, ziel: str) -> str:
    """-> 'verwerfen' | 'behalten' | 'abbrechen'"""
    win = dialog(app, "Laborwechsel", "380x170")
    ergebnis = tk.StringVar(value="abbrechen")
    tk.Label(win, text=f"Zu Labor '{ziel}' wechseln.\nEingegebene Daten verwerfen oder behalten?",
             font=FONT, bg=WHITE, fg=TEXT, justify="center").pack(pady=(16, 12))
    bf = tk.Frame(win, bg=WHITE)
    bf.pack()

    def waehle(wert):
        ergebnis.set(wert)
        win.destroy()
    button(bf, "Verwerfen", lambda: waehle("verwerfen"), art="gefahr").pack(side="left", padx=6)
    button(bf, "Behalten", lambda: waehle("behalten")).pack(side="left", padx=6)
    button(bf, "Abbrechen", lambda: waehle("abbrechen"), art="sekundaer").pack(side="left", padx=6)
    win.wait_window()
    return ergebnis.get()
