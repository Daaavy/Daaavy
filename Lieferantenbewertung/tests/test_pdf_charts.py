import os

import pytest

from lieferantenbewertung import charts, pdf_export, scoring

BEISPIEL = {
    "DE1": [
        {"monat": "2026-08", "produkt": "DOA S", "konzentration": "L1", "pruefnummer": "1",
         "qualitaet": {"verworfen": 4, "gemessen": 39, "produkt": 40},
         "zuverlaessigkeit": {"versand": "13.07.2026", "eingang": "23.07.2026"},
         "kosten": {"laborpreis": 180}, "service": {"berichtet": None},
         "kommentar": "Sonderzeichen <&> müssen escaped werden"},
    ],
    "DE2": [
        {"monat": "2026-06", "produkt": "DOA S", "konzentration": "L1", "pruefnummer": "2",
         "qualitaet": {"verworfen": 0, "gemessen": 8, "produkt": 40},
         "zuverlaessigkeit": {}, "kosten": {"laborpreis": 90}, "service": {}, "kommentar": ""},
    ],
}


@pytest.mark.parametrize("funktion", [pdf_export.erstelle_uebersicht, pdf_export.erstelle_detail])
def test_pdf_wird_erstellt(tmp_path, funktion):
    pytest.importorskip("reportlab")
    pfad = str(tmp_path / "bericht.pdf")
    funktion(pfad, BEISPIEL, "2026", "Alle")
    assert os.path.getsize(pfad) > 1000


def test_pdf_ohne_daten(tmp_path):
    pytest.importorskip("reportlab")
    pfad = str(tmp_path / "leer.pdf")
    pdf_export.erstelle_uebersicht(pfad, BEISPIEL, "1999", "Alle")
    assert os.path.exists(pfad)


def test_diagramme():
    pytest.importorskip("matplotlib")
    benchmarks = scoring.benchmark_tabelle(BEISPIEL)
    kennzahlen = charts.labor_kennzahlen(BEISPIEL, benchmarks)
    assert set(kennzahlen) == {"DE1", "DE2"}
    assert charts.score_diagramm(kennzahlen) is not None
    assert charts.preis_diagramm(BEISPIEL) is not None
    verlauf = {("DE1", "DOA S"): [{"preis": 90.0, "monat": "2026-06"}, {"preis": 100.0, "monat": "2026-08"}]}
    assert charts.preisentwicklung_diagramm(verlauf) is not None
