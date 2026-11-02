# Lieferantenbewertung 2.0

Bewertet Labore monatlich nach **Qualität, Zuverlässigkeit, Kosten und Service**.
Das Programm ist eine Überarbeitung der alten `Lieferantenbewertung.py`. Die
Bedienung ist gleich geblieben, die bestehende `labordaten.json` und
`preise.json` werden ohne Umwandlung weiterverwendet.

## Starten

```bash
pip install -r requirements.txt
```

```bash
python start.py
```

`labordaten.json` und `preise.json` liegen wie bisher im Programmordner (oder
in dem Ordner, der in `config.ini` eingetragen ist).

### Update auf eine neue Version

Die ZIP enthält nur das Programm, keine Daten. Neue Version **über den
bestehenden Ordner entpacken** und Dateien ersetzen lassen. `labordaten.json`,
`preise.json` und `config.ini` bleiben dabei erhalten.

### Access-Datenbank

Die Anbindung ist optional. Dazu `config.example.ini` als `config.ini`
kopieren und den Pfad eintragen:

```ini
[pfade]
access_db = X:\Pfad\zur\Datenbank.accdb
```

Fehlende Tabellen und Spalten legt das Programm beim Start selbst an. Ob die
Verbindung steht, zeigt die Statusleiste unten rechts. Bestehende Daten
überträgt einmalig:

```bash
python migration_json_to_access.py
```

### Als .exe bauen (optional)

```bash
pyinstaller --noconsole --onefile --name Lieferantenbewertung start.py
```

## Bedienung

Links ist die Navigation, sie hat zwei Bereiche:

**Übersicht** – zentrale Seiten, die alle Labore betreffen:

| Seite | Inhalt |
|---|---|
| Start | Kennzahlen, Ampel aller Labore, Handlungsbedarf (Labore unter 75 mit schwächster Kategorie) und Datenhinweise (unstimmige Eingaben, Klick öffnet den Eintrag) |
| Vergleich | Rangliste aller Labore und Vergleichsdiagramme, filterbar nach Jahr und Produkt |
| Alle Bewertungen | Alle Einträge mit Filtern nach Labor, Produkt, Jahr und Status |
| Preise | Preisentwicklung aller Labore, Preise manuell pflegen |
| Berichte | PDF-Export und Speicherort der Daten |

**Labore** – ein Klick öffnet die Laborseite. Dort gibt es nur, was dieses
eine Labor betrifft:

| Reiter | Inhalt |
|---|---|
| Überblick | Kategorien, Verlauf je Monat, Auswertung nach Produkt, Datenhinweise |
| Bewertung erfassen | Eingabemaske (auch mehrere Level auf einmal) |
| Einträge | Alle Bewertungen des Labors: bearbeiten, verschieben, löschen |
| Preise | Preisentwicklung dieses Labors |
| Stammdaten | Name, Adresse, Ansprechpartner (mit Access), Labor löschen |

## Was ist neu gegenüber der alten Version?

### Behobene Fehler

