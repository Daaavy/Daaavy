"""Diagramme (matplotlib). Liefert Figure-Objekte, die die Oberfläche einbettet."""
from __future__ import annotations

from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch

from . import config, scoring

PALETTE = ["#378ADD", "#1D9E75", "#D85A30", "#BA7517", "#993556",
           "#534AB7", "#639922", "#E24B4A", "#0F6E56", "#854F0B"]
STATUS_FARBE = {"ok": "#2E86AB", "warn": "#E0A030", "bad": "#C0504D", "none": "#D3D1C7"}
TEXT2 = "#888780"


def _achse_stylen(ax, gitter="y"):
    ax.set_facecolor("#FFFFFF")
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors=TEXT2, labelsize=8.5, length=0, pad=4)
    ax.grid(axis=gitter, color="#EFEFEB", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _grenzlinien(ax, horizontal=True):
    linie = ax.axhline if horizontal else ax.axvline
    for wert, farbe in ((config.GRENZE_FREIGEGEBEN, STATUS_FARBE["ok"]),
                        (config.GRENZE_BEOBACHTUNG, STATUS_FARBE["warn"])):
        linie(wert, color=farbe, linestyle=(0, (4, 3)), linewidth=1.2, alpha=0.7, zorder=2)


labor_kennzahlen = scoring.labor_kennzahlen  # Kompatibilität


def score_diagramm(kennzahlen: dict) -> Figure:
    labore = list(kennzahlen)
    fig = Figure(figsize=(14, max(4.2, 0.35 * len(labore) + 1.5)), facecolor="#F8F8F6")
    raster = fig.add_gridspec(1, 3, wspace=0.40, left=0.06, right=0.97, top=0.88, bottom=0.16)
    ax1, ax2, ax3 = (fig.add_subplot(raster[i]) for i in range(3))

    # 1) Gesamt-Score als Balken
    _achse_stylen(ax1, "x")
    ax1.grid(axis="y", visible=False)
    r = 0.52 * 0.42
    for i, labor in enumerate(labore):
        sc = kennzahlen[labor]["g"]
        v = sc or 0
        farbe = STATUS_FARBE[scoring.status(sc)[0]]
        ax1.add_patch(FancyBboxPatch((0, i - 0.26), 100, 0.52, boxstyle=f"round,pad=0,rounding_size={r}",
                                     facecolor="#E8F0F8", edgecolor="none", zorder=1))
        if v > 0:
            ax1.add_patch(FancyBboxPatch((0, i - 0.26), v, 0.52, boxstyle=f"round,pad=0,rounding_size={r}",
                                         facecolor=farbe, edgecolor="none", zorder=3))
        ax1.text(min(v + 2.5, 104), i, f"{v:.1f}" if sc is not None else "–", va="center", ha="left",
                 fontsize=9, color="#2C2C2A", fontweight="bold")
    _grenzlinien(ax1, horizontal=False)
    ax1.set_xlim(0, 116)
    ax1.set_ylim(len(labore) - 0.35, -0.65)  # erstes Labor oben
    ax1.set_yticks(range(len(labore)))
    ax1.set_yticklabels(labore, fontsize=9.5)
    ax1.set_title("Gesamt-Score (neuere Werte stärker gewichtet)", fontsize=10,
                  fontweight="bold", pad=12, loc="left")

    # 2) Kategorien als Farbtabelle (bleibt auch bei vielen Laboren lesbar)
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    kats = ["Qualität", "Zuverl.", "Kosten", "Service"]
    werte = np.array([[np.nan if kennzahlen[l][k] is None else kennzahlen[l][k] for k in "qzks"]
                      for l in labore], dtype=float)
    farbskala = LinearSegmentedColormap.from_list(
        "bewertung", [STATUS_FARBE["bad"], STATUS_FARBE["warn"], "#9CC9DF", STATUS_FARBE["ok"]]
    ).with_extremes(bad="#F1F1EE")
    ax2.imshow(np.ma.masked_invalid(werte), cmap=farbskala, vmin=0, vmax=100, aspect="auto")
    for (zeile, spalte), wert in np.ndenumerate(werte):
        ax2.text(spalte, zeile, "–" if np.isnan(wert) else f"{wert:.0f}", ha="center", va="center",
                 fontsize=8.5, color=TEXT2 if np.isnan(wert) else "#FFFFFF", fontweight="bold")
    ax2.set_xticks(range(4))
    ax2.set_xticklabels(kats, fontsize=9)
    ax2.xaxis.tick_top()
    ax2.set_yticks(range(len(labore)))
    ax2.set_yticklabels(labore, fontsize=9)
    ax2.tick_params(length=0, colors=TEXT2)
    for sp in ax2.spines.values():
        sp.set_visible(False)
    ax2.set_title("Kategorien (Durchschnitt)", fontsize=10, fontweight="bold", pad=24, loc="left")

    # 3) Verlauf – gemeinsame Monatsachse für alle Labore
    _achse_stylen(ax3)
    alle_monate = sorted({m for k in kennzahlen.values() for m in k["verlauf"] if m})
    pos = {m: i for i, m in enumerate(alle_monate)}
    for i, labor in enumerate(labore):
        punkte = [(pos[m], s) for m, s in sorted(kennzahlen[labor]["verlauf"].items())
                  if s is not None and m in pos]
        if not punkte:
            continue
        xs, ys = zip(*punkte)
        farbe = PALETTE[i % len(PALETTE)]
        ax3.plot(xs, ys, color=farbe, linewidth=2.2, label=labor, zorder=3)
        ax3.scatter(xs, ys, color=farbe, s=44, zorder=5, edgecolors="white", linewidths=1.8)
    if alle_monate:
        ax3.set_xticks(range(len(alle_monate)))
        ax3.set_xticklabels(alle_monate, rotation=38, ha="right", fontsize=8)
    _grenzlinien(ax3)
    ax3.set_ylim(0, 114)
    ax3.set_title("Verlauf (Monatsdurchschnitt)", fontsize=10, fontweight="bold", pad=12, loc="left")
    if len(labore) <= 8:
        ax3.legend(fontsize=8, loc="lower left", framealpha=0.95)
    return fig


def preis_diagramm(eintraege_je_labor: dict) -> Figure | None:
    """Durchschnittlicher Preis pro Lauf und pro gemessenem Analyt je Labor."""
    lp, ap = {}, {}
    for labor, eintraege in eintraege_je_labor.items():
        for e in eintraege:
            preis = scoring.parse_zahl((e.get("kosten") or {}).get("laborpreis"))
            gem = scoring.parse_zahl((e.get("qualitaet") or {}).get("gemessen"))
            if not preis or not gem:
                continue
            lp.setdefault(labor, []).append(preis)
            ap.setdefault(labor, []).append(preis / gem)
    if not lp:
        return None
    labore = list(lp)
    fig = Figure(figsize=(14, max(3.0, 0.3 * len(labore) + 1.4)), facecolor="#FFFFFF")
    ax_lp, ax_ap = fig.subplots(1, 2)
    fig.subplots_adjust(left=0.06, right=0.97, top=0.85, bottom=0.18, wspace=0.4)
    for ax, quelle, titel, einheit in ((ax_lp, lp, "Preis pro Lauf", "EUR"),
                                       (ax_ap, ap, "Preis pro gemessenem Analyt", "EUR / Analyt")):
        werte = [sum(quelle[l]) / len(quelle[l]) for l in labore]
        _achse_stylen(ax, "x")
        balken = ax.barh(labore, werte, color=[PALETTE[i % len(PALETTE)] for i in range(len(labore))],
                         alpha=0.85, zorder=3)
        maximum = max(werte) if werte else 1
        for b, v in zip(balken, werte):
            ax.text(v + maximum * 0.01, b.get_y() + b.get_height() / 2, f"{v:.2f} €",
                    va="center", fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, maximum * 1.2)
        ax.set_xlabel(einheit, fontsize=8, color=TEXT2)
        ax.set_title(titel, fontsize=10, fontweight="bold", pad=8, loc="left")
    return fig


def preisentwicklung_diagramm(verlauf: dict, breite_zoll: float = 10) -> Figure:
    """verlauf: {(labor, produkt): [{preis, datum, monat}, ...]}"""
    fig = Figure(figsize=(breite_zoll, 2.6), facecolor="#FFFFFF")
    ax = fig.add_subplot()
    fig.subplots_adjust(left=0.06, right=0.78, top=0.88, bottom=0.22)
    _achse_stylen(ax)
    alle_monate = sorted({p.get("monat", "") for v in verlauf.values() for p in v})
    pos = {m: i for i, m in enumerate(alle_monate)}
    for i, ((labor, produkt), punkte) in enumerate(verlauf.items()):
        farbe = PALETTE[i % len(PALETTE)]
        xs = [pos[p.get("monat", "")] for p in punkte]
        ys = [p["preis"] for p in punkte]
        ax.plot(xs, ys, color=farbe, linewidth=2.2, marker="o", markersize=5,
                label=f"{labor} / {produkt}", zorder=3, markerfacecolor="white",
                markeredgewidth=2, markeredgecolor=farbe)
        ax.annotate(f"  {ys[-1]:.2f} €", (xs[-1], ys[-1]), fontsize=7.5, color=farbe, va="center")
    ax.set_xticks(range(len(alle_monate)))
    ax.set_xticklabels(alle_monate, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("€", fontsize=8, color=TEXT2)
    ax.set_ylim(bottom=0)
    if len(verlauf) > 1:
        ax.legend(fontsize=7.5, frameon=False, loc="upper left", bbox_to_anchor=(1.08, 1.02),
                  ncol=2 if len(verlauf) > 14 else 1)
    return fig


def labor_verlauf_diagramm(kennzahl: dict, breite_zoll: float = 7) -> Figure:
    """Gesamtscore eines Labors je Monat (dick) mit den vier Kategorien (dünn)."""
    fig = Figure(figsize=(breite_zoll, 3.0), facecolor="#FFFFFF")
    ax = fig.add_subplot()
    fig.subplots_adjust(left=0.08, right=0.80, top=0.86, bottom=0.2)
    _achse_stylen(ax)
    monate = sorted(m for m in kennzahl["monate"] if m)
    xs = range(len(monate))
    linien = (("gesamt", "Gesamt", "#1A1A1A", 2.6), ("qualitaet", "Qualität", PALETTE[0], 1.4),
              ("zuverlaessigkeit", "Zuverl.", PALETTE[1], 1.4), ("kosten", "Kosten", PALETTE[2], 1.4),
              ("service", "Service", PALETTE[4], 1.4))
    for key, name, farbe, staerke in linien:
        punkte = [(x, kennzahl["monate"][m][key]) for x, m in zip(xs, monate)
                  if kennzahl["monate"][m][key] is not None]
        if not punkte:
            continue
        px, py = zip(*punkte)
        ax.plot(px, py, color=farbe, linewidth=staerke, marker="o", markersize=5 if key == "gesamt" else 3,
                label=name, zorder=4 if key == "gesamt" else 3, alpha=1 if key == "gesamt" else 0.75)
    _grenzlinien(ax)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(monate, rotation=30, ha="right", fontsize=8)
    ax.set_xlim(-0.5, max(len(monate) - 0.5, 0.5))
    ax.set_ylim(0, 105)
    ax.set_title("Verlauf je Monat", fontsize=10, fontweight="bold", loc="left", pad=8)
    ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.02, 1.0))
    return fig


