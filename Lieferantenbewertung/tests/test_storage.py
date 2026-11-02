import json
import os

from lieferantenbewertung.storage import Datenspeicher, Preisspeicher, labor_sortierschluessel


def alte_datei(tmp_path, daten):
    pfad = tmp_path / "labordaten.json"
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    return str(pfad)


def level(monat, konz, pruef):
    return {"monat": monat, "produkt": "DOA S", "konzentration": konz, "pruefnummer": pruef,
            "qualitaet": {"verworfen": 1, "gemessen": 10, "produkt": 10}}


def test_alte_daten_bekommen_ids_und_bleiben_erhalten(tmp_path):
    pfad = alte_datei(tmp_path, {"DE1": [level("2026-08", "L1", "1"), level("2026-08", "L2", "2")]})
    store = Datenspeicher(pfad)
    ids = [e["id"] for _, e in store.eintraege()]
    assert len(ids) == 2 and len(set(ids)) == 2
    # IDs wurden in die Datei zurückgeschrieben, alte Version als .bak gesichert
    assert all("id" in e for e in json.loads(open(pfad, encoding="utf-8").read())["DE1"])
    assert os.path.exists(pfad + ".bak")


def test_loeschen_trifft_nur_einen_eintrag_im_selben_monat(tmp_path):
    # Alte Version löschte ALLE Einträge des Monats.
    store = Datenspeicher(alte_datei(tmp_path, {"DE1": [level("2026-08", f"L{i}", str(i)) for i in range(3)]}))
    _, ziel = store.eintraege("DE1")[1]
    store.eintrag_loeschen(ziel["id"])
    assert [e["konzentration"] for _, e in store.eintraege("DE1")] == ["L0", "L2"]


def test_keine_begrenzung_auf_12_eintraege(tmp_path):
    # Alte Version schnitt nach dem Speichern alles außer den letzten 12 Einträgen ab.
    store = Datenspeicher(alte_datei(tmp_path, {"DE1": []}))
    for i in range(20):
        store.eintrag_speichern("DE1", level(f"2025-{(i % 12) + 1:02d}", "L1", str(i)))
    assert len(Datenspeicher(store.pfad).eintraege("DE1")) == 20


def test_bearbeiten_ersetzt_ueber_id(tmp_path):
    store = Datenspeicher(alte_datei(tmp_path, {"DE1": [level("2026-08", "L1", "1")]}))
    _, e = store.eintraege("DE1")[0]
    geaendert = dict(e, kommentar="neu")
    store.eintrag_speichern("DE1", geaendert)
    assert len(store.eintraege("DE1")) == 1
    assert store.eintraege("DE1")[0][1]["kommentar"] == "neu"


def test_duplikat_und_verschieben(tmp_path):
    store = Datenspeicher(alte_datei(tmp_path, {"DE1": [level("2026-08", "L1", "3943")], "DE2": []}))
    neu = level("2026-09", "L1", "3943")
    assert store.duplikat("DE1", neu) is not None
    assert store.duplikat("DE2", neu) is None
    eid = store.eintraege("DE1")[0][1]["id"]
    store.eintrag_verschieben(eid, "DE2")
    assert store.finden(eid)[0] == "DE2"


def test_labor_sortierung():
    assert sorted(["DE106", "FR109", "DE9", "DE29", "CH78"], key=labor_sortierschluessel) == \
        ["CH78", "DE9", "DE29", "DE106", "FR109"]


def test_preise(tmp_path):
    p = Preisspeicher(str(tmp_path / "preise.json"))
    assert p.aktualisieren("DE1", "DOA S", 90.0, "2026-08")
    assert not p.aktualisieren("DE1", "DOA S", 90.0, "2026-09")  # unverändert
    assert p.aktualisieren("DE1", "DOA S", 100.0, "2026-09")
    assert p.letzter_preis("DE1", "DOA S") == 100.0
    p.loeschen("DE1", "DOA S")
    assert p.letzter_preis("DE1", "DOA S") is None
