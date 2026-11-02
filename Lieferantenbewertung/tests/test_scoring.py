import pytest

from lieferantenbewertung import scoring


def eintrag(**teile):
    basis = {"produkt": "DOA S", "qualitaet": {}, "zuverlaessigkeit": {}, "kosten": {}, "service": {}}
    basis.update(teile)
    return basis


@pytest.mark.parametrize("text, erwartet", [
    ("1,5", 1.5), ("1.5", 1.5), (" 3 ", 3.0), ("", None), ("abc", None), (None, None), (2, 2.0),
])
def test_parse_zahl(text, erwartet):
    assert scoring.parse_zahl(text) == erwartet


def test_netto_tage_ohne_wochenende():
    # Mo 01.06.2026 -> Mo 08.06.2026 = 7 Kalendertage, davon 2 Wochenendtage
    assert scoring.netto_tage("01.06.2026", "08.06.2026") == 5
    assert scoring.netto_tage("01.06.2026", "08.06.2026", puffer=2) == 3


def test_netto_tage_ungueltig():
    assert scoring.netto_tage("27.06.2026", "09.06.2026") is None  # Ende vor Start
    assert scoring.netto_tage("", "09.06.2026") is None
    assert scoring.netto_tage("32.01.2026", "09.06.2026") is None


def test_qualitaet():
    q = {"verworfen": 4, "gemessen": 39, "produkt": 40}
    # Fehlerquote 90, Analytauswahl 97.5 -> 0.7*90 + 0.3*97.5
    assert scoring.qualitaet_score(q) == pytest.approx(92.25)


def test_qualitaet_mit_none_werten_stuerzt_nicht_ab():
    # Alte Version: TypeError, wenn "verworfen" als null gespeichert war
    assert scoring.qualitaet_score({"verworfen": None, "gemessen": None, "produkt": 4}) == 100.0
    assert scoring.qualitaet_score({"produkt": None}) is None


def test_service_behebungsrate_richtig_herum():
    # 4 Fehler berichtet, 1 behoben -> 25 %. (Alte Version rechnete berichtet/behoben = 400 % -> 100.)
    assert scoring.service_score({"berichtet": 4, "behoben": 1}) == 25.0
    assert scoring.service_score({"berichtet": 1, "behoben": 0}) == 0.0
    assert scoring.service_score({"berichtet": 0, "behoben": 0}) is None


def test_service_reaktionszeit_und_nachfragen():
    s = {"anfrage": "01.06.2026", "antwort": "02.06.2026", "nachfragen": 2}
    assert scoring.service_score(s) == 80.0


def test_kosten():
    assert scoring.kosten_score({"laborpreis": 200}, benchmark=100) == 50.0
    assert scoring.kosten_score({"laborpreis": 50}, benchmark=100) == 100.0
    assert scoring.kosten_score({"laborpreis": 0, "kostenlos": True}, benchmark=100) == 100.0
    assert scoring.kosten_score({"laborpreis": 0}, benchmark=100) is None


def test_gesamt_normiert_auf_vorhandene_kategorien():
    sc = scoring.Scores(qualitaet=100, zuverlaessigkeit=None, kosten=None, service=40)
    # (50*100 + 30*40) / 80
    assert sc.gesamt == pytest.approx(77.5)
    assert scoring.Scores(None, None, None, None).gesamt is None


def test_benchmark_tabelle():
    daten = {
        "A": [eintrag(kosten={"laborpreis": 100})],
        "B": [eintrag(kosten={"laborpreis": 200}), eintrag(kosten={"laborpreis": 0})],
    }
    assert scoring.benchmark_tabelle(daten) == {"DOA S": 150.0}


def test_gewichteter_schnitt_bevorzugt_neuere():
    assert scoring.gewichteter_schnitt([0, 100]) == pytest.approx(100 * 2 / 3)
    assert scoring.gewichteter_schnitt([None, None]) is None


def test_status():
    assert scoring.status(80)[1] == "Freigegeben"
    assert scoring.status(60)[1] == "Beobachtung"
    assert scoring.status(10)[1] == "Gesperrt"
    assert scoring.status(None)[1] == "Keine Daten"


def test_plausibilitaet():
    e = eintrag(qualitaet={"verworfen": 5, "gemessen": 50, "produkt": 40},
                zuverlaessigkeit={"versand": "27.06.2026", "eingang": "09.06.2026"},
                service={"berichtet": 1, "behoben": 2})
    hinweise = " ".join(scoring.plausibilitaet(e))
    assert "gemessene" in hinweise
    assert "Eingangsdatum" in hinweise
    assert "behobene" in hinweise
    assert scoring.plausibilitaet(eintrag(qualitaet={"verworfen": 0, "gemessen": 4, "produkt": 4})) == []


def test_hauptgrund_zuverlaessigkeit():
    e = eintrag(qualitaet={"verworfen": 0, "gemessen": 40, "produkt": 40},
                zuverlaessigkeit={"versand": "01.06.2026", "eingang": "31.07.2026"})
    g = scoring.hauptgrund([e], {})
    assert g["kategorie"] == "zuverlaessigkeit"
    assert "nach 44 Werktagen" in g["text"]
    assert g["verlust"] > 20


def test_hauptgrund_nimmt_groessten_punktverlust_nicht_niedrigsten_wert():
    # Zuverlässigkeit 70 (Gewicht 20) vs. Qualität 50 % verworfen (Gewicht 50):
    # Qualität kostet mehr Punkte, obwohl ihr Score höher ist.
    e = eintrag(qualitaet={"verworfen": 2, "gemessen": 4, "produkt": 4},
                zuverlaessigkeit={"versand": "01.06.2026", "eingang": "24.06.2026"})
    g = scoring.hauptgrund([e], {})
    assert g["kategorie"] == "qualitaet"
    assert "50 % der Analyten wurden verworfen" in g["text"]


def test_hauptgrund_ohne_abzug():
    e = eintrag(qualitaet={"verworfen": 0, "gemessen": 4, "produkt": 4})
    assert scoring.hauptgrund([e], {}) is None
    assert scoring.hauptgrund([], {}) is None
