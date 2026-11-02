"""PDF-Berichte (benötigt reportlab)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from xml.sax.saxutils import escape

from . import config, scoring
from .storage import labor_sortierschluessel

SCHWARZ = "#1A1A1A"
GRAU = "#888888"
HELLGRAU = "#F5F5F5"
LINIE = "#DDDDDD"
BLAU = "#2E6FAD"
STATUS_FARBEN = {"ok": "#D5EFDF", "warn": "#FCE9D2", "bad": "#F6D5D2", "none": "#FFFFFF"}


def _fmt(v, einheit=""):
    return f"{v:.1f}{einheit}" if v is not None else "–"


def _ganzzahl(v):
    z = scoring.parse_zahl(v)
    return str(int(z)) if z is not None else "–"


def _gewichte_text():
    return " / ".join(f"{config.KATEGORIE_NAMEN[k]} {g}" for k, g in config.GEWICHTE.items())


def _gefiltert(daten, jahr, produkt_filter):
    for labor in sorted(daten, key=labor_sortierschluessel):
        for e in sorted(daten[labor], key=lambda x: (x.get("produkt", ""), x.get("monat", ""))):
            if not e.get("monat", "").startswith(jahr):
                continue
            if produkt_filter != "Alle" and e.get("produkt", "") != produkt_filter:
                continue
            yield labor, e


def _basis(pfad):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate
    return SimpleDocTemplate(pfad, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                             topMargin=2 * cm, bottomMargin=2 * cm,
                             title="Lieferantenbewertung", author=config.FIRMA or "")


def _stile():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    basis = getSampleStyleSheet()["Normal"]
    c = colors.HexColor
    return {
        "titel": ParagraphStyle("titel", parent=basis, fontSize=16, fontName="Helvetica-Bold",
                                textColor=c(SCHWARZ), spaceAfter=4, leading=20),
        "sub": ParagraphStyle("sub", parent=basis, fontSize=8, textColor=c(GRAU), spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=basis, fontSize=11, fontName="Helvetica-Bold",
                             textColor=c(SCHWARZ), spaceBefore=14, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=basis, fontSize=9, fontName="Helvetica-Bold",
                             textColor=c(GRAU), spaceBefore=8, spaceAfter=2),
        "text": ParagraphStyle("text", parent=basis, fontSize=8, textColor=c(GRAU)),
        "formel": ParagraphStyle("formel", parent=basis, fontSize=8, textColor=c(BLAU),
                                 fontName="Helvetica-Bold", leftIndent=20),
    }


def _kopf(story, titel, stile):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, Paragraph, Spacer
    story.append(Paragraph(escape(titel), stile["titel"]))
    zeile = f"Erstellt am {datetime.now().strftime(config.DATUMSFORMAT)}"
    if config.FIRMA:
        zeile = f"{escape(config.FIRMA)}  |  {zeile}"
    story.append(Paragraph(zeile, stile["sub"]))
    story.append(Paragraph(
        f"Status: ab {config.GRENZE_FREIGEGEBEN} % Freigegeben, ab {config.GRENZE_BEOBACHTUNG} % "
        f"Beobachtung, darunter Gesperrt  |  Gewichte: {_gewichte_text()}", stile["sub"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor(LINIE)))
    story.append(Spacer(1, 0.3 * cm))


def erstelle_uebersicht(pfad: str, daten: dict, jahr: str, produkt_filter: str = "Alle") -> None:
    """Je Produkt eine Tabelle mit den Durchschnittsscores aller Labore."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    stile = _stile()
    story = []
    zusatz = f" – {produkt_filter}" if produkt_filter != "Alle" else ""
    _kopf(story, f"Lieferantenbewertung {jahr}{zusatz}", stile)

    benchmarks = scoring.benchmark_tabelle(daten)
    nach_produkt = defaultdict(lambda: defaultdict(list))
    for labor, e in _gefiltert(daten, jahr, produkt_filter):
        nach_produkt[e.get("produkt", "")][labor].append(e)

    if not nach_produkt:
        story.append(Paragraph(f"Keine Daten für {escape(jahr)} vorhanden.", stile["text"]))
        _basis(pfad).build(story)
        return

    for produkt in sorted(nach_produkt):
        story.append(Paragraph(escape(produkt or "(kein Produkt)"), stile["h2"]))
        zeilen = [["Labor", "Messungen", "Qualität", "Zuverl.", "Kosten", "Service", "Gesamt", "Status"]]
        status_keys = []
        for labor in sorted(nach_produkt[produkt], key=labor_sortierschluessel):
            eintraege = nach_produkt[produkt][labor]
            scores = [scoring.berechne_scores(e, benchmarks) for e in eintraege]
            gesamt = scoring.durchschnitt(s.gesamt for s in scores)
            key, text = scoring.status(gesamt)
            status_keys.append(key)
            zeilen.append([
                labor, str(len(eintraege)),
                _fmt(scoring.durchschnitt(s.qualitaet for s in scores)),
                _fmt(scoring.durchschnitt(s.zuverlaessigkeit for s in scores)),
                _fmt(scoring.durchschnitt(s.kosten for s in scores)),
                _fmt(scoring.durchschnitt(s.service for s in scores)),
                _fmt(gesamt), text,
            ])
        tabelle = Table(zeilen, colWidths=[2.2 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm,
                                           1.8 * cm, 1.8 * cm, 1.8 * cm, 2.4 * cm], repeatRows=1)
        stil = TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(GRAU)),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor(LINIE)),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTNAME", (6, 1), (6, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor(LINIE)),
        ])
        for zeile, key in enumerate(status_keys, start=1):
            stil.add("BACKGROUND", (7, zeile), (7, zeile), colors.HexColor(STATUS_FARBEN[key]))
        tabelle.setStyle(stil)
        story.append(tabelle)

    _basis(pfad).build(story)