| Problem in der alten Version | Jetzt |
|---|---|
| Nach jedem Speichern wurden pro Labor **alle Einträge außer den letzten 12 gelöscht** (bei 3 Leveln pro Monat also nach 4 Monaten). | Es wird nichts mehr abgeschnitten. |
| „Eintrag löschen“ im Verlauf löschte **alle Einträge des Monats** (z. B. L1, L2 und L3 gemeinsam). | Jeder Eintrag hat eine eindeutige ID, gelöscht wird genau der ausgewählte. |
| „Bearbeiten“ öffnete bei mehreren Einträgen im selben Monat oft den falschen. | Auswahl über die ID. |
| Servicescore: Die Behebungsrate wurde als *berichtet ÷ behoben* berechnet statt *behoben ÷ berichtet* (wie im PDF beschrieben). Ein berichteter, aber nicht behobener Fehler zählte gar nicht. | Wird jetzt korrekt berechnet. **Dadurch können sich einzelne Service-Scores ändern** (z. B. DE88). |
| Leere Felder wurden als `0` gespeichert, z. B. „0 gemessene Analyten“, und drückten so den Qualitätsscore. | Leere Felder bleiben leer und werden nicht mitgerechnet. |
| Absturz bei Einträgen mit leeren Werten (`null`) aus der Level-Eingabe. | Wird abgefangen. |
| „Labor löschen“-Knopf in der Seitenleiste hat nichts gelöscht. | Funktioniert. |
| Access: Mehrere Level desselben Produkts im selben Monat überschrieben sich gegenseitig in `tbl_Bewertung`. | Neue Spalten `EintragID`, `Konzentration`, `Pruefnummer`, `K_Kostenlos`. |
| Access: Nur `tbl_Bewertung` wurde angelegt. Fehlte `tbl_Aenderungslog`, schlug jedes Speichern in Access fehl, und das ohne Meldung. | Alle Tabellen werden angelegt, Fehler werden angezeigt. |
| Ein Komma als Dezimalzeichen („12,5“) führte zum Absturz bzw. wurde zu 0. | Komma und Punkt werden beide akzeptiert. |
| Diagramm „Verlauf“: Die Monatsachse stimmte nur für das erste Labor. | Gemeinsame Monatsachse für alle Labore. |
| PDF: Kommentare mit `&` oder `<` brachen den Export ab, und die Formelseite nannte eine falsche Gesamtformel. | Behoben. |
| JSON wurde direkt überschrieben: Ein Absturz während des Speicherns konnte die Datei zerstören. | Atomares Speichern und automatische Sicherung `labordaten.json.bak`. |

### Neu

- **Live-Vorschau** des Scores während der Eingabe.
- **Plausibilitätsprüfung** vor dem Speichern, z. B. Eingang vor Versand,
  mehr gemessene als vorhandene Analyten oder ungültiges Datum.
- Hinweis, ob gerade ein bestehender Eintrag bearbeitet oder ein neuer angelegt wird.
- „Verschieben zu anderem Labor“ als eigener Knopf im Verlauf.
- Kategorien-Diagramm als Farbtabelle, die auch bei vielen Laboren lesbar bleibt.
- Preise können im Reiter *Preisentwicklung* manuell gepflegt werden.
- Änderungsprotokoll pro Labor (Rechtsklick, nur mit Access).
- Pfade und Firmenname stehen in `config.ini` statt im Code.

### Aufbau

```
start.py                       Programmstart
migration_json_to_access.py    JSON -> Access übertragen
lieferantenbewertung/
  config.py      Einstellungen, Gewichte, Grenzwerte
  scoring.py     Score-Berechnung (ohne Oberfläche, getestet)
  storage.py     JSON-Dateien laden/speichern
  labor_db.py    Access-Anbindung
  charts.py      Diagramme
  pdf_export.py  PDF-Berichte
  gui/
    app.py       Hauptfenster mit Navigation
    seiten/      zentral.py (Start, Vergleich, …), labor.py (Laborseite), eingabe.py
    rund.py      runde Buttons, Karten, Eingabefelder
    dialoge.py   Dialogfenster
tests/           automatische Tests:  python -m pytest
```

## Berechnung

| Kategorie | Gewicht | Berechnung |
|---|---|---|
| Qualität | 50 | 70 % Fehlerquote (100 − verworfen/gesamt·100) + 30 % Analytauswahl (gemessen/gesamt·100) |
| Zuverlässigkeit | 20 | Werktage Versand → Eingang minus 2 Tage Puffer: ≤14 → 100, ≤21 → 70, ≤28 → 30, sonst 0 |
| Kosten | 20 | min(100, Ø-Preis aller Labore ÷ eigener Preis · 100), kostenlos = 100 |
| Service | 30 | Ø aus Behebungsrate (behoben/berichtet) und Reaktionszeit (≤3 Tage 100, ≤7 Tage 70, danach −10/Tag, −10 je Nachfrage) |

Der Gesamtscore ist der gewichtete Durchschnitt der vorhandenen Kategorien.
Die Gewichte ergeben zusammen 120 und werden normiert, effektiv also
42 / 17 / 17 / 25 %. Gewichte und Grenzwerte lassen sich in
`lieferantenbewertung/config.py` ändern.

Status: ab 75 **Freigegeben**, ab 50 **Beobachtung**, darunter **Gesperrt**.