def kategorie_diagramm(kennzahl: dict, breite_zoll: float = 5) -> Figure:
    """Durchschnitt der vier Kategorien eines Labors als waagerechte Balken."""
    fig = Figure(figsize=(breite_zoll, 3.0), facecolor="#FFFFFF")
    ax = fig.add_subplot()
    fig.subplots_adjust(left=0.30, right=0.94, top=0.86, bottom=0.12)
    _achse_stylen(ax, "x")
    kats = [("qualitaet", "Qualität"), ("zuverlaessigkeit", "Zuverlässigkeit"),
            ("kosten", "Kosten"), ("service", "Service")]
    r = 0.55 * 0.42
    for i, (key, name) in enumerate(kats):
        wert = kennzahl[key[0]]
        v = wert or 0
        ax.add_patch(FancyBboxPatch((0, i - 0.275), 100, 0.55, boxstyle=f"round,pad=0,rounding_size={r}",
                                    facecolor="#EEF3F9", edgecolor="none", zorder=1))
        if v > 0:
            ax.add_patch(FancyBboxPatch((0, i - 0.275), v, 0.55, boxstyle=f"round,pad=0,rounding_size={r}",
                                        facecolor=STATUS_FARBE[scoring.status(wert)[0]], edgecolor="none",
                                        zorder=3))
        ax.text(min(v + 2, 102), i, f"{v:.0f}" if wert is not None else "keine Daten", va="center",
                fontsize=9, fontweight="bold" if wert is not None else "normal",
                color="#2C2C2A" if wert is not None else TEXT2)
    ax.set_xlim(0, 118)
    ax.set_ylim(3.6, -0.6)
    ax.set_yticks(range(4))
    ax.set_yticklabels([n for _, n in kats], fontsize=9)
    ax.set_xticks([])
    ax.set_title("Kategorien (Durchschnitt)", fontsize=10, fontweight="bold", loc="left", pad=8)
    return fig