def erstelle_detail(pfad: str, daten: dict, jahr: str, produkt_filter: str = "Alle") -> None:
    """Alle Einzelmessungen mit Rohdaten, Scores und den Berechnungsformeln."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                    Spacer, Table, TableStyle)

    stile = _stile()
    story = []
    zusatz = f" – {produkt_filter}" if produkt_filter != "Alle" else ""
    _kopf(story, f"Detail-Übersicht Lieferantenbewertung {jahr}{zusatz}", stile)

    benchmarks = scoring.benchmark_tabelle(daten)
    g = config.GEWICHTE
    aktuelles_labor = None
    for labor, e in _gefiltert(daten, jahr, produkt_filter):
        kopf = []
        if labor != aktuelles_labor:
            kopf = [Paragraph(escape(labor), stile["h2"]),
                    HRFlowable(width="100%", thickness=0.3, color=colors.HexColor(LINIE))]
            aktuelles_labor = labor

        q_d, z_d, k_d, s_d = (e.get(x) or {} for x in ("qualitaet", "zuverlaessigkeit", "kosten", "service"))
        sc = scoring.berechne_scores(e, benchmarks)
        _, status_text = scoring.status(sc.gesamt)
        teile = [e.get("produkt") or "–"]
        if e.get("konzentration"):
            teile.append(e["konzentration"])
        if e.get("pruefnummer"):
            teile.append(f"Prüfnr. {e['pruefnummer']}")
        teile.append(e.get("monat", ""))

        lp = scoring.parse_zahl(k_d.get("laborpreis"))
        bm = benchmarks.get(e.get("produkt", ""))
        zeilen = [
            [f"Qualität (Gewicht {g['qualitaet']})", ""],
            ["  Verworfene Analyten", _ganzzahl(q_d.get("verworfen"))],
            ["  Gemessene Analyten", _ganzzahl(q_d.get("gemessen"))],
            ["  Gesamte Analyten im Produkt", _ganzzahl(q_d.get("produkt"))],
            ["  Score", _fmt(sc.qualitaet, " %")],
            [f"Zuverlässigkeit (Gewicht {g['zuverlaessigkeit']})", ""],
            ["  Versanddatum", z_d.get("versand") or "–"],
            ["  Eingangsdatum Werte", z_d.get("eingang") or "–"],
            ["  Score", _fmt(sc.zuverlaessigkeit, " %")],
            [f"Kosten (Gewicht {g['kosten']})", ""],
            ["  Laborpreis", "kostenlos" if k_d.get("kostenlos") else (f"{lp:.2f} EUR" if lp else "–")],
            ["  Benchmark (Durchschnitt aller Labore)", f"{bm:.2f} EUR" if bm else "–"],
            ["  Score", _fmt(sc.kosten, " %")],
            [f"Service (Gewicht {g['service']})", ""],
            ["  Berichtete Fehler", _ganzzahl(s_d.get("berichtet"))],
            ["  Behobene Fehler", _ganzzahl(s_d.get("behoben"))],
            ["  Datum Anfrage", s_d.get("anfrage") or "–"],
            ["  Datum Antwort", s_d.get("antwort") or "–"],
            ["  Nachfragen", _ganzzahl(s_d.get("nachfragen"))],
            ["  Score", _fmt(sc.service, " %")],
            ["GESAMTSCORE", f"{_fmt(sc.gesamt, ' %')}  ->  {status_text}" if sc.gesamt is not None else "–"],
        ]
        tabelle = Table(zeilen, colWidths=[9 * cm, 6 * cm])
        stil = TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEBELOW", (0, 0), (-1, -1), 0.2, colors.HexColor(LINIE)),
        ])
        for i, (label, _) in enumerate(zeilen):
            if not label.startswith("  "):
                stil.add("FONTNAME", (0, i), (-1, i), "Helvetica-Bold")
                stil.add("BACKGROUND", (0, i), (-1, i), colors.HexColor(HELLGRAU))
            elif label == "  Score":
                stil.add("FONTNAME", (1, i), (1, i), "Helvetica-Bold")
                stil.add("TEXTCOLOR", (1, i), (1, i), colors.HexColor(BLAU))
        tabelle.setStyle(stil)

        block = kopf + [Spacer(1, 0.2 * cm), Paragraph(escape("  |  ".join(teile)), stile["h3"]), tabelle]
        if e.get("kommentar", "").strip():
            block.append(Paragraph("Kommentar: " + escape(e["kommentar"].strip()), stile["text"]))
        story.append(KeepTogether(block))

    if aktuelles_labor is None:
        story.append(Paragraph(f"Keine Daten für {escape(jahr)} vorhanden.", stile["text"]))

    # Formelseite
    story.append(PageBreak())
    story.append(Paragraph("Berechnungsgrundlagen", stile["titel"]))
    story.append(Spacer(1, 0.3 * cm))
    qa, qb = int(config.QUALITAET_ANTEIL_FEHLERQUOTE * 100), int(config.QUALITAET_ANTEIL_ANALYTAUSWAHL * 100)
    formeln = [
        ("Gesamtscore",
         "Gewichteter Durchschnitt der vorhandenen Kategorien. Fehlende Kategorien werden "
         "herausgerechnet, die Gewichte werden auf die vorhandenen Kategorien normiert.",
         [f"Gesamt = (Q×{g['qualitaet']} + Z×{g['zuverlaessigkeit']} + K×{g['kosten']} + S×{g['service']}) "
          f"/ Summe der Gewichte der vorhandenen Kategorien"]),
        ("Qualitätsscore (Q)", f"Fehlerquote ({qa} %) und Analytauswahl ({qb} %).",
         ["Fehlerquote   = 100 - (Verworfene / Gesamte Analyten) × 100",
          "Analytauswahl = (Gemessene / Gesamte Analyten) × 100",
          f"Q = Fehlerquote × {qa/100:.2f} + Analytauswahl × {qb/100:.2f}"]),
        ("Zuverlässigkeitsscore (Z)",
         f"Termintreue in Werktagen (ohne Wochenenden), abzüglich {config.TERMINTREUE_PUFFER} Tage Puffer.",
         ["<= 14 Tage -> 100 %", "15–21 Tage -> 70 %", "22–28 Tage -> 30 %", "> 28 Tage -> 0 %"]),
        ("Kostenscore (K)", "Vergleich mit dem Durchschnittspreis aller Labore für dasselbe Produkt.",
         ["K = min(100, Benchmark / Laborpreis × 100)", "Kostenloses Labor -> K = 100"]),
        ("Servicescore (S)", "Durchschnitt aus Behebungsrate und Reaktionszeit (sofern vorhanden).",
         ["Behebungsrate = (Behobene / Berichtete Fehler) × 100",
          "Reaktionszeit: <= 3 Tage = 100 %, 4–7 Tage = 70 %, danach -10 % pro Tag",
          "Je Nachfrage -10 % auf die Reaktionszeit"]),
    ]
    for titel, erklaerung, zeilen in formeln:
        story.append(Paragraph(titel, stile["h2"]))
        story.append(Paragraph(escape(erklaerung), stile["text"]))
        for z in zeilen:
            story.append(Paragraph(escape(z), stile["formel"]))

    _basis(pfad).build(story)
