# VERSION: 2026-10-06-UX
#!/usr/bin/env python3
"""
Analyte Comparison Tool  –  medichem diagnostica
pip install pdfplumber reportlab
python analyte_comparison.py
"""

import os, sys, re, threading, itertools, datetime, queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

try:
    import pdfplumber
except ImportError:
    sys.exit("Bitte installieren: pip install pdfplumber reportlab")

# ─────────────────────────────────────────────────────────────
# Feste Analytliste (Reihenfolge = r000..r039 im neuen Format)
# ─────────────────────────────────────────────────────────────
ANALYTE_LIST = [
    "Amphetamine", "MBDB", "MDA", "MDE (MDEA)", "MDMA", "Methamphetamine",
    "Methylphenidate", "Ritalinic acid",
    "11-OH-THC", "CBD", "THC", "THC-COOH",
    "Mephedrone", "Methedrone", "Methylone",
    "Benzoylecgonine", "Cocaine", "Cocaethylene", "Ecgonine methyl ester",
    "6-MAM", "Codeine", "Dihydrocodeine", "Ethylmorphine", "Fentanyl",
    "Hydrocodone", "Hydromorphone", "Ketamine", "Morphine", "Norfentanyl",
    "Norketamine", "Nortilidine", "O-Desmethyltramadol", "Oxycodone",
    "Oxymorphone", "Pholcodine", "Tilidine", "Tramadol",
    "Benzylpiperazine (BZP)", "GHB", "LSD",
]
ANALYTE_INDEX = {a.lower(): i for i, a in enumerate(ANALYTE_LIST)}

GROUPS = {
    "Amines / Amphetamines": ANALYTE_LIST[0:8],
    "Cannabinoids":          ANALYTE_LIST[8:12],
    "Cathinones":            ANALYTE_LIST[12:15],
    "Cocaine":               ANALYTE_LIST[15:19],
    "Opioids":               ANALYTE_LIST[19:37],
    "Piperazines":           ANALYTE_LIST[37:38],
    "GHB":                   ANALYTE_LIST[38:39],
    "Hallucinogens":         ANALYTE_LIST[39:40],
    "Phosphatidylethanol":   [],  # PEth — dynamisch befüllt über Namen-Match
}

# Globale Registry: wird beim Parsen von PDFs befüllt
# analyte_name_lower -> group_name
_analyte_group_registry: dict = {}

def get_group(name):
    # 1. Aus der PDF-Registry (hat Vorrang für unbekannte Analyten)
    reg = _analyte_group_registry.get(name.lower())
    if reg:
        return reg
    # 2. Aus der festen GROUPS-Liste
    for g, lst in GROUPS.items():
        if any(a.lower() == name.lower() for a in lst):
            return g
    # 3. PEth-Fallback per Präfix
    nl = name.lower()
    if nl.startswith('peth') or 'phosphatidylethanol' in nl:
        return 'Phosphatidylethanol'
    return "Sonstige"

GROUP_ORDER = list(GROUPS.keys()) + ["Sonstige"]

def sort_key(name):
    low = name.lower()
    idx = ANALYTE_INDEX.get(low, 999)
    g   = get_group(name)
    return (GROUP_ORDER.index(g), idx, low)

# ─────────────────────────────────────────────────────────────
# PDF Parsing
# ─────────────────────────────────────────────────────────────
_NUM  = re.compile(r'^\d[\d\.,]*$')
_UNIT = {"µg/L", "mg/L", "ng/L", "ng/mL", "µg/mL", "mg/mL", "pg/mL", "ng/dL",
         "g/L", "g/dL", "mmol/L", "nmol/L", "pmol/L", "µmol/L",
         "pg/mg", "ng/mg", "µg/mg", "mg/mg",
         "µg/l", "mg/l", "ng/l", "ng/ml", "µg/ml", "mg/ml", "pg/ml", "ng/dl",
         "pg/mg".lower(), "ng/mg".lower()}
_CODE = re.compile(r'\b([A-Z]{2}\d{2,4})\b')
_RUN  = re.compile(r'^[A-Z]$')

def _parse_cost(raw):
    raw = raw.strip().replace('\xa0', '').replace(' ', '')
    if not raw:
        return None
    if ',' in raw and '.' in raw:
        raw = raw.replace('.','').replace(',','.') if raw.rfind(',') > raw.rfind('.') else raw.replace(',','')
    elif ',' in raw:
        raw = raw.replace(',','.')
    try:
        return float(raw)
    except:
        return None

def _annot_fields(path):
    """Alle ausgefüllten Formularfelder aus PDF lesen."""
    fields = {}
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for a in (page.annots or []):
                    t = a.get('title') or ''
                    v = a.get('data', {}).get('V') or b''
                    if isinstance(v, bytes):
                        v = v.decode('latin-1', 'ignore').strip().replace('\xa0','')
                    elif not isinstance(v, str):
                        v = str(v)
                    else:
                        v = v.strip().replace('\xa0','')
                    if t:
                        fields[t] = v
    except:
        pass
    return fields

def _fulltext(path):
    text = ''
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or '') + '\n'
    except:
        pass
    return text

def parse_pdf(path):
    """Returns {lab, analytes, cost, runs, filename}"""
    filename = os.path.basename(path)
    fields   = _annot_fields(path)
    text     = _fulltext(path)
    lines    = text.splitlines()

    # Lab-Code
    lab = fields.get('f_lab_code', '').strip()
    if not lab:
        for i, line in enumerate(lines):
            if 'internal lab code' in line.lower() or 'lab code' in line.lower():
                for j in range(i, min(i+6, len(lines))):
                    m = _CODE.search(lines[j])
                    if m: lab = m.group(1); break
            if lab: break
    if not lab:
        for line in lines:
            m = _CODE.search(line)
            if m: lab = m.group(1); break
    if not lab:
        # Lab-Code aus Dateinamen extrahieren (z.B. DE61 aus DOA_H_DE61_1_4.pdf)
        m = re.search(r'([A-Z]{2,4}\d{2,4})', filename)
        if m:
            lab = m.group(1)
        else:
            lab = os.path.splitext(filename)[0][:15]

    # Kosten (Gesamtkosten net bevorzugt)
    cost = _parse_cost(fields.get('f_total_net', ''))
    if cost is None: cost = _parse_cost(fields.get('f_total_gross', ''))
    if cost is None:
        for line in lines:
            if 'total analysis cost' in line.lower() and 'gross' not in line.lower():
                m = re.search(r'(\d[\d\.,]+)\s*€', line)
                if not m: m = re.search(r':\s*(\d[\d\.,]+)\s*$', line)
                if m: cost = _parse_cost(m.group(1)); break
    if cost is None:
        for line in lines:
            if 'total analysis cost' in line.lower():
                m = re.search(r'(\d[\d\.,]+)\s*€', line)
                if not m: m = re.search(r':\s*(\d[\d\.,]+)\s*$', line)
                if m: cost = _parse_cost(m.group(1)); break

    # Formularfeld-Format (DE33-style)
    val_keys = {k: v for k, v in fields.items() if re.match(r'^val_r\d+$', k)}
    run_costs   = {}
    analyte_run = {}
    analyte_group = {}  # analyte name -> group name from PDF
    all_analytes_raw = []  # alle Analyten inkl. nicht-validierter
    analyte_lod = {}  # analyte name -> LOD-Wert (float) aus der PDF, falls vorhanden

    if val_keys:
        # Run-Kosten aus cost_0, cost_1, ...
        i = 0
        while True:
            r = fields.get(f'run_{i}', '').strip()
            c = _parse_cost(fields.get(f'cost_{i}', ''))
            if not r: break
            if c is not None: run_costs[r] = c
            i += 1
        # Analyt->Run aus run_rNNN
        for key in fields:
            m = re.match(r'^run_r(\d+)$', key)
            if m:
                idx = int(m.group(1))
                rl  = fields[key].strip()
                if 0 <= idx < len(ANALYTE_LIST) and rl:
                    analyte_run[ANALYTE_LIST[idx]] = rl
        # Validierte Analyten
        validated = []
        for key, val in val_keys.items():
            if 'Yes' in val or 'yes' in val.lower():
                m = re.search(r'\d+', key)
                if m:
                    idx = int(m.group())
                    if 0 <= idx < len(ANALYTE_LIST):
                        validated.append(ANALYTE_LIST[idx])
    else:
        # Koordinatenbasiertes Parsing — erkennt Analyten anhand der Spaltenposition
        # Run-Buchstaben stehen immer in der "Run"-Spalte (x ~390-420)
        _IS_RUN = re.compile(r'^[A-Z?]$')

        # Run-Kosten aus Kostentabelle
        in_cost = False
        for line in lines:
            s = line.strip()
            if 'MEASUREMENT METHOD' in s or 'Run Method Cost' in s: in_cost = True; continue
            if not in_cost: continue
            if 'Total' in s or 'COMMENTS' in s: break
            m = re.match(r'^([A-Z])\s+\S.*?(\d[\d\.,]+)\s*€', s)
            if m:
                c = _parse_cost(m.group(2))
                if c is not None: run_costs[m.group(1)] = c

        validated = []

        # Altes Format mit "4"-Präfix noch unterstützen
        table_lines = []
        in_t = False
        for line in lines:
            s = line.strip()
            if 'Analyte' in s and 'Validated' in s: in_t = True; continue
            if not in_t: continue
            if 'MEASUREMENT METHOD' in s: in_t = False; continue
            table_lines.append(s)
        has_4 = any(l.startswith('4 ') for l in table_lines)

        if has_4:
            for line in table_lines:
                if not line.startswith('4 '): continue
                rest = line[2:].strip()
                while rest.startswith('4 ') or rest.startswith('4\t'):
                    rest = rest[2:].strip()
                parts = rest.split()
                name_parts = []
                for p in parts:
                    if p in _UNIT or p in ('Information','ULOQ','Only'): break
                    if _NUM.match(p): break
                    if _IS_RUN.match(p): break
                    name_parts.append(p)
                name = re.split(r'\s*[<>]\s*\d',' '.join(name_parts))[0].strip()
                name = _normalize_name(name)
                rl = None
                for p in reversed(parts):
                    if _IS_RUN.match(p): rl=p; break
                if name and len(name)>=2:
                    validated.append(name)
                    if rl: analyte_run[name]=rl
        else:
            # Koordinatenbasiert: per Seite, Run-Spalte aus Header bestimmen
            try:
                with pdfplumber.open(path) as _pdf:
                    for _page in _pdf.pages:
                        _words = _page.extract_words()
                        _text  = _page.extract_text() or ''

                        # Header-Zeile finden
                        _hrow = None
                        _run_x = 399  # Fallback
                        _lod_x = None
                        _lloq_x = None
                        for _w in _words:
                            if _w['text'] == 'Analyte' and _w['x0'] < 150:
                                _hrow = _w['top']
                            if _w['text'] == 'Run' and _hrow and abs(_w['top']-_hrow) < 10:
                                _run_x = _w['x0']
                            if _w['text'] == 'LOD' and _hrow and abs(_w['top']-_hrow) < 10:
                                _lod_x = _w['x0']
                            if _w['text'] == 'LLOQ' and _hrow and abs(_w['top']-_hrow) < 10:
                                _lloq_x = _w['x0']
                        if _hrow is None:
                            continue

                        # Tabellenende
                        _tend = 9999
                        for _w in _words:
                            if _w['top'] > _hrow+10 and _w['text'] in ('MEASUREMENT','Total') and _w['x0'] < 200:
                                _tend = _w['top']; break

                        # Zeilen gruppieren — Clustering nach Abstand statt starrem
                        # Rundungsraster, damit Wörter, die z.B. bei top=772.4 und
                        # top=772.7 liegen, nicht durch eine Rundungsgrenze
                        # (round(x/5)*5) in unterschiedliche Zeilen gerissen werden.
                        _in_table = sorted(
                            [_w for _w in _words if _hrow < _w['top'] < _tend],
                            key=lambda w: w['top'])
                        _row_list = []  # Liste von [ref_top, [wörter]]
                        for _w in _in_table:
                            if _row_list and abs(_w['top'] - _row_list[-1][0]) < 4:
                                _row_list[-1][1].append(_w)
                            else:
                                _row_list.append([_w['top'], [_w]])
                        _rows = {i: ws for i, (_, ws) in enumerate(_row_list)}

                        _current_group = ''
                        _CHECK_CHARS = {'✓', '✔', '☑'}
                        # Das Häkchen vor dem Analytnamen ist KEIN Textzeichen, sondern
                        # eine gezeichnete Vektor-Kurve über dem Checkbox-Rahmen.
                        # Unchecked = 1 Kurvenobjekt (nur Rahmen), Checked = 2 (Rahmen + Haken).
                        _page_curves = _page.curves
                        _CHECK_X0, _CHECK_X1 = 38, 58

                        def _row_is_checked(_rw_):
                            _tops = [_w['top'] for _w in _rw_]
                            if not _tops: return False
                            _tmin, _tmax = min(_tops), max(_tops)
                            _n = sum(1 for _c in _page_curves
                                     if _CHECK_X0 <= _c['x0'] <= _CHECK_X1
                                     and (_tmin - 6) <= _c['top'] <= (_tmax + 6))
                            return _n >= 2

                        for _top, _rw in sorted(_rows.items()):
                            _rw = sorted(_rw, key=lambda w: w['x0'])

                            # Häkchen vor dem Analytnamen — das ist das einzig maßgebliche
                            # Signal: Analyt angehakt = zählt, unabhängig von Run/LOD.
                            _lead_check = _row_is_checked(_rw)

                            # Run-Buchstabe optional weiterhin erfassen (nur für die
                            # Run/Kosten-Zuordnung, NICHT für die Validiert-Entscheidung)
                            _run_words = [_w for _w in _rw
                                         if _IS_RUN.match(_w['text'])
                                         and abs(_w['x0'] - _run_x) < 50]

                            # Gruppenheader erkennen: kein Häkchen, keine Run-Spalte,
                            # Wörter links beginnen bei x≈57 (nicht 60)
                            if not _lead_check and not _run_words:
                                _first = [_w for _w in _rw if _w['x0'] < 58]
                                if _first:
                                    _all_left = [_w for _w in _rw
                                                 if _w['x0'] < _run_x - 100
                                                 and _w['text'] not in _UNIT
                                                 and _w['text'] not in _CHECK_CHARS
                                                 and not re.match(r'^[\d,\.]+$', _w['text'])]
                                    _gh = ' '.join(_w['text'] for _w in
                                                   sorted(_all_left, key=lambda w: w['x0']))
                                    _gh = _gh.strip()
                                    if _gh and len(_gh) >= 3 and not _gh[0].isdigit():
                                        _gh_clean = re.sub(r'\s*\(cont\.?\)\s*$', '', _gh, flags=re.I).strip()
                                        _current_group = _gh_clean if _gh_clean else _current_group
                                continue

                            if not _lead_check:
                                # Nicht angehakt — zählt nicht, egal ob Run/LOD vorhanden
                                continue

                            _rl = _run_words[0]['text'] if _run_words else '-'

                            # Name: Wörter links (x < run_x - 150), Häkchen-Zeichen ausschließen
                            _name_limit = _run_x - 150
                            _np = []
                            for _w in _rw:
                                if _w['x0'] >= _name_limit: break
                                _t = _w['text']
                                if _t in _CHECK_CHARS: continue
                                if _t in _UNIT: continue
                                if _NUM.match(_t): continue
                                if re.match(r'^[<>]\d', _t): continue
                                if _IS_RUN.match(_t): continue
                                _t = re.split(r'[<>]\d', _t)[0].strip()
                                if _t: _np.append(_t)

                            _name = re.split(r'\s*[<>]\s*\d',' '.join(_np))[0].strip()
                            _name = _strip_unit(_name)
                            _name = _normalize_name(_name)
                            if _name and len(_name) >= 2 and not _NUM.match(_name):
                                if _name not in validated:
                                    validated.append(_name)
                                all_analytes_raw.append(_name)
                                analyte_run[_name] = _rl
                                if _current_group:
                                    analyte_group[_name] = _current_group
                                # LOD-Wert aus der LOD-Spalte lesen (falls Header gefunden).
                                # Fenstergrenzen als Mittelpunkt zwischen LOD- und LLOQ-Kopfzeile,
                                # NICHT als fester Versatz — Werte stehen in manchen PDF-Vorlagen
                                # deutlich links von ihrer eigenen Kopfzeile, ein fester Versatz
                                # lässt dann LLOQ-Werte fälschlich ins LOD-Fenster rutschen.
                                if _lod_x is not None:
                                    if _lloq_x is not None:
                                        _half_gap = max(6, (_lloq_x - _lod_x) / 2)
                                        _lod_lo = _lod_x - _half_gap
                                        _lod_hi = _lod_x + _half_gap
                                    else:
                                        _lod_lo = _lod_x - 15
                                        _lod_hi = _lod_x + 25
                                    for _w in _rw:
                                        if _lod_lo <= _w['x0'] < _lod_hi \
                                                and re.match(r'^\d+([.,]\d+)?$', _w['text']):
                                            _lv = _parse_cost(_w['text'])
                                            if _lv is not None:
                                                analyte_lod[_name] = _lv
                                            break
            except Exception as _e:
                pass  # Fallback auf leere Liste wenn Koordinaten-Parsing fehlschlägt

    # Bereinigung
    cleaned = []
    seen = set()
    for name in validated:
        name = re.split(r'\s*[<>]\s*\d', name)[0].strip()
        if name and len(name) >= 2 and name.lower() not in seen:
            seen.add(name.lower())
            cleaned.append(name)
    result_analytes = sorted(cleaned, key=sort_key)

    # Run-Struktur aufbauen
    runs = {}
    for analyte, rl in analyte_run.items():
        analyte = re.split(r'\s*[<>]\s*\d', analyte)[0].strip()
        if analyte and analyte in result_analytes:
            runs.setdefault(rl, {'cost': run_costs.get(rl), 'analytes': []})
            if analyte not in runs[rl]['analytes']:
                runs[rl]['analytes'].append(analyte)

    # Runs ohne Preis bekommen den Preis der anderen Runs dieses Labors
    known_costs = [rd['cost'] for rd in runs.values() if rd.get('cost') is not None]
    if known_costs:
        fallback_cost = max(set(known_costs), key=known_costs.count)  # häufigster Preis
        for rl, rd in runs.items():
            if rd.get('cost') is None:
                rd['cost'] = fallback_cost

    # Alle Analyten (inkl. nicht-validierter) bereinigen
    _SKIP = {'g/l', 'mg/l', 'µg/l', 'ng/l', 'ng/ml', 'µg/ml', 'mg/ml',
             'pg/ml', 'ng/dl', 'g/dl', 'unit', 'units', '%', 'mmol/l',
             'nmol/l', 'pmol/l', 'µmol/l', 'g/ml', 'µg/dl', 'ng/g',
             'µg/g', 'mg/dl', 'iu/l', 'mu/l',
             # Haar-Matrix
             'pg/mg', 'ng/mg', 'µg/mg', 'mg/mg',
             # Großbuchstaben
             'g/L', 'mg/L', 'µg/L', 'ng/L', 'ng/mL', 'µg/mL', 'mg/mL',
             'pg/mL', 'ng/dL', 'g/dL', 'mmol/L', 'nmol/L', 'pmol/L', 'µmol/L',
             'pg/mg', 'ng/mg', 'µg/mg'}
    all_seen = set()
    all_analytes_clean = []
    for name in all_analytes_raw:
        name = re.split(r'\s*[<>]\s*\d', name)[0].strip()
        if (name and len(name) >= 2
                and name.lower() not in all_seen
                and name.lower() not in _SKIP
                and not re.match(r'^[\d.,]+\s*(g|mg|µg|ng|pg|ml|l|dl)/?', name, re.I)):
            all_seen.add(name.lower())
            all_analytes_clean.append(name)

    # Auch validated-Liste bereinigen
    validated = [a for a in validated
                 if a.lower() not in _SKIP
                 and not re.match(r'^[\d.,]+\s*(g|mg|µg|ng|pg|ml|l|dl)/?', a, re.I)]
    all_analytes_sorted = sorted(all_analytes_clean, key=sort_key)

    # Globale Registry aktualisieren damit get_group() neue Gruppen kennt
    for _an, _gn in analyte_group.items():
        _analyte_group_registry[_an.lower()] = _gn
        if _gn not in GROUP_ORDER:
            GROUP_ORDER.append(_gn)

    return {
        'lab':          lab,
        'analytes':     result_analytes,       # nur validierte
        'all_analytes': all_analytes_sorted,   # alle inkl. nicht-validierter
        'cost':         cost,
        'runs':         runs,
        'filename':     filename,
        'contact':      _parse_contact(path, fields, lines),
        'product':      _parse_product(path, fields, lines),
        'analyte_group': analyte_group,
        'lod':          analyte_lod,   # analyte name -> LOD-Wert (float), falls in PDF vorhanden
    }


def _strip_unit(name):
    """Entfernt angehängte Einheiten vom Analytnamen."""
    # Einheit am Ende entfernen
    name = re.sub(
        r'\s+(g|mg|µg|ng|pg|mmol|nmol|µmol|pmol|mU|U|IU)'
        r'(/|\s*per\s*)(L|mL|dL|100mL|100ml|l|mg|g)\s*$',
        '', name, flags=re.I).strip()
    # Alleinstehende Einheiten entfernen
    name = re.sub(r'^(g|mg|µg|ng|pg|mmol|nmol|µmol|pmol)/(L|mL|dL|l|mg|g)$',
                  '', name, flags=re.I).strip()
    return name


# Bekannte deutsch/englische Schreibvarianten desselben Analyten —
# manche Labore tragen die deutsche Bezeichnung (ohne "e") statt der
# englischen ein. Key = kleingeschriebene Variante, Value = kanonischer Name.
_NAME_ALIASES = {
    'hydrocodon':      'Hydrocodone',
    'hydromorphon':    'Hydromorphone',
    'oxycodon':        'Oxycodone',
    'buprenorphin':    'Buprenorphine',
    'norbuprenorphin': 'Norbuprenorphine',
    'ketamin':         'Ketamine',
    'norketamin':      'Norketamine',
    'codein':          'Codeine',
    'methylphenidat':  'Methylphenidate',
    'methamphetamin':  'Methamphetamine',
    'amphetamin':      'Amphetamine',
    'nortilidin':      'Nortilidine',
    'tilidin':         'Tilidine',
    'fentanyl':        'Fentanyl',
    'morphin':         'Morphine',
    'dihydrocodein':   'Dihydrocodeine',
    'ethylmorphin':    'Ethylmorphine',
    'pholcodin':       'Pholcodine',
    'mephedron':       'Mephedrone',
    'methedron':       'Methedrone',
    'methylon':        'Methylone',
    'cocaethylen':     'Cocaethylene',
}

def _normalize_name(name):
    """Führt bekannte deutsch/englische Schreibvarianten auf einen Namen zusammen."""
    return _NAME_ALIASES.get(name.strip().lower(), name)


def _parse_contact(path, fields, lines):
    """Extrahiert Kontaktdaten: Name, E-Mail, Telefon, Laborname, Adresse."""
    contact = {
        'lab_name': fields.get('f_lab_name', '').strip(),
        'address':  fields.get('f_address',  '').strip(),
        'person':   fields.get('f_contact_person', '').strip(),
        'email':    fields.get('f_email', '').strip(),
        'phone':    fields.get('f_phone', '').strip(),
    }

    if not any(contact.values()):
        try:
            with pdfplumber.open(path) as _pdf:
                page = _pdf.pages[0]
                words = page.extract_words()

                header_y = None
                for w in words:
                    if w['text'] == 'E-Mail' and w['x0'] > 150:
                        header_y = w['top']
                        break

                if header_y is not None:
                    data_words = [w for w in words
                                  if header_y < w['top'] < header_y + 25]
                    data_words.sort(key=lambda w: w['x0'])

                    email_x = next((w['x0'] for w in words
                                    if w['text'] == 'E-Mail'), 200)

                    _email_re = re.compile(
                        r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')

                    name_parts = []
                    found_email = ''
                    for w in data_words:
                        t = w['text']
                        # Für Namen: Sonderzeichen → Leerzeichen (erhält Wortgrenzen)
                        t_name  = re.sub(r'[›‹»«\x00-\x1f\x7f-\x9f]', ' ', t).strip()
                        # Für E-Mail: Sonderzeichen entfernen
                        t_clean = re.sub(r'[›‹»«\x00-\x1f\x7f-\x9f]', '', t)
                        if not found_email and w['x0'] < email_x - 10:
                            name_clean = re.sub(r'\s+', ' ', t_name)
                            if name_clean:
                                name_parts.append(name_clean)
                        elif not found_email and '@' in t_clean:
                            # E-Mail aus Token extrahieren:
                            # Ziffern die direkt an die TLD angehängt sind entfernen
                            # z.B. "bender@ukbonn.d0e2" → "bender@ukbonn.de"
                            t_fixed = re.sub(r'(\.[a-zA-Z])[\d]+([a-zA-Z]?)(\d*)$',
                                            lambda m: m.group(1) + (m.group(2) or ''),
                                            t_clean)
                            # Trailing digits nach gültiger TLD abschneiden
                            t_fixed = re.sub(r'(\.[a-zA-Z]{2,})\d+', r'\1', t_fixed)
                            m = _email_re.search(t_fixed)
                            if m:
                                found_email = m.group(0).rstrip("'\".,")

                    if name_parts:   contact['person'] = ' '.join(name_parts)
                    if found_email:  contact['email']  = found_email

                lab_name_y = None
                for w in words:
                    if w['text'] == 'name' and w['x0'] < 150:
                        near = [x for x in words
                                if abs(x['top'] - w['top']) < 5
                                and x['text'] == 'Laboratory']
                        if near:
                            lab_name_y = w['top']
                            break

                if lab_name_y is not None:
                    ln_words = [w for w in words
                                if lab_name_y < w['top'] < lab_name_y + 45
                                and w['x0'] < 280]
                    ln_words.sort(key=lambda w: (w['top'], w['x0']))
                    if ln_words:
                        contact['lab_name'] = ' '.join(w['text'] for w in ln_words)

                    addr_words = [w for w in words
                                  if lab_name_y < w['top'] < lab_name_y + 60
                                  and w['x0'] >= 280]
                    addr_words.sort(key=lambda w: (w['top'], w['x0']))
                    if addr_words:
                        lines_addr = {}
                        for w in addr_words:
                            yk = round(w['top'] / 5) * 5
                            lines_addr.setdefault(yk, []).append(w['text'])
                        contact['address'] = ', '.join(
                            ' '.join(v) for v in lines_addr.values())

        except Exception:
            pass

    if not contact['email']:
        _email_re = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
        for line in lines:
            if '@' in line and 'medichem' not in line.lower():
                line_clean = re.sub(r'[›‹»«\x00-\x1f\x7f-\x9f]', '', line)
                m = _email_re.search(line_clean)
                if m:
                    contact['email'] = m.group(0).rstrip("'\".,")
                    break

    return contact


def _parse_product(path, fields, lines):
    """Extrahiert den Produktnamen aus der PRODUCT-Zeile des PDFs."""
    # Formularfeld zuerst
    p = fields.get('f_product', '').strip()
    if p: return p

    # Koordinatenbasiert: Wörter direkt unter dem PRODUCT-Label (x<300, y≈156)
    try:
        with pdfplumber.open(path) as _pdf:
            words = _pdf.pages[0].extract_words()
            prod_y = next((w['top'] for w in words
                           if w['text'] == 'PRODUCT' and w['x0'] < 100), None)
            if prod_y is not None:
                row = [w for w in words
                       if prod_y < w['top'] < prod_y + 25 and w['x0'] < 300]
                row.sort(key=lambda w: w['x0'])
                if row:
                    return ' '.join(w['text'] for w in row)
    except Exception:
        pass

    # Fallback: Zeile nach "PRODUCT" im Volltext
    for i, line in enumerate(lines):
        if 'PRODUCT' in line.upper() and 'CONTACT' not in line.upper():
            for j in range(i+1, min(i+4, len(lines))):
                candidate = lines[j].strip()
                # Nicht die CONTACT/DATE-Zeile erwischen
                if candidate and 'CONTACT' not in candidate.upper():
                    # Alles bis zur E-Mail-Adresse abschneiden
                    candidate = re.split(r'\s{3,}|\t', candidate)[0].strip()
                    if candidate:
                        return candidate
    return ''


def optimize(results, min_n=3, target_n=5, max_n=6, masked_runs=None, forced_runs=None):
    """Run-basierte Greedy-Optimierung."""
    all_analytes = sorted({a for r in results for a in r['analytes']}, key=sort_key)
    if not all_analytes:
        return [], 0.0, {}

    if masked_runs is None: masked_runs = set()
    if forced_runs is None: forced_runs = set()

    # ── Run-Units aufbauen ────────────────────────────────────
    run_units = []
    for r in results:
        runs = r.get('runs', {})
        if runs:
            for rl, rd in runs.items():
                key = f"{r['lab']}-{rl}"
                if key in masked_runs: continue
                r_lower = {a.lower() for a in r['analytes']}
                ra = [a for a in rd['analytes'] if a.lower() in r_lower]
                if ra:
                    run_units.append({
                        'lab': r['lab'], 'run': rl,
                        'cost': rd.get('cost') or 0,
                        'analytes': ra, '_result': r,
                        '_ls': {a.lower() for a in ra},
                        'forced': key in forced_runs,
                    })
        else:
            run_units.append({
                'lab': r['lab'], 'run': '?',
                'cost': r.get('cost') or 0,
                'analytes': r['analytes'], '_result': r,
                '_ls': {a.lower() for a in r['analytes']},
                'forced': False,
            })

    # Erzwungene Runs die noch nicht in run_units sind hinzufügen
    for r in results:
        for rl, rd in r.get('runs', {}).items():
            key = f"{r['lab']}-{rl}"
            if key not in forced_runs or key in masked_runs: continue
            if any(u['lab']==r['lab'] and u['run']==rl for u in run_units): continue
            r_lower = {a.lower() for a in r['analytes']}
            ra = [a for a in rd['analytes'] if a.lower() in r_lower]
            if ra:
                run_units.append({
                    'lab': r['lab'], 'run': rl,
                    'cost': rd.get('cost') or 0,
                    'analytes': ra, '_result': r,
                    '_ls': {a.lower() for a in ra},
                    'forced': True,
                })

    if not run_units:
        return [], 0.0, {}

    # ── Hilfsfunktionen ───────────────────────────────────────
    al_lower = {a: a.lower() for a in all_analytes}

    def calc_cov(sel):
        cov = {a: 0 for a in all_analytes}
        for u in sel:
            ls = u['_ls']
            for a in all_analytes:
                if al_lower[a] in ls: cov[a] += 1
        return cov

    def run_value(u, cov):
        val = 0.0
        for a in all_analytes:
            if al_lower[a] in u['_ls']:
                c = cov.get(a, 0)
                if c < min_n:
                    # Stark priorisieren: unter min_n ist kritisch
                    val += (target_n - c) * 3.0
                elif c < target_n:
                    val += (target_n - c)
                elif c < max_n:
                    val += 0.1
        return val

    # ── Greedy Phase 1 ────────────────────────────────────────
    # Erzwungene Runs immer einschließen
    sel = [u for u in run_units if u['forced']]
    remaining = [u for u in run_units if not u['forced']]
    cov = calc_cov(sel)

    while remaining:
        best_u, best_ratio = None, -1.0
        for u in remaining:
            v = run_value(u, cov)
            if v <= 0: continue
            ratio = v / max(u['cost'], 0.01)
            if ratio > best_ratio:
                best_ratio, best_u = ratio, u
        if best_u is None: break
        # Nur hinzufügen wenn Analyt unter max_n angehoben wird
        adds = any(cov.get(a, 0) < max_n for a in all_analytes if al_lower[a] in best_u['_ls'])
        if not adds: break
        sel.append(best_u)
        remaining.remove(best_u)
        for a in all_analytes:
            if al_lower[a] in best_u['_ls']: cov[a] += 1

    # ── Greedy Phase 2: Redundante Runs entfernen ─────────────
    sel = sorted(sel, key=lambda u: -(u['cost'] or 0))
    keep = list(sel)
    for u in sel:
        if u['forced']: continue
        ls = u['_ls']
        keep_without = [x for x in keep if x is not u]
        cov_without  = calc_cov(keep_without)
        can_remove   = True
        for a in all_analytes:
            if al_lower[a] not in ls: continue
            if cov_without.get(a, 0) < min_n:
                can_remove = False
                break
        if can_remove:
            keep = keep_without
    sel = keep
    cov = calc_cov(sel)

    # ── Ergebnislabore aufbauen ───────────────────────────────
    lab_map = {}
    for u in sel:
        lab = u['lab']
        if lab not in lab_map:
            lab_map[lab] = {'result': u['_result'], 'runs': [], 'cost': 0.0}
        lab_map[lab]['runs'].append(u['run'])
        lab_map[lab]['cost'] += u['cost']

    selected_labs = []
    for lab, info in lab_map.items():
        r = dict(info['result'])
        r['selected_runs'] = sorted(info['runs'])
        r['selected_cost'] = info['cost']
        selected_labs.append(r)

    return selected_labs, sum(u['cost'] for u in sel), cov


# ─────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────
BG, FG, GRAY, LIGHT, BORDER = '#ffffff', '#111111', '#6b6b6b', '#f2f2f2', '#e0e0e0'
ACCENT    = '#1f5fbf'   # Akzentfarbe für aktive Schritte / Links
OK_FG     = '#2d6a2d'
WARN_FG   = '#9a6700'
ERR_FG    = '#b42318'
DISABLED  = '#b5b5b5'
FONT      = ('Arial', 10)
FONT_SM   = ('Arial', 9)
FONT_XS   = ('Arial', 8)
FONT_B    = ('Arial', 10, 'bold')
FONT_SMB  = ('Arial', 9, 'bold')
FONT_H    = ('Arial', 13, 'bold')

APP_TITLE = 'Analyte Comparison'


def fmt_eur(v):
    s = f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    return s + ' EUR'


def _safe_int(var, default=0):
    """IntVar.get() wirft bei leerem/ungültigem Spinbox-Text — hier abfangen."""
    try:
        return int(var.get())
    except (tk.TclError, ValueError, TypeError, AttributeError):
        return default


def _open_file(path):
    """Datei mit dem Standardprogramm öffnen (Windows, macOS, Linux)."""
    if sys.platform.startswith('win'):
        os.startfile(path)
    elif sys.platform == 'darwin':
        import subprocess; subprocess.Popen(['open', path])
    else:
        import subprocess; subprocess.Popen(['xdg-open', path])


class Tooltip:
    """Kleiner Hinweistext beim Überfahren eines Widgets mit der Maus."""
    def __init__(self, widget, text, delay=450):
        self.widget, self.text, self.delay = widget, text, delay
        self._after = None
        self._tip = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, _=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            try: self.widget.after_cancel(self._after)
            except tk.TclError: pass
            self._after = None

    def _show(self):
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f'+{x}+{y}')
        tk.Label(tw, text=self.text, font=FONT_XS, bg='#ffffe8', fg=FG,
                 relief='solid', bd=1, padx=6, pady=3, justify='left',
                 wraplength=320).pack()

    def _hide(self, _=None):
        self._cancel()
        if self._tip:
            try: self._tip.destroy()
            except tk.TclError: pass
            self._tip = None


class ScrollFrame(tk.Frame):
    """Vertikal scrollbarer Bereich. Mausrad wirkt nur, solange die Maus darüber ist."""
    def __init__(self, parent, width=220, **kw):
        bg = kw.pop('bg', BG)
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, width=width)
        self.vsb = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg, **kw)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',
            lambda e: self.canvas.itemconfig(self._win, width=e.width))
        ScrollFrame._install(self)

    @staticmethod
    def _install(widget):
        # Ein globaler Mausrad-Handler, der den ScrollFrame unter dem Mauszeiger scrollt
        root = widget.winfo_toplevel()
        if getattr(root, '_wheel_installed', False):
            return
        root._wheel_installed = True
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            widget.bind_all(seq, ScrollFrame._dispatch, add='+')

    @staticmethod
    def _dispatch(e):
        try:
            w = e.widget.winfo_containing(e.x_root, e.y_root)
        except (tk.TclError, AttributeError, KeyError):
            return
        while w is not None:
            if isinstance(w, ttk.Treeview) or isinstance(w, tk.Listbox) or isinstance(w, tk.Text):
                return  # haben eigenes Scrollverhalten
            if isinstance(w, ScrollFrame):
                w._on_wheel(e)
                return
            w = w.master

    def _on_wheel(self, e):
        # Nicht scrollen, wenn der Inhalt vollständig sichtbar ist
        if self.canvas.yview() == (0.0, 1.0):
            return
        if getattr(e, 'num', None) == 4:
            step = -1
        elif getattr(e, 'num', None) == 5:
            step = 1
        else:
            step = -1 if e.delta > 0 else 1
        self.canvas.yview_scroll(step * 2, 'units')

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


class App(tk.Tk):
    STEPS = ['PDFs laden', 'Übersicht prüfen', 'Optimieren', 'Exportieren']

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry('1400x900')
        self.minsize(1100, 650)
        try:
            self.state('zoomed')  # Vollbild beim Start (Windows)
        except tk.TclError:
            pass
        self.configure(bg=BG)

        # ── Fachlicher Zustand ────────────────────────────────
        self.files      = []
        self.results    = []
        self.masked     = set()        # deaktivierte Labore
        self.masked_runs     = set()   # Runs, die für Proben NICHT gemessen werden: 'LAB-RUN'
        self.forced_runs     = set()   # manuell erzwungene Runs: 'LAB-RUN'
        self.fixed_runs      = set()   # explizit fixierte Runs (Fix-Häkchen)
        self.ref_masked_runs = set()   # Runs, die für Referenz NICHT gemessen werden: 'LAB-RUN'
        self.lab_measure_count = {}    # lab -> Anzahl Messungen (Multiplikator), default 1
        self.opt_result = None         # (labs, cost, cov, min_n, target_n)
        self._opt_mode  = None         # 'opt' oder 'all' (Alle Labore ohne Optimierung)
        self._opt_stale = False        # Parameter seit letzter Optimierung geändert
        self._planning_path = None     # aktuell geöffnete .wz-Datei
        self._archive_dir   = None     # Archiv-Ordner
        self._art_nrs       = {}       # lab -> Artikelnummer (SelectLine)
        self._last_export_meta = ('', '', '', {})
        self._dirty   = False          # ungespeicherte Änderungen
        self._busy    = False          # PDFs werden gerade eingelesen

        # ── Tk-Variablen (einmalig angelegt, Traces nur einmal) ─
        self.lod_mode      = tk.StringVar(value='ohne')
        self.lod_on_var    = tk.BooleanVar(value=False)
        self.min_n_var     = tk.IntVar(value=3)
        self.tgt_n_var     = tk.IntVar(value=5)
        self.max_n_var     = tk.IntVar(value=6)
        self.opt_probe_var    = tk.IntVar(value=0)
        self.opt_ref_var      = tk.IntVar(value=0)
        self.opt_messtage_var = tk.IntVar(value=1)
        self.opt_ref_lab_vars = {}     # lab -> BooleanVar (Referenz an)
        self.probe_batch_vars = {}     # idx -> StringVar
        self.ref_batch_vars   = {}
        self._lab_active_vars = {}     # lab -> BooleanVar (Sidebar)
        self._lab_count_vars  = {}     # lab -> IntVar (Sidebar)

        # Hintergrund-Threads dürfen Tk nicht direkt aufrufen → Warteschlange
        self._ui_queue = queue.Queue()

        self._setup_styles()
        self._build_menu()
        self._build()

        for v in (self.min_n_var, self.tgt_n_var, self.max_n_var):
            v.trace_add('write', lambda *_: self._on_params_changed())
        for v in (self.opt_probe_var, self.opt_ref_var, self.opt_messtage_var):
            v.trace_add('write', lambda *_: self._on_probe_changed())
        self._poll_ui_queue()
        self._bind_shortcuts()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self._update_ui_state()

    def _call_soon(self, fn, *args):
        """Aus einem Hintergrund-Thread: fn(*args) im Haupt-Thread ausführen."""
        self._ui_queue.put((fn, args))

    def _poll_ui_queue(self):
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    self.report_callback_exception(*sys.exc_info())
        except queue.Empty:
            pass
        self.after(40, self._poll_ui_queue)

    # ══════════════════════════════════════════════════════════
    # Aufbau
    # ══════════════════════════════════════════════════════════
    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('Treeview', background=BG, foreground=FG, rowheight=22,
                    fieldbackground=BG, font=FONT_SM)
        s.configure('Treeview.Heading', background=LIGHT, foreground=FG,
                    font=FONT_SMB, relief='flat', padding=(4,4))
        s.map('Treeview', background=[('selected','#dfe9f8')],
                          foreground=[('selected',FG)])
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', font=FONT, padding=[18,6],
                    background='#ececec', foreground=GRAY)
        s.map('TNotebook.Tab', background=[('selected',BG)],
                               foreground=[('selected',FG)])
        s.configure('TProgressbar', background=ACCENT, troughcolor=LIGHT)
        s.configure('Sash', sashthickness=6)
        s.configure('TPanedwindow', background=BORDER)
        # Ruhigere Optik für klassische Tk-Widgets
        for cls in ('Checkbutton', 'Spinbox', 'Entry', 'Button'):
            self.option_add(f'*{cls}.highlightThickness', 0)
        self.option_add('*Checkbutton.borderWidth', 0)
        self.option_add('*Spinbox.relief', 'solid')
        self.option_add('*Spinbox.borderWidth', 1)

    def _build_menu(self):
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label='Neue Planung', accelerator='Strg+N', command=self._new_planning)
        f.add_command(label='Planung öffnen…', accelerator='Strg+O', command=self._load_planning)
        f.add_command(label='Speichern', accelerator='Strg+S', command=self._save_planning)
        f.add_command(label='Speichern unter…', accelerator='Strg+Umschalt+S',
                      command=lambda: self._save_planning(save_as=True))
        f.add_separator()
        f.add_command(label='PDF-Dateien hinzufügen…', accelerator='Strg+D', command=self._add_files)
        f.add_command(label='Alle PDFs neu einlesen', command=self._run)
        f.add_separator()
        f.add_command(label='Archivieren…', command=self._archive_planning)
        f.add_command(label='Archiv-Ordner ändern…', command=self._choose_archive_dir)
        f.add_separator()
        f.add_command(label='Beenden', command=self._on_close)
        m.add_cascade(label='Datei', menu=f)

        v = tk.Menu(m, tearoff=0)
        v.add_checkbutton(label='LOD-Werte statt Häkchen anzeigen', accelerator='Strg+L',
                          variable=self.lod_on_var, command=self._on_lod_toggle)
        v.add_separator()
        v.add_command(label='Übersicht', accelerator='Strg+1', command=lambda: self.nb.select(0))
        v.add_command(label='Optimierung', accelerator='Strg+2', command=lambda: self.nb.select(1))
        m.add_cascade(label='Ansicht', menu=v)

        h = tk.Menu(m, tearoff=0)
        h.add_command(label='Kurzanleitung', accelerator='F1', command=self._show_help)
        m.add_cascade(label='Hilfe', menu=h)
        self.config(menu=m)

    def _bind_shortcuts(self):
        b = self.bind_all
        b('<Control-n>', lambda e: self._new_planning())
        b('<Control-o>', lambda e: self._load_planning())
        b('<Control-s>', lambda e: self._save_planning())
        b('<Control-S>', lambda e: self._save_planning(save_as=True))
        b('<Control-d>', lambda e: self._add_files())
        b('<Control-e>', lambda e: self._export_opt())
        b('<Control-l>', lambda e: (self.lod_on_var.set(not self.lod_on_var.get()),
                                    self._on_lod_toggle()))
        b('<Control-Key-1>', lambda e: self.nb.select(0))
        b('<Control-Key-2>', lambda e: self.nb.select(1))
        b('<F5>', lambda e: self._run_opt())
        b('<F1>', lambda e: self._show_help())

    def _build(self):
        # ── Kopfzeile ─────────────────────────────────────────
        top = tk.Frame(self, bg=BG, padx=16, pady=10)
        top.pack(fill='x')

        logo = tk.Frame(top, bg=BG)
        logo.pack(side='left')
        tk.Label(logo, text='ANALYTE COMPARISON', font=('Arial',12,'bold'),
                 bg=BG, fg=FG).pack(anchor='w')
        self.plan_name_lbl = tk.Label(logo, text='Neue Planung', font=FONT_XS,
                                      bg=BG, fg=GRAY)
        self.plan_name_lbl.pack(anchor='w')

        # Schrittanzeige: zeigt, wo man im Ablauf steht
        steps = tk.Frame(top, bg=BG)
        steps.pack(side='left', padx=(40,0))
        self._step_lbls = []
        for i, name in enumerate(self.STEPS):
            if i:
                tk.Label(steps, text='›', font=FONT, bg=BG, fg=DISABLED).pack(side='left', padx=6)
            lbl = tk.Label(steps, text=f'{i+1}  {name}', font=FONT_SM, bg=BG,
                           fg=DISABLED, cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda e, i=i: self._goto_step(i))
            self._step_lbls.append(lbl)

        # Wichtigste Aktionen rechts
        act = tk.Frame(top, bg=BG)
        act.pack(side='right')
        self.export_top_btn = self._button(act, 'PDF exportieren…', self._export_opt, primary=True)
        self.export_top_btn.pack(side='right', padx=(6,0))
        Tooltip(self.export_top_btn, 'Planung als PDF speichern (Strg+E)')
        self.save_btn = self._button(act, 'Speichern', self._save_planning, primary=False)
        self.save_btn.pack(side='right', padx=(6,0))
        Tooltip(self.save_btn, 'Planung als .wz-Datei speichern (Strg+S)')
        self.lod_chk = tk.Checkbutton(act, text='LOD-Werte anzeigen', variable=self.lod_on_var,
                                      command=self._on_lod_toggle, font=FONT_SM, bg=BG,
                                      activebackground=BG, cursor='hand2')
        self.lod_chk.pack(side='right', padx=(6,12))
        Tooltip(self.lod_chk, 'Statt ✓ wird die Nachweisgrenze (LOD) angezeigt.\n'
                              '★ markiert den niedrigsten LOD je Analyt. (Strg+L)')

        tk.Frame(self, bg=BORDER, height=1).pack(fill='x')

        # ── Statusleiste (unten) ──────────────────────────────
        sbar = tk.Frame(self, bg=LIGHT, padx=16, pady=4)
        sbar.pack(side='bottom', fill='x')
        self.status_var = tk.StringVar(value='')
        self.status_lbl = tk.Label(sbar, textvariable=self.status_var, font=FONT_SM,
                                   fg=FG, bg=LIGHT, anchor='w')
        self.status_lbl.pack(side='left', fill='x', expand=True)
        self.progress = ttk.Progressbar(sbar, length=160, mode='determinate')
        tk.Frame(self, bg=BORDER, height=1).pack(side='bottom', fill='x')

        # ── Hauptbereich: Seitenleiste | Tabs ─────────────────
        pw = ttk.PanedWindow(self, orient='horizontal')
        pw.pack(fill='both', expand=True)
        side = tk.Frame(pw, bg=BG, padx=12, pady=10)
        self._build_sidebar(side)
        pw.add(side, weight=0)

        self.nb = ttk.Notebook(pw)
        pw.add(self.nb, weight=1)
        self._build_tab_overview()
        self._build_tab_opt()
        self.nb.bind('<<NotebookTabChanged>>', lambda e: self._update_ui_state())

    def _button(self, parent, text, cmd, primary=True, small=False):
        b = tk.Button(parent, text=text, command=cmd,
            font=FONT_XS if small else FONT_SM,
            bg=FG if primary else LIGHT, fg=BG if primary else FG,
            relief='flat', padx=8 if small else 12, pady=2 if small else 5,
            activebackground='#333' if primary else '#e2e2e2',
            activeforeground=BG if primary else FG,
            disabledforeground='#9a9a9a',
            cursor='hand2', bd=0)
        return b

    def _section_title(self, parent, text, **pack):
        lbl = tk.Label(parent, text=text, font=FONT_SMB, fg=GRAY, bg=parent['bg'])
        lbl.pack(anchor='w', **({'pady': (0,4)} | pack))
        return lbl

    # ── Seitenleiste: Dateien + Labore ────────────────────────
    def _build_sidebar(self, side):
        side.configure(width=250)
        hdr = tk.Frame(side, bg=BG)
        hdr.pack(fill='x', pady=(0,4))
        self.files_title = tk.Label(hdr, text='PDF-DATEIEN', font=FONT_SMB, fg=GRAY, bg=BG)
        self.files_title.pack(side='left')

        btns = tk.Frame(side, bg=BG)
        btns.pack(fill='x', pady=(0,4))
        add_b = self._button(btns, '+ Hinzufügen…', self._add_files, primary=True, small=True)
        add_b.pack(side='left')
        Tooltip(add_b, 'Ringversuchs-PDFs auswählen (Strg+D).\nSie werden sofort eingelesen.')
        self.remove_btn = self._button(btns, 'Entfernen', self._remove_file, primary=False, small=True)
        self.remove_btn.pack(side='left', padx=(4,0))
        Tooltip(self.remove_btn, 'Markierte Datei(en) entfernen (Entf)')

        fl = tk.Frame(side, bg=BORDER, padx=1, pady=1)
        fl.pack(fill='x')
        fi = tk.Frame(fl, bg=BG)
        fi.pack(fill='both', expand=True)
        sb_y = ttk.Scrollbar(fi, orient='vertical')
        self.file_lb = tk.Listbox(fi, yscrollcommand=sb_y.set, font=FONT_SM, height=8,
            bg=BG, fg=FG, selectbackground='#dfe9f8', selectforeground=FG,
            relief='flat', bd=0, activestyle='none', selectmode='extended',
            highlightthickness=0, width=28)
        sb_y.config(command=self.file_lb.yview)
        sb_y.pack(side='right', fill='y')
        self.file_lb.pack(side='left', fill='both', expand=True, padx=4, pady=2)
        self.file_lb.bind('<Delete>', lambda e: self._remove_file())
        self.file_lb.bind('<BackSpace>', lambda e: self._remove_file())
        self.file_lb.bind('<<ListboxSelect>>', lambda e: self._update_ui_state())

        # Labore
        lh = tk.Frame(side, bg=BG)
        lh.pack(fill='x', pady=(16,2))
        tk.Label(lh, text='LABORE', font=FONT_SMB, fg=GRAY, bg=BG).pack(side='left')
        msr = tk.Label(lh, text='Messungen', font=FONT_XS, fg=GRAY, bg=BG)
        msr.pack(side='right')
        Tooltip(msr, 'Wie oft das Labor misst.\nZählt entsprechend mehrfach in der Abdeckung (n).')
        tk.Label(side, text='Häkchen entfernen = Labor nicht berücksichtigen',
                 font=FONT_XS, fg=GRAY, bg=BG, anchor='w', justify='left',
                 wraplength=220).pack(anchor='w', pady=(0,4))
        self.lab_list = ScrollFrame(side, width=190)
        self.lab_list.pack(fill='both', expand=True)

    def _refresh_lab_list(self):
        self.lab_list.clear()
        inner = self.lab_list.inner
        if not self.results:
            tk.Label(inner, text='Noch keine Labore –\nzuerst PDFs hinzufügen.',
                     font=FONT_SM, fg=GRAY, bg=BG, justify='left').pack(anchor='w', pady=4)
            return
        for r in self.results:
            lab = r['lab']
            row = tk.Frame(inner, bg=BG)
            row.pack(fill='x', pady=1)
            av = tk.BooleanVar(value=lab not in self.masked)
            self._lab_active_vars[lab] = av
            has_data = bool(r.get('analytes'))
            cb = tk.Checkbutton(row, text=lab, variable=av, font=FONT_SM, bg=BG,
                                activebackground=BG, anchor='w', cursor='hand2',
                                fg=FG if has_data else ERR_FG,
                                command=lambda l=lab: self._toggle_mask(l))
            cb.pack(side='left', fill='x', expand=True)
            tip = r.get('filename', '')
            if r.get('product'):
                tip += f"\nProdukt: {r['product']}"
            tip += f"\n{len(r.get('analytes', []))} Analyten, {len(r.get('runs', {}))} Runs"
            if not has_data:
                tip += '\n⚠ Keine Analyten erkannt – PDF prüfen.'
            Tooltip(cb, tip)
            cv = tk.IntVar(value=self.lab_measure_count.get(lab, 1))
            self._lab_count_vars[lab] = cv
            sp = tk.Spinbox(row, from_=1, to=20, width=3, textvariable=cv, font=FONT_SM,
                            justify='right', command=lambda l=lab: self._on_count_spin(l))
            sp.pack(side='right')
            sp.bind('<FocusOut>', lambda e, l=lab: self._on_count_spin(l))
            sp.bind('<Return>',   lambda e, l=lab: self._on_count_spin(l))

    def _on_count_spin(self, lab):
        var = self._lab_count_vars.get(lab)
        n = max(1, _safe_int(var, 1)) if var else 1
        self._set_lab_measure_count(lab, n)

    # ── Tab 1: Übersicht ──────────────────────────────────────
    def _build_tab_overview(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text='Übersicht')
        self.ov_stack = tk.Frame(tab, bg=BG)
        self.ov_stack.pack(fill='both', expand=True, padx=8, pady=8)

        # Tabelle
        self.ov_table_frame = tk.Frame(self.ov_stack, bg=BG)
        tf = tk.Frame(self.ov_table_frame, bg=BG)
        tf.pack(fill='both', expand=True)
        self.tree = self._tree(tf)
        self.tree.bind('<Button-3>', lambda e: self._heading_menu(self.tree, e))
        self._legend(self.ov_table_frame, [
            ('✓', 'Labor misst den Analyten'),
            ('○', 'nur in einem deaktivierten Labor'),
            ('2✓', 'Labor misst mehrfach'),
            ('n', 'Anzahl Messungen gesamt'),
        ], hint='Rechtsklick auf einen Laborkopf: Labor ein-/ausblenden, Messungen setzen')

        # Leerer Zustand: erklärt, was zu tun ist
        self.ov_empty = self._empty_state(self.ov_stack,
            'Noch keine Daten',
            'Füge die Ringversuchs-PDFs der Labore hinzu.\n'
            'Sie werden automatisch eingelesen und hier als Tabelle angezeigt.',
            [('PDF-Dateien hinzufügen…', self._add_files, True),
             ('Gespeicherte Planung öffnen…', self._load_planning, False)])

    def _empty_state(self, parent, title, text, actions):
        f = tk.Frame(parent, bg=BG)
        box = tk.Frame(f, bg=BG)
        box.place(relx=0.5, rely=0.4, anchor='center')
        tk.Label(box, text=title, font=FONT_H, bg=BG, fg=FG).pack(pady=(0,6))
        lbl = tk.Label(box, text=text, font=FONT, bg=BG, fg=GRAY, justify='center')
        lbl.pack(pady=(0,16))
        row = tk.Frame(box, bg=BG)
        row.pack()
        f._btns = []
        for label, cmd, primary in actions:
            b = self._button(row, label, cmd, primary=primary)
            b.pack(side='left', padx=4)
            f._btns.append(b)
        f._text_lbl = lbl
        return f

    def _legend(self, parent, items, hint=''):
        leg = tk.Frame(parent, bg=BG)
        leg.pack(fill='x', pady=(6,0))
        for sym, txt in items:
            if sym.startswith('#'):
                tk.Label(leg, text='   ', bg=sym, relief='solid', bd=1).pack(side='left', padx=(0,4))
            else:
                tk.Label(leg, text=sym, font=FONT_SMB, bg=BG, fg=FG).pack(side='left', padx=(0,4))
            tk.Label(leg, text=txt, font=FONT_XS, bg=BG, fg=GRAY).pack(side='left', padx=(0,14))
        if hint:
            tk.Label(leg, text=hint, font=FONT_XS, bg=BG, fg=GRAY).pack(side='right')
        return leg

    def _tree(self, parent):
        t = ttk.Treeview(parent, show='headings', selectmode='browse')
        vsb = ttk.Scrollbar(parent, orient='vertical', command=t.yview)
        hsb = ttk.Scrollbar(parent, orient='horizontal', command=t.xview)
        t.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side='bottom', fill='x')
        vsb.pack(side='right', fill='y')
        t.pack(fill='both', expand=True)
        t.tag_configure('group',    background='#e9e9e9', font=FONT_SMB)
        t.tag_configure('alt',      background='#fafafa')
        t.tag_configure('normal',   background=BG)
        t.tag_configure('inactive', background='#f0f0f0', foreground='#aaaaaa')
        t.tag_configure('ok5',      background='#e8f5e9')
        t.tag_configure('ok3',      background='#fff9e6')
        t.tag_configure('low',      background='#fdecea')
        return t

    # ── Tab 2: Optimierung ────────────────────────────────────
    def _build_tab_opt(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text='Optimierung')

        # Kontrollleiste
        ctrl = tk.Frame(tab, bg=LIGHT, padx=12, pady=8)
        ctrl.pack(fill='x')

        def spin(label, var, tip):
            box = tk.Frame(ctrl, bg=LIGHT)
            box.pack(side='left', padx=(0,14))
            l = tk.Label(box, text=label, font=FONT_SM, bg=LIGHT, fg=FG)
            l.pack(side='left', padx=(0,4))
            s = tk.Spinbox(box, from_=1, to=20, width=3, textvariable=var, font=FONT_SM,
                           justify='right')
            s.pack(side='left')
            Tooltip(l, tip); Tooltip(s, tip)

        tk.Label(ctrl, text='Abdeckung je Analyt:', font=FONT_SMB, bg=LIGHT,
                 fg=FG).pack(side='left', padx=(0,10))
        spin('mindestens', self.min_n_var,
             'Jeder Analyt soll von mindestens so vielen Laboren gemessen werden.\n'
             'Analyten darunter werden rot markiert.')
        spin('Ziel', self.tgt_n_var,
             'Angestrebte Anzahl Messungen je Analyt (grün markiert).')
        spin('höchstens', self.max_n_var,
             'Über dieser Anzahl werden keine weiteren Runs für einen Analyten hinzugefügt.')

        self.opt_btn = self._button(ctrl, 'Optimieren  (F5)', self._run_opt, primary=True)
        self.opt_btn.pack(side='left', padx=(4,6))
        Tooltip(self.opt_btn, 'Günstigste Kombination von Laboren und Runs berechnen,\n'
                              'die die gewünschte Abdeckung erreicht.')
        self.all_btn = self._button(ctrl, 'Alle Labore übernehmen', self._show_all_labs_overview,
                                    primary=False)
        self.all_btn.pack(side='left')
        Tooltip(self.all_btn, 'Ohne Optimierung: alle aktiven Labore mit allen Runs einplanen.')

        self.opt_preview_btn = self._button(ctrl, 'Vorschau', self._preview_opt, primary=False)
        self.opt_preview_btn.pack(side='right')
        Tooltip(self.opt_preview_btn, 'PDF-Vorschau öffnen (ohne zu speichern)')

        # Ergebniszeile
        res = tk.Frame(tab, bg=BG, padx=12, pady=6)
        res.pack(fill='x')
        self.opt_status = tk.StringVar(value='')
        self.opt_status_lbl = tk.Label(res, textvariable=self.opt_status, font=FONT_B,
                                       fg=FG, bg=BG, anchor='w')
        self.opt_status_lbl.pack(side='left')
        self.opt_hint = tk.StringVar(value='')
        self.opt_hint_lbl = tk.Label(res, textvariable=self.opt_hint, font=FONT_SM,
                                     fg=WARN_FG, bg=BG, anchor='w')
        self.opt_hint_lbl.pack(side='left', padx=(14,0))
        tk.Frame(tab, bg=BORDER, height=1).pack(fill='x')

        self.opt_stack = tk.Frame(tab, bg=BG)
        self.opt_stack.pack(fill='both', expand=True)

        self.opt_empty = self._empty_state(self.opt_stack,
            'Noch nicht optimiert',
            'Lege oben die gewünschte Abdeckung fest und klicke auf „Optimieren“.\n'
            'Danach kannst du einzelne Runs an- und abwählen – die Kosten aktualisieren sich sofort.',
            [('Optimieren', self._run_opt, True),
             ('Alle Labore übernehmen', self._show_all_labs_overview, False)])

        # Body: Runs | Tabelle | Kosten & Proben (Breiten per Maus verstellbar)
        self.opt_body = ttk.PanedWindow(self.opt_stack, orient='horizontal')

        # Links: Auswahl je Labor
        left = tk.Frame(self.opt_body, bg=BG, padx=10, pady=10)
        self._section_title(left, 'AUSWAHL JE LABOR')
        lh = tk.Frame(left, bg=BG)
        lh.pack(fill='x', padx=(0,18))
        for txt, w, tip in [
                ('Probe', 5, 'Run wird für die Proben gemessen'),
                ('Ref', 4, 'Run wird auch für die Referenzproben gemessen'),
                ('Run / Kosten', 0, 'Klick auf den Namen schaltet Probe und Ref zusammen'),
                ('Fix', 3, 'Run beim erneuten Optimieren immer behalten')]:
            l = tk.Label(lh, text=txt, font=FONT_XS, fg=GRAY, bg=BG, width=w or None,
                         anchor='w' if not w else 'center')
            l.pack(side='right' if txt == 'Fix' else 'left',
                   fill='x' if not w else None, expand=not w)
            Tooltip(l, tip)
        tk.Frame(left, bg=BORDER, height=1).pack(fill='x', pady=(2,0))
        self.opt_lab_scroll = ScrollFrame(left, width=300)
        self.opt_lab_scroll.pack(fill='both', expand=True)
        self.opt_lab_frame = self.opt_lab_scroll.inner
        self.opt_body.add(left, weight=0)

        # Mitte: Abdeckungstabelle
        mid = tk.Frame(self.opt_body, bg=BG, padx=8, pady=10)
        self._section_title(mid, 'ABDECKUNG')
        tf = tk.Frame(mid, bg=BG)
        tf.pack(fill='both', expand=True)
        self.opt_tree = self._tree(tf)
        self.opt_tree.bind('<Button-3>', self._opt_rightclick)
        self._legend(mid, [
            ('#e8f5e9', 'Ziel erreicht'),
            ('#fff9e6', 'Minimum erreicht'),
            ('#fdecea', 'unter Minimum'),
            ('(A)', 'gewählte Runs'),
            ('[B]', 'weitere Runs, nicht gewählt'),
        ], hint='Rechtsklick: Labor/Run ein- oder ausblenden')
        self.opt_body.add(mid, weight=1)

        # Rechts: Kosten, Probenrechner, Chargen
        right = tk.Frame(self.opt_body, bg=BG, pady=10)
        self.opt_right = ScrollFrame(right, width=275, padx=10)
        self.opt_right.pack(fill='both', expand=True)
        r = self.opt_right.inner

        self._section_title(r, 'KOSTEN PRO PROBE')
        self.opt_cost_frame_container = tk.Frame(r, bg=BG)
        self.opt_cost_frame_container.pack(fill='x')
        self.opt_cost_frame = tk.Frame(self.opt_cost_frame_container, bg=BG)
        self.opt_cost_frame.pack(fill='x')

        tk.Frame(r, bg=BORDER, height=1).pack(fill='x', pady=(12,10))
        self._section_title(r, 'PROBENRECHNER')
        for label, var, lo, tip in [
                ('Proben', self.opt_probe_var, 0, 'Anzahl Proben pro Messtag'),
                ('Referenzproben', self.opt_ref_var, 0, 'Anzahl Referenzproben pro Messtag'),
                ('Messtage', self.opt_messtage_var, 1, 'Alle Mengen werden mit den Messtagen multipliziert')]:
            row = tk.Frame(r, bg=BG)
            row.pack(fill='x', pady=2)
            l = tk.Label(row, text=label, font=FONT_SM, fg=FG, bg=BG, anchor='w')
            l.pack(side='left', fill='x', expand=True)
            sb = tk.Spinbox(row, from_=lo, to=9999, width=6, textvariable=var,
                            font=FONT_SM, justify='right')
            sb.pack(side='right')
            Tooltip(l, tip)

        self.opt_ref_frame = tk.Frame(r, bg=BG)
        self.opt_ref_frame.pack(fill='x')

        tk.Frame(r, bg=BORDER, height=1).pack(fill='x', pady=(10,8))
        self._section_title(r, 'GESAMTKOSTEN')
        self.opt_probe_lbl = tk.Label(r, text='', font=FONT_SM, fg=FG, bg=BG,
                                      anchor='w', justify='left')
        self.opt_probe_lbl.pack(anchor='w', fill='x')

        tk.Frame(r, bg=BORDER, height=1).pack(fill='x', pady=(10,8))
        self._section_title(r, 'CHARGEN')
        self._batch_container = tk.Frame(r, bg=BG)
        self._batch_container.pack(fill='x')
        self.opt_body.add(right, weight=0)

        tk.Frame(tab, bg=BORDER, height=1).pack(fill='x')
        foot = tk.Frame(tab, bg=BG, padx=12, pady=8)
        foot.pack(fill='x')
        self.opt_export_btn = self._button(foot, 'PDF exportieren…', self._export_opt, primary=True)
        self.opt_export_btn.pack(side='right')
        self.opt_archive_btn = self._button(foot, 'Archivieren…', self._archive_planning, primary=False)
        self.opt_archive_btn.pack(side='right', padx=(0,6))
        Tooltip(self.opt_archive_btn, 'PDF und Planung (.wz) gemeinsam im Archiv-Ordner ablegen')

    # ══════════════════════════════════════════════════════════
    # Zustand der Oberfläche
    # ══════════════════════════════════════════════════════════
    def _set_status(self, text, kind='info'):
        self.status_var.set(text)
        self.status_lbl.config(fg={'info': FG, 'ok': OK_FG, 'warn': WARN_FG,
                                   'error': ERR_FG}.get(kind, FG))

    def _mark_dirty(self, dirty=True):
        self._dirty = dirty
        self._update_title()

    def _update_title(self):
        name = os.path.basename(self._planning_path) if self._planning_path else 'Neue Planung'
        mark = ' •' if self._dirty else ''
        self.title(f'{APP_TITLE} — {name}{mark}')
        self.plan_name_lbl.config(
            text=name + ('  (ungespeichert)' if self._dirty else ''))

    def _current_step(self):
        if not self.results:
            return 0
        if not self.opt_result:
            return 1 if self.nb.index('current') == 0 else 2
        return 3

    def _goto_step(self, i):
        if i == 0:
            self._add_files()
        elif i == 1:
            self.nb.select(0)
        elif i == 2:
            self.nb.select(1)
        elif i == 3:
            self._export_opt()

    def _update_ui_state(self):
        has_files   = bool(self.files)
        has_results = bool(self.results)
        has_opt     = self.opt_result is not None
        busy        = self._busy

        # Schrittanzeige
        cur = self._current_step()
        for i, lbl in enumerate(self._step_lbls):
            if i < cur:
                lbl.config(fg=OK_FG, font=FONT_SM, text=f'✓  {self.STEPS[i]}')
            elif i == cur:
                lbl.config(fg=ACCENT, font=FONT_SMB, text=f'{i+1}  {self.STEPS[i]}')
            else:
                lbl.config(fg=DISABLED, font=FONT_SM, text=f'{i+1}  {self.STEPS[i]}')

        self.files_title.config(text=f'PDF-DATEIEN ({len(self.files)})' if has_files else 'PDF-DATEIEN')
        self.remove_btn.config(state='normal' if self.file_lb.curselection() and not busy else 'disabled')

        exp = 'normal' if has_opt and not busy else 'disabled'
        for b in (self.export_top_btn, self.opt_export_btn, self.opt_preview_btn, self.opt_archive_btn):
            b.config(state=exp)
        self.save_btn.config(state='normal' if has_results and not busy else 'disabled')
        run_state = 'normal' if has_results and not busy else 'disabled'
        self.opt_btn.config(state=run_state)
        self.all_btn.config(state=run_state)
        for b in self.opt_empty._btns:
            b.config(state=run_state)

        # Übersicht: Tabelle oder Leerzustand
        if has_results:
            self.ov_empty.pack_forget()
            self.ov_table_frame.pack(fill='both', expand=True)
        else:
            self.ov_table_frame.pack_forget()
            self.ov_empty.pack(fill='both', expand=True)

        # Optimierung: Ergebnis oder Leerzustand
        if has_opt:
            self.opt_empty.pack_forget()
            self.opt_body.pack(fill='both', expand=True)
        else:
            self.opt_body.pack_forget()
            self.opt_empty.pack(fill='both', expand=True)
            self.opt_empty._text_lbl.config(text=(
                'Lege oben die gewünschte Abdeckung fest und klicke auf „Optimieren“.\n'
                'Danach kannst du einzelne Runs an- und abwählen – die Kosten aktualisieren sich sofort.'
                if has_results else
                'Zuerst PDF-Dateien hinzufügen (links). Danach kann hier optimiert werden.'))
            if not busy:
                self.opt_status.set('')

        if not self.status_var.get() and not busy:
            self._set_status('Bereit. PDF-Dateien hinzufügen, um zu beginnen.' if not has_files
                             else f'{len(self.results)} Labore geladen.')

    def _show_help(self):
        messagebox.showinfo('Kurzanleitung',
            '1. PDFs laden\n'
            '   Links auf „+ Hinzufügen…“ klicken. Die PDFs werden sofort eingelesen.\n\n'
            '2. Übersicht prüfen\n'
            '   Die Tabelle zeigt, welches Labor welchen Analyten misst.\n'
            '   Links können Labore abgewählt und Mehrfachmessungen eingestellt werden.\n\n'
            '3. Optimieren\n'
            '   Gewünschte Abdeckung einstellen und „Optimieren“ klicken (F5).\n'
            '   Runs links per Häkchen an-/abwählen: Probe, Ref (Referenz), Fix.\n'
            '   Rechts Proben, Referenzproben und Messtage eintragen.\n\n'
            '4. Exportieren\n'
            '   „PDF exportieren…“ (Strg+E) oder „Archivieren…“.\n\n'
            'Speichern: Strg+S · Öffnen: Strg+O · Neu: Strg+N', parent=self)

    # ══════════════════════════════════════════════════════════
    # Dateien
    # ══════════════════════════════════════════════════════════
    def _add_files(self):
        if self._busy:
            return
        paths = filedialog.askopenfilenames(
            parent=self, title='PDF-Dateien auswählen', filetypes=[('PDF','*.pdf')])
        new = [p for p in paths if p not in self.files]
        dup = len(paths) - len(new)
        for p in new:
            self.files.append(p)
            self.file_lb.insert('end', os.path.basename(p))
        if new:
            self._mark_dirty()
            self._parse_files(new, reset=False)
        elif dup:
            self._set_status(f'{dup} Datei(en) waren bereits in der Liste.', 'warn')

    def _remove_file(self):
        if self._busy:
            return
        sel = sorted(self.file_lb.curselection(), reverse=True)
        if not sel:
            return
        removed = []
        for idx in sel:
            self.file_lb.delete(idx)
            removed.append(os.path.basename(self.files.pop(idx)))
        before = len(self.results)
        self.results = [r for r in self.results if r.get('filename') not in removed]
        known = {r['lab'] for r in self.results}
        self.masked &= known
        self._mark_dirty()
        if len(self.results) != before:
            self._after_results_changed()
        self._set_status(f'{len(removed)} Datei(en) entfernt.')
        self._update_ui_state()

    def _run(self):
        """Alle Dateien neu einlesen."""
        if not self.files:
            self._set_status('Keine Dateien vorhanden – bitte zuerst PDFs hinzufügen.', 'warn')
            return
        self._parse_files(list(self.files), reset=True)

    def _parse_files(self, paths, reset, on_done=None):
        if self._busy:
            return
        self._busy = True
        if reset:
            self.results = []
        self.progress.pack(side='right', before=self.status_lbl)
        self.progress['maximum'] = len(paths)
        self.progress['value']   = 0
        self.config(cursor='watch')
        self._update_ui_state()

        def worker():
            parsed, errors = [], []
            for i, path in enumerate(paths):
                name = os.path.basename(path)
                self._call_soon(self._set_status, f'Lese {i+1}/{len(paths)}: {name} …')
                try:
                    parsed.append(parse_pdf(path))
                except Exception as e:
                    errors.append(f'{name}: {e}')
                    parsed.append({'lab': name[:15], 'analytes': [], 'cost': None,
                                   'runs': {}, 'filename': name})
                self._call_soon(self.progress.configure, {'value': i+1})
            self._call_soon(self._on_parsed, parsed, errors, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_parsed(self, parsed, errors, on_done=None):
        self._busy = False
        self.config(cursor='')
        self.progress.pack_forget()
        self.results.extend(parsed)
        # Reihenfolge wie in der Dateiliste
        order = {os.path.basename(p): i for i, p in enumerate(self.files)}
        self.results.sort(key=lambda r: order.get(r.get('filename'), 999))
        known = {r['lab'] for r in self.results}
        self.masked &= known

        empty = [r['filename'] for r in parsed if not r.get('analytes')]
        if errors:
            self._set_status(f'{len(errors)} Datei(en) konnten nicht gelesen werden.', 'error')
            self.after_idle(lambda: messagebox.showerror('Fehler beim Einlesen',
                'Folgende Dateien konnten nicht gelesen werden:\n\n' + '\n'.join(errors),
                parent=self))
        elif empty:
            self._set_status(f'{len(parsed)} Datei(en) eingelesen – in {len(empty)} wurden '
                             f'keine Analyten erkannt: {", ".join(empty)}', 'warn')
        else:
            self._set_status(f'{len(parsed)} Datei(en) eingelesen · '
                             f'{len(self.results)} Labore insgesamt.', 'ok')
        if on_done:
            on_done()
        else:
            self._after_results_changed()
        self._update_ui_state()

    def _after_results_changed(self):
        """Nach Änderung der Laborliste: alle Ansichten aktualisieren."""
        self._refresh_lab_list()
        self._refresh_overview()
        if self.opt_result is not None:
            # Bestehendes Ergebnis mit neuer Laborliste neu berechnen
            self._opt_stale = True
            self._rerun_opt_after_mask()

    # ══════════════════════════════════════════════════════════
    # Übersicht
    # ══════════════════════════════════════════════════════════
    def _active(self):
        return [r for r in self.results if r['lab'] not in self.masked]

    def _refresh_overview(self):
        self._render_table(self.tree, self._active(), show_all_analytes=True)

    def _refresh_opt_table(self):
        if self.opt_result:
            labs, cost, cov, min_n, target_n = self.opt_result
            self._render_table(self.opt_tree, labs,
                               coverage=cov,
                               min_n=min_n, target_n=target_n, show_all_analytes=True)

    def _render_table(self, tree, results, coverage=None,
                      min_n=None, target_n=None, show_all_analytes=False):
        # Scrollposition merken, damit die Tabelle beim Umschalten nicht springt
        try:
            ypos = tree.yview()[0]
            xpos = tree.xview()[0]
        except tk.TclError:
            ypos = xpos = 0
        tree.delete(*tree.get_children())
        tree['columns'] = []
        if not self.results:
            return

        all_a = sorted(
            {a for r in self.results
             for a in r.get('all_analytes', r['analytes'])},
            key=sort_key)

        # Spalten = alle geladenen Labore (gewählte + nicht gewählte)
        all_results_for_cols = list(self.results)
        labs_cols = [r['lab'] for r in all_results_for_cols]

        cols = ['Analyt'] + labs_cols + ['n']
        tree['columns'] = cols
        tree.heading('Analyt', text='Analyt', anchor='w')
        tree.column('Analyt', width=200, minwidth=120, stretch=False)
        opt_labs_set = {r['lab'] for r in results}
        for lab in labs_cols:
            mcount = self.lab_measure_count.get(lab, 1)
            head = lab + (f' ×{mcount}' if mcount != 1 else '')
            if lab in self.masked:
                head = '(' + head + ')'
            tree.heading(lab, text=head)
            w = max(70, min(len(head)*9, 160)) if coverage is None else max(90, min(len(head)*9, 170))
            tree.column(lab, width=w, minwidth=50, stretch=False, anchor='center')
        tree.heading('n', text='n')
        tree.column('n', width=40, minwidth=36, stretch=False, anchor='center')

        lod_on = self.lod_mode.get() == 'mit'
        _lod_lookup = {}
        if lod_on:
            for r in all_results_for_cols:
                _lod_lookup[r['lab']] = {k.lower(): v for k, v in r.get('lod', {}).items()}

        cur_group = None
        row_idx = 0
        for analyte in all_a:
            grp = get_group(analyte)
            if grp != cur_group:
                cur_group = grp
                tree.insert('', 'end',
                    values=[grp.upper()] + ['']*(len(labs_cols)+1),
                    tags=('group',))
                row_idx += 1
            vals = [analyte]
            count = 0
            _row_lod = []  # (index in vals, LOD-Wert) für Zellen mit has=True und bekanntem LOD
            for r in all_results_for_cols:
                lab = r['lab']
                in_opt = lab in opt_labs_set
                if in_opt:
                    r_opt = next((x for x in results if x['lab'] == lab), r)
                    runs = r_opt.get('runs', r.get('runs', {}))
                    sel_runs = r_opt.get('selected_runs', list(runs.keys()))
                else:
                    runs = r.get('runs', {})
                    sel_runs = []  # nicht gewählt → keine aktiven Runs
                orig = next((x for x in self.results if x['lab'] == lab), r)
                all_runs_lab = list(orig.get('runs', runs).keys())

                mcount = self.lab_measure_count.get(lab, 1)
                mprefix = f'{mcount}' if mcount != 1 else ''
                _lv = _lod_lookup.get(lab, {}).get(analyte.lower()) if lod_on else None

                if runs:
                    active_runs = []
                    for rl in sel_runs:
                        key = f"{lab}-{rl}"
                        if key not in self.masked_runs:
                            if any(a.lower()==analyte.lower()
                                   for a in runs.get(rl, {}).get('analytes', [])):
                                active_runs.append(rl)

                    inactive_runs = []
                    for rl in all_runs_lab:
                        if rl in sel_runs: continue
                        if any(a.lower()==analyte.lower()
                               for a in orig.get('runs',{}).get(rl,{}).get('analytes',[])):
                            inactive_runs.append(rl)

                    has = len(active_runs) > 0
                    if has:
                        base = (f'{_lv:g}' if _lv is not None else '✓') if lod_on else (mprefix + '✓')
                        if coverage is not None:
                            cell = base + ' (' + ','.join(active_runs) + ')'
                            if inactive_runs:
                                cell += ' [' + ','.join(inactive_runs) + ']'
                        else:
                            cell = base
                    elif inactive_runs:
                        # Vorhanden aber nicht gewählt — zählt NICHT
                        cell = '○ [' + ','.join(inactive_runs) + ']' if coverage is not None else '○'
                    else:
                        cell = ''
                else:
                    has = in_opt and any(a.lower() == analyte.lower() for a in r['analytes'])
                    present = any(a.lower() == analyte.lower() for a in r['analytes'])
                    if has:
                        cell = (f'{_lv:g}' if _lv is not None else '✓') if lod_on else (mprefix + '✓')
                    elif present:
                        cell = '○'
                    else:
                        cell = ''
                if lod_on and has and _lv is not None:
                    _row_lod.append((len(vals), _lv))
                vals.append(cell)
                if has: count += mcount
            vals.append(str(count) if count else '–')

            if lod_on and _row_lod:
                _min_v = min(v for _, v in _row_lod)
                for _idx, _v in _row_lod:
                    if _v == _min_v:
                        vals[_idx] = '★' + vals[_idx]

            if coverage is not None:
                c = count
                tag = 'ok5' if c >= target_n else 'ok3' if c >= min_n else 'low'
            else:
                if count == 0:
                    tag = 'inactive'
                else:
                    tag = 'alt' if row_idx % 2 == 0 else 'normal'
            tree.insert('', 'end', values=vals, tags=(tag,))
            row_idx += 1

        tree.yview_moveto(ypos)
        tree.xview_moveto(xpos)

    def _heading_menu(self, tree, event):
        """Rechtsklick auf einen Laborkopf: Labor ein-/ausblenden, Messanzahl setzen."""
        if tree.identify_region(event.x, event.y) != 'heading':
            return False
        try:
            idx = int(tree.identify_column(event.x).replace('#', '')) - 1
            cols = list(tree['columns'])
            if idx < 0 or idx >= len(cols):
                return True
            name = cols[idx]
        except (ValueError, tk.TclError):
            return True
        if name in ('Analyt', 'n'):
            return True
        menu = tk.Menu(self, tearoff=0)
        label = 'Labor wieder berücksichtigen' if name in self.masked else 'Labor nicht berücksichtigen'
        menu.add_command(label=f'{label}: {name}', command=lambda: self._toggle_mask(name))
        n_now = self.lab_measure_count.get(name, 1)
        menu.add_command(label=f'Anzahl Messungen setzen … (aktuell {n_now}×)',
                         command=lambda: self._ask_lab_measure_count(name))
        menu.tk_popup(event.x_root, event.y_root)
        return True

    def _toggle_mask(self, lab):
        if lab in self.masked:
            self.masked.discard(lab)
        else:
            self.masked.add(lab)
        var = self._lab_active_vars.get(lab)
        if var is not None and var.get() != (lab not in self.masked):
            var.set(lab not in self.masked)
        self._mark_dirty()
        self._refresh_overview()
        if self.opt_result is not None:
            self._rerun_opt_after_mask()
        state = 'nicht berücksichtigt' if lab in self.masked else 'wieder berücksichtigt'
        self._set_status(f'Labor {lab} wird {state}.')

    def _ask_lab_measure_count(self, lab):
        current = self.lab_measure_count.get(lab, 1)
        n = simpledialog.askinteger(
            'Anzahl Messungen', f'Wie oft misst Labor {lab}?',
            initialvalue=current, minvalue=1, maxvalue=20, parent=self)
        if n is not None:
            self._set_lab_measure_count(lab, n)

    def _set_lab_measure_count(self, lab, n):
        if n == self.lab_measure_count.get(lab, 1):
            return
        if n == 1:
            self.lab_measure_count.pop(lab, None)
        else:
            self.lab_measure_count[lab] = n
        var = self._lab_count_vars.get(lab)
        if var is not None and _safe_int(var, 1) != n:
            var.set(n)
        self._mark_dirty()
        self._refresh_overview()
        self._refresh_opt_table()

    def _on_lod_toggle(self):
        self.lod_mode.set('mit' if self.lod_on_var.get() else 'ohne')
        self._refresh_overview()
        self._refresh_opt_table()

    def _set_lod_mode(self, mode):
        self.lod_on_var.set(mode == 'mit')
        self._on_lod_toggle()

    # ══════════════════════════════════════════════════════════
    # Optimierung
    # ══════════════════════════════════════════════════════════
    def _get_params(self):
        """Liest Min/Ziel/Max und prüft sie. Gibt None zurück, wenn ungültig."""
        mn = _safe_int(self.min_n_var, None)
        tg = _safe_int(self.tgt_n_var, None)
        mx = _safe_int(self.max_n_var, None)
        if None in (mn, tg, mx) or mn < 1:
            return None, 'Bitte für Minimum, Ziel und Höchstwert ganze Zahlen ≥ 1 eingeben.'
        if not (mn <= tg <= mx):
            return None, f'Es muss gelten: mindestens ({mn}) ≤ Ziel ({tg}) ≤ höchstens ({mx}).'
        return (mn, tg, mx), ''

    def _on_params_changed(self):
        params, err = self._get_params()
        if err:
            self.opt_hint.set('⚠ ' + err)
            self.opt_hint_lbl.config(fg=ERR_FG)
            return
        if self.opt_result is not None and self._opt_mode == 'opt':
            _, _, _, mn, tg = self.opt_result
            if (mn, tg) != params[:2] or self._opt_stale:
                self.opt_hint.set('Parameter geändert – „Optimieren“ klicken, um neu zu berechnen.')
                self.opt_hint_lbl.config(fg=WARN_FG)
                return
        self._update_opt_hint()

    def _update_opt_hint(self):
        """Hinweis zu Analyten, die das Minimum nicht erreichen."""
        self.opt_hint_lbl.config(fg=WARN_FG)
        if not self.opt_result or self._opt_mode != 'opt':
            self.opt_hint.set('')
            return
        labs, cost, cov, min_n, target_n = self.opt_result
        low = [a for a, c in cov.items() if c < min_n]
        if low:
            shown = ', '.join(sorted(low, key=sort_key)[:5])
            more  = f' und {len(low)-5} weitere' if len(low) > 5 else ''
            self.opt_hint.set(f'⚠ {len(low)} Analyt(en) unter Minimum: {shown}{more}')
            self.opt_hint_lbl.config(fg=ERR_FG)
        else:
            self.opt_hint.set('')

    def _show_all_labs_overview(self):
        """Alle aktiven Labore mit allen Runs einplanen — ohne Optimierung."""
        active = self._active()
        if not active:
            self._set_status('Keine aktiven Labore.', 'warn')
            return
        labs = []
        for r in active:
            lab_copy = dict(r)
            runs_d = r.get('runs', {})
            lab_copy['selected_runs'] = list(runs_d.keys())
            lab_copy['selected_cost'] = sum((rd.get('cost') or 0) for rd in runs_d.values())
            labs.append(lab_copy)
        total = sum(r['selected_cost'] for r in labs)
        self.opt_result = (labs, total, {}, 0, 0)
        self._opt_mode = 'all'
        self._opt_stale = False
        self._mark_dirty()
        self.nb.select(1)
        self._render_opt_labs(labs, total)
        self._refresh_opt_table()
        self.opt_status.set(f'Alle {len(labs)} aktiven Labore · ohne Optimierung')
        self._update_opt_hint()
        self._update_ui_state()

    def _rerun_opt_after_mask(self):
        """Ergebnis mit aktuell aktiven Laboren/Runs neu berechnen.

        Alle Runs, die im aktuellen Ergebnis gewählt sind, bleiben erhalten —
        außer explizit abgewählte. So ändert das An-/Abwählen eines einzelnen
        Runs nie die Auswahl der anderen Labore.
        """
        if self.opt_result is None:
            return
        if self._opt_mode == 'all':
            self._show_all_labs_overview()
            return
        active = self._active()
        if not active:
            self.opt_result = None
            self._opt_mode = None
            self._set_status('Alle Labore sind abgewählt.', 'warn')
            self._update_ui_state()
            return
        prev_labs, _, _, min_n, target_n = self.opt_result
        params, _ = self._get_params()
        max_n = params[2] if params else 6

        masked_runs = set(self.masked_runs)
        pinned = set(self.forced_runs)
        for r in prev_labs:
            for rl in r.get('selected_runs', []):
                key = f"{r['lab']}-{rl}"
                if key not in masked_runs:
                    pinned.add(key)

        def worker():
            try:
                labs, cost, cov = optimize(active, min_n, target_n, max_n, masked_runs, pinned)
                self._call_soon(self._on_opt_done, labs, cost, cov, min_n, target_n, True)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._call_soon(self._set_status, f'Fehler bei der Neuberechnung: {e}', 'error')

        threading.Thread(target=worker, daemon=True).start()

    def _run_opt(self):
        if self._busy:
            return
        active = self._active()
        if not active:
            messagebox.showwarning('Keine Daten',
                'Es sind keine Labore aktiv.\nBitte PDFs hinzufügen oder Labore links anhaken.',
                parent=self)
            return
        params, err = self._get_params()
        if err:
            messagebox.showwarning('Ungültige Abdeckung', err, parent=self)
            return
        min_n, target_n, max_n = params
        self.nb.select(1)
        self.opt_btn.config(state='disabled')
        self.opt_status.set('Optimierung läuft …')
        self.config(cursor='watch')

        masked_runs = set(self.masked_runs)
        forced_runs = set(self.forced_runs)

        def worker():
            try:
                labs, cost, cov = optimize(active, min_n, target_n, max_n, masked_runs, forced_runs)
                self._call_soon(self._on_opt_done, labs, cost, cov, min_n, target_n, False)
            except Exception as e:
                msg = str(e)
                def fail(m=msg):
                    self.config(cursor='')
                    self.opt_btn.config(state='normal')
                    self.opt_status.set('Optimierung fehlgeschlagen')
                    messagebox.showerror('Fehler', m, parent=self)
                self._call_soon(fail)

        threading.Thread(target=worker, daemon=True).start()

    def _on_opt_done(self, labs, cost, cov, min_n, target_n, silent=False):
        self.config(cursor='')
        self.opt_btn.config(state='normal')
        if not labs or not cov:
            self.opt_status.set('Keine Lösung gefunden')
            self.opt_hint.set('Sind alle Labore oder Runs abgewählt?')
            return
        self.opt_result = (labs, cost, cov, min_n, target_n)
        self._opt_mode = 'opt'
        self._opt_stale = False
        self._mark_dirty()
        self._show_opt_status()
        self._render_opt_labs(labs, cost)
        self._refresh_opt_table()
        self._update_opt_hint()
        if not silent:
            self._set_status('Optimierung abgeschlossen. Runs links per Häkchen anpassen, '
                             'rechts Proben eintragen, dann exportieren.', 'ok')
        self._update_ui_state()

    def _show_opt_status(self):
        labs, cost, cov, min_n, target_n = self.opt_result
        total = len(cov)
        n_min = sum(1 for c in cov.values() if c >= min_n)
        n_tgt = sum(1 for c in cov.values() if c >= target_n)
        self.opt_status.set(
            f'{len(labs)} Labore  ·  {fmt_eur(cost)} pro Probe  ·  '
            f'{n_min}/{total} Analyten ≥ {min_n}×  ·  {n_tgt}/{total} ≥ {target_n}×')

    # ── Kosten + Probenrechner ────────────────────────────────
    def _lab_costs(self, lab_result):
        """(Kosten Probe, Kosten Referenz) eines Labors aus den gewählten Runs."""
        lab = lab_result['lab']
        orig = next((x for x in self.results if x['lab'] == lab), lab_result)
        runs_data = orig.get('runs', {})
        sel_runs  = lab_result.get('selected_runs', list(runs_data.keys()))
        c_probe = sum((runs_data.get(rl, {}).get('cost') or 0) for rl in sel_runs
                      if f"{lab}-{rl}" not in self.masked_runs)
        c_ref   = sum((runs_data.get(rl, {}).get('cost') or 0) for rl in sel_runs
                      if f"{lab}-{rl}" not in self.ref_masked_runs)
        return c_probe, c_ref

    def _render_opt_costs(self, labs, total_cost):
        """Kostentabelle + Referenz-Auswahl rechts im Opt-Tab."""
        self.opt_cost_frame.destroy()
        self.opt_cost_frame = tk.Frame(self.opt_cost_frame_container, bg=BG)
        self.opt_cost_frame.pack(fill='x')
        f = self.opt_cost_frame
        f.columnconfigure(0, weight=1)

        for col, h in enumerate(['', 'Einfach', 'Doppelt']):
            tk.Label(f, text=h, font=FONT_XS, fg=GRAY, bg=BG).grid(
                row=0, column=col, padx=(0,8) if col < 2 else 0, sticky='e' if col else 'w')
        tk.Frame(f, bg=BORDER, height=1).grid(row=1, column=0, columnspan=3, sticky='ew', pady=(0,2))

        row_idx = 2
        sum_probe = sum_ref = 0.0
        for r in labs:
            c_probe, c_ref = self._lab_costs(r)
            sum_probe += c_probe
            sum_ref   += c_ref
            tk.Label(f, text=r['lab'], font=FONT_SMB, fg=FG, bg=BG, anchor='w').grid(
                row=row_idx, column=0, columnspan=3, sticky='w', pady=(4,0))
            row_idx += 1
            for lbl, c in [('Probe', c_probe), ('Referenz', c_ref)]:
                tk.Label(f, text='   ' + lbl, font=FONT_XS, fg=GRAY, bg=BG).grid(
                    row=row_idx, column=0, sticky='w')
                tk.Label(f, text=fmt_eur(c) if c else '–', font=FONT_XS, fg=FG, bg=BG).grid(
                    row=row_idx, column=1, sticky='e', padx=(0,8))
                tk.Label(f, text=fmt_eur(c*2) if c else '–', font=FONT_XS, fg=FG, bg=BG).grid(
                    row=row_idx, column=2, sticky='e')
                row_idx += 1

        tk.Frame(f, bg=BORDER, height=1).grid(row=row_idx, column=0, columnspan=3,
                                               sticky='ew', pady=(4,2))
        row_idx += 1
        for lbl, c in [('Σ Probe', sum_probe), ('Σ Referenz', sum_ref)]:
            tk.Label(f, text=lbl, font=FONT_SMB, fg=FG, bg=BG).grid(row=row_idx, column=0, sticky='w')
            tk.Label(f, text=fmt_eur(c), font=FONT_SMB, fg=FG, bg=BG).grid(
                row=row_idx, column=1, sticky='e', padx=(0,8))
            tk.Label(f, text=fmt_eur(c*2), font=FONT_SMB, fg=FG, bg=BG).grid(
                row=row_idx, column=2, sticky='e')
            row_idx += 1

        # Referenz-Checkboxen
        for w in self.opt_ref_frame.winfo_children():
            w.destroy()
        l = tk.Label(self.opt_ref_frame, text='Referenzproben gehen an:', font=FONT_XS,
                     fg=GRAY, bg=BG)
        l.pack(anchor='w', pady=(8,2))
        grid = tk.Frame(self.opt_ref_frame, bg=BG)
        grid.pack(fill='x')
        for i, r in enumerate(labs):
            lab = r['lab']
            if lab not in self.opt_ref_lab_vars:
                self.opt_ref_lab_vars[lab] = tk.BooleanVar(value=True)
            tk.Checkbutton(grid, text=lab, variable=self.opt_ref_lab_vars[lab],
                           font=FONT_SM, bg=BG, activebackground=BG, cursor='hand2',
                           command=self._on_probe_changed).grid(
                row=i // 2, column=i % 2, sticky='w', padx=(0,10))

        self._calc_opt_probe()

    def _on_probe_changed(self):
        if self.opt_result is not None:
            self._mark_dirty()
        self._calc_opt_probe()
        self._rebuild_batch_fields()

    def _calc_opt_probe(self, total_cost=None, labs=None):
        lbl = self.opt_probe_lbl
        n  = _safe_int(self.opt_probe_var, 0)
        nr = _safe_int(self.opt_ref_var, 0)
        mt = max(1, _safe_int(self.opt_messtage_var, 1))
        if labs is None and self.opt_result:
            labs = self.opt_result[0]
        if not labs:
            lbl.config(text='', fg=FG)
            return
        if n == 0 and nr == 0:
            lbl.config(text='Anzahl Proben oder Referenzproben\neintragen, um die Kosten zu sehen.',
                       fg=GRAY)
            return

        cost_probe = cost_ref = 0.0
        for r in labs:
            lab = r['lab']
            orig = next((x for x in self.results if x['lab'] == lab), r)
            runs_data = orig.get('runs', {})
            sel_runs  = r.get('selected_runs', list(runs_data.keys()))
            ref_incl  = self.opt_ref_lab_vars.get(lab, tk.BooleanVar(value=True)).get()
            for rl in sel_runs:
                rc = runs_data.get(rl, {}).get('cost') or 0
                if f"{lab}-{rl}" not in self.masked_runs:
                    cost_probe += rc
                if ref_incl and f"{lab}-{rl}" not in self.ref_masked_runs:
                    cost_ref += rc

        lines = []
        if mt > 1:
            lines.append(f'für {mt} Messtage')
        if n:
            lines.append(f'Proben  einfach:  {fmt_eur(cost_probe*n*mt)}')
            lines.append(f'Proben  doppelt:  {fmt_eur(cost_probe*2*n*mt)}')
        if nr:
            lines.append(f'Referenz einfach:  {fmt_eur(cost_ref*nr*mt)}')
            lines.append(f'Referenz doppelt:  {fmt_eur(cost_ref*2*nr*mt)}')
        if n and nr:
            lines.append('')
            lines.append(f'Σ einfach:  {fmt_eur(cost_probe*n*mt + cost_ref*nr*mt)}')
            lines.append(f'Σ doppelt:  {fmt_eur(cost_probe*2*n*mt + cost_ref*2*nr*mt)}')
        lbl.config(text='\n'.join(lines), fg=FG)

    def _rebuild_batch_fields(self, total_cost=None, labs=None):
        """Baut Chargen-Felder passend zur Anzahl Proben/Referenzproben."""
        container = self._batch_container
        n_probe = _safe_int(self.opt_probe_var, 0)
        n_ref   = _safe_int(self.opt_ref_var, 0)
        if (n_probe, n_ref) == getattr(self, '_batch_shape', None) and container.winfo_children():
            return
        self._batch_shape = (n_probe, n_ref)

        old_probe = {k: v.get() for k, v in self.probe_batch_vars.items()}
        old_ref   = {k: v.get() for k, v in self.ref_batch_vars.items()}
        for w in container.winfo_children():
            w.destroy()
        self.probe_batch_vars = {}
        self.ref_batch_vars   = {}

        if n_probe == 0 and n_ref == 0:
            tk.Label(container, text='Erscheint, sobald Proben eingetragen sind.',
                     font=FONT_XS, fg=GRAY, bg=BG).pack(anchor='w')
            return

        def section(title, n, old_vals, store):
            if n == 0: return
            tk.Label(container, text=title, font=FONT_XS, fg=GRAY,
                     bg=BG).pack(anchor='w', pady=(6,1))
            for i in range(min(n, 200)):
                row = tk.Frame(container, bg=BG)
                row.pack(fill='x', pady=1)
                tk.Label(row, text=f'{i+1}.', font=FONT_XS, fg=GRAY, bg=BG,
                         width=3, anchor='e').pack(side='left', padx=(0,4))
                var = tk.StringVar(value=old_vals.get(i, ''))
                var.trace_add('write', lambda *_: self._mark_dirty())
                store[i] = var
                tk.Entry(row, textvariable=var, font=FONT_SM, bg=LIGHT, fg=FG,
                         relief='flat', bd=3).pack(side='left', fill='x', expand=True)

        section('Probe-Chargen', n_probe, old_probe, self.probe_batch_vars)
        section('Referenz-Chargen', n_ref, old_ref, self.ref_batch_vars)

    def _get_batches(self):
        """Liest aktuelle Chargen-Eingaben als dict für PDF-Export."""
        probe = {i: v.get().strip() for i, v in self.probe_batch_vars.items()}
        ref   = {i: v.get().strip() for i, v in self.ref_batch_vars.items()}
        return {'probe': probe, 'ref': ref,
                'ref_masked_runs': set(self.ref_masked_runs)}

    # ── Run-Auswahl je Labor ──────────────────────────────────
    def _set_run(self, key, probe=None, ref=None):
        """Run für Probe und/oder Referenz an- oder abwählen."""
        if probe is not None:
            if probe:
                self.masked_runs.discard(key)
                self.forced_runs.add(key)
            else:
                self.masked_runs.add(key)
                self.forced_runs.discard(key)
                self.fixed_runs.discard(key)
        if ref is not None:
            if ref:
                self.ref_masked_runs.discard(key)
            else:
                self.ref_masked_runs.add(key)
        self._mark_dirty()

    def _render_opt_labs(self, labs, total_cost):
        self.opt_lab_scroll.clear()
        frame = self.opt_lab_frame
        self._opt_row_vars = []   # Referenzen halten, sonst verlieren Checkboxen ihren Zustand
        opt_labs = {r['lab']: r for r in labs}

        # Gewählte Labore zuerst, dann die übrigen
        ordered = ([r for r in self.results if r['lab'] in opt_labs] +
                   [r for r in self.results if r['lab'] not in opt_labs])
        shown_other = False
        for r in ordered:
            lab = r['lab']
            lab_in_opt = lab in opt_labs
            lab_masked = lab in self.masked
            if not lab_in_opt and not shown_other:
                shown_other = True
                tk.Label(frame, text='Nicht eingeplant', font=FONT_XS, fg=GRAY,
                         bg=BG).pack(anchor='w', pady=(14,0))
                tk.Frame(frame, bg=BORDER, height=1).pack(fill='x', pady=(2,0))

            r_display = opt_labs.get(lab, r)
            sel_runs  = r_display.get('selected_runs', []) if lab_in_opt else []
            runs_data = r.get('runs', {})
            all_runs  = sorted(runs_data.keys())
            c_probe, c_ref = self._lab_costs(r_display) if lab_in_opt else (0, 0)

            hdr = tk.Frame(frame, bg=BG)
            hdr.pack(fill='x', pady=(8,1))
            av = tk.BooleanVar(value=not lab_masked)
            self._opt_row_vars.append(av)
            cb = tk.Checkbutton(hdr, text=lab, variable=av, font=FONT_SMB,
                                bg=BG, activebackground=BG, cursor='hand2',
                                fg=FG if not lab_masked else GRAY,
                                command=lambda l=lab: self._toggle_mask(l))
            cb.pack(side='left')
            Tooltip(cb, 'Labor berücksichtigen / nicht berücksichtigen')
            info = (f'{fmt_eur(c_probe)}' if lab_in_opt else
                    'deaktiviert' if lab_masked else 'nicht benötigt')
            tk.Label(hdr, text=info, font=FONT_XS, fg=GRAY, bg=BG).pack(side='right')

            if lab_masked or not runs_data:
                continue

            for rl in all_runs:
                rd  = runs_data.get(rl, {})
                rc  = rd.get('cost') or 0
                key = f"{lab}-{rl}"
                selected = rl in sel_runs
                probe_on = selected and key not in self.masked_runs
                ref_on   = probe_on and key not in self.ref_masked_runs
                bg = BG if selected else LIGHT

                sub = tk.Frame(frame, bg=bg)
                sub.pack(fill='x', padx=(18,0), pady=1)

                pv = tk.BooleanVar(value=probe_on)
                rv = tk.BooleanVar(value=ref_on)
                fv = tk.BooleanVar(value=key in self.fixed_runs)
                self._opt_row_vars += [pv, rv, fv]

                def on_probe(k=key, v=pv):
                    self._set_run(k, probe=v.get(), ref=v.get())
                    self._rerun_opt_after_mask()

                def on_ref(k=key, v=rv):
                    self._set_run(k, ref=v.get())
                    # nach dem Klick neu zeichnen (nicht innerhalb des Widget-Callbacks)
                    self.after_idle(lambda: self.opt_result and (
                        self._render_opt_labs(self.opt_result[0], self.opt_result[1]),
                        self._refresh_opt_table()))

                def on_fix(k=key, v=fv):
                    if v.get():
                        self.fixed_runs.add(k)
                        self.forced_runs.add(k)
                        self.masked_runs.discard(k)
                    else:
                        self.fixed_runs.discard(k)
                        self.forced_runs.discard(k)
                    self._mark_dirty()
                    self._rerun_opt_after_mask()

                tk.Checkbutton(sub, variable=pv, command=on_probe, bg=bg,
                               activebackground=bg, cursor='hand2', width=2).pack(side='left')
                ref_cb = tk.Checkbutton(sub, variable=rv, command=on_ref, bg=bg,
                                        activebackground=bg, cursor='hand2', width=2,
                                        state='normal' if probe_on else 'disabled')
                ref_cb.pack(side='left')

                fg = FG if probe_on else GRAY
                name = tk.Label(sub, text=f'Run {rl}', font=FONT_SM, bg=bg, fg=fg,
                                anchor='w', cursor='hand2')
                name.pack(side='left', padx=(4,0))
                name.bind('<Button-1>', lambda e, v=pv, f=on_probe: (v.set(not v.get()), f()))
                n_an = len(rd.get('analytes', []))
                tk.Label(sub, text=f'({n_an})', font=FONT_XS, bg=bg,
                         fg=GRAY).pack(side='left', padx=(4,0))

                fix_cb = tk.Checkbutton(sub, variable=fv, command=on_fix, bg=bg,
                                        activebackground=bg, cursor='hand2')
                fix_cb.pack(side='right')
                tk.Label(sub, text=fmt_eur(rc), font=FONT_XS, bg=bg, fg=fg).pack(side='right', padx=(0,6))

                tip = ', '.join(rd.get('analytes', [])) or 'keine Analyten'
                Tooltip(name, f'Run {rl} – {n_an} Analyten:\n{tip}')

        self._render_opt_costs(labs, total_cost)
        self._rebuild_batch_fields()

    def _opt_rightclick(self, event):
        """Rechtsklick in der Abdeckungstabelle."""
        if self._heading_menu(self.opt_tree, event):
            return
        row_id = self.opt_tree.identify_row(event.y)
        if not row_id or not self.opt_result:
            return
        analyte = self.opt_tree.item(row_id, 'values')[0]
        labs = self.opt_result[0]
        menu = tk.Menu(self, tearoff=0)
        added = False
        for r in labs:
            for rl in r.get('selected_runs', []):
                rd = r.get('runs', {}).get(rl, {})
                if not any(a.lower() == str(analyte).lower() for a in rd.get('analytes', [])):
                    continue
                key = f"{r['lab']}-{rl}"
                rc = rd.get('cost', 0) or 0
                on = key not in self.masked_runs
                label = f"{'Abwählen' if on else 'Wieder anwählen'}: {r['lab']} Run {rl} ({fmt_eur(rc)})"
                menu.add_command(label=label,
                    command=lambda k=key, on=on: (self._set_run(k, probe=not on, ref=not on),
                                                  self._rerun_opt_after_mask()))
                added = True
        if added:
            menu.tk_popup(event.x_root, event.y_root)

    def _toggle_run_mask(self, key, selected=True):
        """Kompatibilität: gewählten Run ab-/anwählen bzw. nicht gewählten erzwingen."""
        if selected:
            if key in self.masked_runs:
                self.masked_runs.discard(key)
            else:
                self.masked_runs.add(key)
        else:
            if key in self.forced_runs:
                self.forced_runs.discard(key)
            else:
                self.forced_runs.add(key)
        self._mark_dirty()
        self._rerun_opt_after_mask()

    # ══════════════════════════════════════════════════════════
    # Planung Speichern / Laden / Archivieren
    # ══════════════════════════════════════════════════════════
    def _state_to_dict(self):
        """Serialisiert den kompletten App-Zustand als dict."""
        opt = None
        if self.opt_result:
            labs, cost, cov, min_n, target_n = self.opt_result
            opt = {
                'labs': [{k: v for k, v in r.items() if k not in ('_result',)} for r in labs],
                'cost': cost,
                'cov':  cov,
                'min_n': min_n,
                'target_n': target_n,
                'mode': self._opt_mode,
            }
        return {
            'version':      3,
            'files':        self.files,
            'masked':       list(self.masked),
            'masked_runs':     list(self.masked_runs),
            'ref_masked_runs': list(self.ref_masked_runs),
            'forced_runs':     list(self.forced_runs),
            'fixed_runs':      list(self.fixed_runs),
            'lab_measure_count': dict(self.lab_measure_count),
            'lod_mode':     self.lod_mode.get(),
            'min_n':        _safe_int(self.min_n_var, 3),
            'target_n':     _safe_int(self.tgt_n_var, 5),
            'max_n':        _safe_int(self.max_n_var, 6),
            'opt_n_proben': _safe_int(self.opt_probe_var, 0),
            'opt_n_ref':    _safe_int(self.opt_ref_var, 0),
            'opt_messtage': _safe_int(self.opt_messtage_var, 1),
            'ref_labs':     {lab: v.get() for lab, v in self.opt_ref_lab_vars.items()},
            'batches_probe': {str(i): v.get() for i, v in self.probe_batch_vars.items()},
            'batches_ref':   {str(i): v.get() for i, v in self.ref_batch_vars.items()},
            'art_nrs':      dict(self._art_nrs),
            'last_export_meta': list(self._last_export_meta[:3]),
            'opt_result':   opt,
            'archive_dir':  self._archive_dir,
            'results_meta': [
                {'lab': r['lab'], 'filename': r['filename'],
                 'product': r.get('product',''),
                 'contact': r.get('contact', {})}
                for r in self.results
            ],
        }

    def _reset_state(self):
        self.files        = []
        self.results      = []
        self.masked       = set()
        self.masked_runs  = set()
        self.forced_runs  = set()
        self.fixed_runs   = set()
        self.ref_masked_runs = set()
        self.lab_measure_count = {}
        self.opt_result   = None
        self._opt_mode    = None
        self._opt_stale   = False
        self._planning_path = None
        self.probe_batch_vars = {}
        self.ref_batch_vars   = {}
        self.opt_ref_lab_vars = {}
        self._batch_shape = None
        self._art_nrs = {}
        self._last_export_meta = ('', '', '', {})
        self.opt_probe_var.set(0)
        self.opt_ref_var.set(0)
        self.opt_messtage_var.set(1)

        self.file_lb.delete(0, 'end')
        self.tree.delete(*self.tree.get_children())
        self.opt_tree.delete(*self.opt_tree.get_children())
        self.opt_lab_scroll.clear()
        self.opt_status.set('')
        self.opt_hint.set('')
        self._refresh_lab_list()

    def _state_from_dict(self, d, path=None):
        """Stellt App-Zustand aus dict wieder her (PDFs werden neu geparst)."""
        self._reset_state()
        self._planning_path = path
        self.files       = list(d.get('files', []))
        self.masked      = set(d.get('masked', []))
        self.masked_runs = set(d.get('masked_runs', []))
        self.forced_runs     = set(d.get('forced_runs', []))
        self.fixed_runs      = set(d.get('fixed_runs', []))
        self.ref_masked_runs = set(d.get('ref_masked_runs', []))
        self.lab_measure_count = dict(d.get('lab_measure_count', {}))
        self._archive_dir    = d.get('archive_dir') or self._archive_dir
        self._art_nrs        = dict(d.get('art_nrs', {}))
        lem = (list(d.get('last_export_meta') or []) + ['', '', ''])[:3]
        self._last_export_meta = (*lem, dict(self._art_nrs))
        self.lod_on_var.set(d.get('lod_mode') == 'mit')
        self.lod_mode.set('mit' if self.lod_on_var.get() else 'ohne')

        self.min_n_var.set(d.get('min_n', 3))
        self.tgt_n_var.set(d.get('target_n', 5))
        self.max_n_var.set(d.get('max_n', 6))

        missing = [p for p in self.files if not os.path.exists(p)]
        self.files = [p for p in self.files if os.path.exists(p)]
        for p in self.files:
            self.file_lb.insert('end', os.path.basename(p))
        if missing:
            messagebox.showwarning('Fehlende Dateien',
                'Folgende PDFs wurden nicht gefunden und werden nicht berücksichtigt:\n\n' +
                '\n'.join(os.path.basename(p) for p in missing), parent=self)

        d['_missing'] = bool(missing)
        self._mark_dirty(bool(missing))
        if self.files:
            self._parse_files(list(self.files), reset=True,
                              on_done=lambda: self._on_load_done(d))
        else:
            self._update_ui_state()

    def _on_load_done(self, d):
        self._refresh_lab_list()
        self._refresh_overview()

        for lab, val in (d.get('ref_labs') or {}).items():
            self.opt_ref_lab_vars[lab] = tk.BooleanVar(value=bool(val))
        self.probe_batch_vars = {int(k): tk.StringVar(value=v)
                                 for k, v in (d.get('batches_probe') or {}).items()}
        self.ref_batch_vars   = {int(k): tk.StringVar(value=v)
                                 for k, v in (d.get('batches_ref') or {}).items()}
        self._batch_shape = None

        opt = d.get('opt_result')
        if opt:
            try:
                labs = []
                for lr in opt['labs']:
                    orig = next((r for r in self.results if r['lab'] == lr['lab']), None)
                    if orig:
                        r2 = dict(orig)
                        r2['selected_runs'] = lr.get('selected_runs', [])
                        r2['selected_cost'] = lr.get('selected_cost', 0)
                        labs.append(r2)
                cov, min_n, target_n, cost = opt['cov'], opt['min_n'], opt['target_n'], opt['cost']
                self.opt_result = (labs, cost, cov, min_n, target_n)
                self._opt_mode = opt.get('mode') or ('opt' if cov else 'all')
                self.opt_probe_var.set(d.get('opt_n_proben', 0))
                self.opt_ref_var.set(d.get('opt_n_ref', 0))
                self.opt_messtage_var.set(d.get('opt_messtage', 1))
                self._render_opt_labs(labs, cost)
                self._refresh_opt_table()
                if self._opt_mode == 'opt':
                    self._show_opt_status()
                else:
                    self.opt_status.set(f'Alle {len(labs)} aktiven Labore · ohne Optimierung')
                self._update_opt_hint()
            except Exception as e:
                self.opt_result = None
                self.opt_status.set('Optimierung konnte nicht wiederhergestellt werden')
                self.opt_hint.set(str(e))

        # Laden selbst ist keine Änderung (außer es fehlten Dateien)
        self._mark_dirty(bool(d.get('_missing')))
        self._set_status(f'Planung geladen · {len(self.results)} Labore.', 'ok')
        self._update_ui_state()

    def _confirm_discard(self, action='fortfahren'):
        """Fragt bei ungespeicherten Änderungen nach. True = weitermachen."""
        if not self._dirty or not (self.results or self.files):
            return True
        ans = messagebox.askyesnocancel('Ungespeicherte Änderungen',
            f'Die aktuelle Planung hat ungespeicherte Änderungen.\n\n'
            f'Vorher speichern?', parent=self)
        if ans is None:
            return False
        if ans:
            return self._save_planning()
        return True

    def _new_planning(self):
        if self._busy or not self._confirm_discard():
            return
        self._reset_state()
        self._mark_dirty(False)
        self._set_status('Neue Planung. PDF-Dateien hinzufügen, um zu beginnen.')
        self.nb.select(0)
        self._update_ui_state()

    def _save_planning(self, save_as=False):
        import json
        if not self.results:
            self._set_status('Nichts zu speichern – zuerst PDFs laden.', 'warn')
            return False
        path = self._planning_path if not save_as else None
        if not path:
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension='.wz',
                filetypes=[('WZ-Planung','*.wz'), ('Alle','*.*')],
                initialfile=os.path.basename(self._planning_path or 'Planung.wz'))
        if not path:
            return False
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._state_to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror('Speichern fehlgeschlagen', str(e), parent=self)
            return False
        self._planning_path = path
        self._mark_dirty(False)
        self._set_status(f'Gespeichert: {os.path.basename(path)}', 'ok')
        return True

    def _load_planning(self):
        import json
        if self._busy or not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            parent=self, filetypes=[('WZ-Planung','*.wz'), ('Alle','*.*')])
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
        except Exception as e:
            messagebox.showerror('Öffnen fehlgeschlagen',
                f'Die Datei konnte nicht gelesen werden:\n{e}', parent=self)
            return
        self._state_from_dict(d, path)

    def _choose_archive_dir(self):
        d = filedialog.askdirectory(parent=self, title='Archiv-Ordner wählen',
                                    initialdir=self._archive_dir or None)
        if d:
            self._archive_dir = d
            self._mark_dirty()
            self._set_status(f'Archiv-Ordner: {d}', 'ok')
        return d

    def _export_counts(self):
        mt = max(1, _safe_int(self.opt_messtage_var, 1))
        return _safe_int(self.opt_probe_var, 0) * mt, _safe_int(self.opt_ref_var, 0) * mt

    def _default_stem(self, labs, rv, product):
        date_str  = datetime.date.today().strftime('%d.%m.%Y')
        rv_part   = f"RV_{rv}_" if rv else ''
        prod_part = re.sub(r'[^\w\-]', '_', product)[:30] + '_' if product else ''
        names     = [r['lab'] for r in labs]
        lab_codes = '_'.join(names[:8])
        if len(names) > 8:
            lab_codes += f'_+{len(names)-8}weitere'
        return f"{rv_part}WZ-Planung_{prod_part}{lab_codes}_{date_str}"

    def _archive_planning(self):
        """Speichert Planung als .wz + exportiert PDF in den Archiv-Ordner."""
        import json
        if not self.opt_result:
            self._set_status('Zuerst optimieren oder „Alle Labore übernehmen“.', 'warn')
            return
        arch_dir = self._archive_dir
        if not arch_dir or not os.path.isdir(arch_dir):
            arch_dir = self._choose_archive_dir()
            if not arch_dir:
                return

        labs, cost, cov, min_n, target_n = self.opt_result
        meta = self._ask_export_meta(labs, action=f'Archivieren nach\n{arch_dir}')
        if meta is None:
            return
        rv, product, comment, art_nrs = meta
        stem     = self._default_stem(labs, rv, product)
        pdf_path = os.path.join(arch_dir, stem + '.pdf')
        wz_path  = os.path.join(arch_dir, stem + '.wz')
        if os.path.exists(pdf_path) and not messagebox.askyesno('Datei existiert',
                f'{os.path.basename(pdf_path)} existiert bereits.\nÜberschreiben?', parent=self):
            return
        n_proben, n_ref = self._export_counts()
        try:
            self.config(cursor='watch'); self.update_idletasks()
            self._build_pdf(pdf_path, labs, cov,
                            min_n, target_n, n_proben=n_proben, n_ref=n_ref,
                            ref_lab_vars=self.opt_ref_lab_vars, comment=comment,
                            batches=self._get_batches(), rv=rv, product=product,
                            art_nrs=art_nrs)
            self._planning_path = wz_path
            with open(wz_path, 'w', encoding='utf-8') as f:
                json.dump(self._state_to_dict(), f, ensure_ascii=False, indent=2)
            self._mark_dirty(False)
            self._toast(f'Archiviert: {os.path.basename(pdf_path)}', open_path=pdf_path)
        except Exception as e:
            messagebox.showerror('Archivieren fehlgeschlagen', str(e), parent=self)
        finally:
            self.config(cursor='')

    # ── Meldungen / Dialoge ───────────────────────────────────
    def _toast(self, message, duration=5000, open_path=None):
        """Kurze Erfolgsmeldung unten rechts – blockiert die Arbeit nicht."""
        dlg = tk.Toplevel(self)
        dlg.overrideredirect(True)
        dlg.attributes('-topmost', True)
        dlg.configure(bg=OK_FG)
        inner = tk.Frame(dlg, bg=OK_FG, padx=16, pady=12)
        inner.pack()
        tk.Label(inner, text='✓  ' + message, font=FONT_SM, bg=OK_FG, fg='white',
                 wraplength=360, justify='left').pack(side='left')
        if open_path:
            def _open():
                try: _open_file(open_path)
                except Exception as e: messagebox.showerror('Fehler', str(e), parent=self)
                dlg.destroy()
            tk.Button(inner, text='Öffnen', font=FONT_SMB, bg='white', fg=OK_FG,
                      relief='flat', padx=10, pady=2, cursor='hand2', bd=0,
                      command=_open).pack(side='left', padx=(12,0))
        tk.Button(inner, text='✕', font=FONT_SM, bg=OK_FG, fg='white', relief='flat',
                  bd=0, cursor='hand2', activebackground=OK_FG,
                  command=dlg.destroy).pack(side='left', padx=(8,0))
        dlg.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width()  - dlg.winfo_reqwidth()  - 24
        y = self.winfo_rooty() + self.winfo_height() - dlg.winfo_reqheight() - 48
        dlg.geometry(f'+{x}+{y}')
        dlg.after(duration, lambda: dlg.winfo_exists() and dlg.destroy())
        self._set_status(message, 'ok')

    def _ask_export_meta(self, results, action='PDF exportieren'):
        """Dialog für RV-Nummer, Produkt, Kommentar und Artikelnummern.
        Gibt (rv, product, comment, art_nrs) zurück oder None bei Abbruch."""
        products = [r.get('product','') for r in results if r.get('product')]
        last_rv, last_prod, last_comment = self._last_export_meta[:3]
        default_product = last_prod or (max(set(products), key=products.count) if products else '')

        dlg = tk.Toplevel(self)
        dlg.title('Angaben für den Export')
        dlg.transient(self)
        dlg.resizable(True, True)
        dlg.configure(bg=BG)
        dlg.minsize(460, 420)
        self.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width()  // 2 - 240
        y = self.winfo_rooty() + self.winfo_height() // 2 - 280
        dlg.geometry(f'480x560+{max(0,x)}+{max(0,y)}')
        dlg.grab_set()

        result = [None]
        art_entries = {}

        def _ok(*_):
            art_nrs = {lab: e.get().strip() for lab, e in art_entries.items()}
            result[0] = (rv_entry.get().strip(), prod_entry.get().strip(),
                         txt.get('1.0', 'end').strip(), art_nrs)
            dlg.destroy()

        dlg.bind('<Escape>', lambda e: dlg.destroy())
        dlg.bind('<Control-Return>', _ok)

        tk.Frame(dlg, bg=BORDER, height=1).pack(side='bottom', fill='x')
        btn_row = tk.Frame(dlg, bg=LIGHT, padx=16, pady=10)
        btn_row.pack(side='bottom', fill='x')
        tk.Label(btn_row, text='Strg+Enter = bestätigen · Esc = abbrechen',
                 font=FONT_XS, fg=GRAY, bg=LIGHT).pack(side='left')
        self._button(btn_row, 'Abbrechen', dlg.destroy, primary=False).pack(side='right', padx=(8,0))
        ok_label = 'Archivieren' if action.startswith('Archiv') else 'Weiter …'
        self._button(btn_row, ok_label, _ok, primary=True).pack(side='right')

        sf = ScrollFrame(dlg, width=440, padx=20, pady=16)
        sf.pack(fill='both', expand=True)
        form = sf.inner

        tk.Label(form, text='Angaben für den Export', font=FONT_H, bg=BG, fg=FG).pack(anchor='w')
        tk.Label(form, text=action, font=FONT_XS, bg=BG, fg=GRAY, justify='left').pack(anchor='w', pady=(0,12))

        def labeled_entry(label, default='', hint=''):
            tk.Label(form, text=label, font=FONT_SMB, fg=FG, bg=BG).pack(anchor='w', pady=(0,2))
            e = tk.Entry(form, font=FONT_SM, bg=LIGHT, fg=FG, relief='flat', bd=5)
            e.pack(fill='x', pady=(0,2))
            if default:
                e.insert(0, default)
            if hint:
                tk.Label(form, text=hint, font=FONT_XS, fg=GRAY, bg=BG).pack(anchor='w')
            tk.Frame(form, bg=BG, height=8).pack()
            return e

        rv_entry   = labeled_entry('RV-Nummer', last_rv, 'z. B. 25-26 – wird Teil des Dateinamens')
        prod_entry = labeled_entry('Produkt', default_product,
                                   'aus den PDFs übernommen – bei Bedarf anpassen')

        tk.Label(form, text='Kommentar / Notizen', font=FONT_SMB, fg=FG, bg=BG).pack(anchor='w', pady=(0,2))
        txt_frame = tk.Frame(form, bg=BORDER, padx=1, pady=1)
        txt_frame.pack(fill='x', pady=(0,12))
        txt = tk.Text(txt_frame, font=FONT_SM, bg=BG, fg=FG, relief='flat', bd=0,
                      wrap='word', height=3, padx=6, pady=4)
        txt.pack(fill='x')
        if last_comment:
            txt.insert('1.0', last_comment)

        tk.Frame(form, bg=BORDER, height=1).pack(fill='x', pady=(4,8))
        tk.Label(form, text='Artikelnummern (für SelectLine)', font=FONT_SMB,
                 fg=FG, bg=BG).pack(anchor='w')
        tk.Label(form, text='optional – werden für den nächsten Export gemerkt',
                 font=FONT_XS, fg=GRAY, bg=BG).pack(anchor='w', pady=(0,6))
        for r in results:
            lab = r['lab']
            row = tk.Frame(form, bg=BG)
            row.pack(fill='x', pady=2)
            tk.Label(row, text=lab, font=FONT_SM, fg=FG, bg=BG,
                     width=10, anchor='w').pack(side='left')
            e = tk.Entry(row, font=FONT_SM, bg=LIGHT, fg=FG, relief='flat', bd=4, width=20)
            if self._art_nrs.get(lab):
                e.insert(0, self._art_nrs[lab])
            e.pack(side='left', fill='x', expand=True)
            art_entries[lab] = e

        rv_entry.focus_set()
        self.wait_window(dlg)
        if result[0]:
            self._art_nrs.update(result[0][3])
            self._last_export_meta = result[0]
            self._mark_dirty()
        return result[0]

    # ── PDF Export ────────────────────────────────────────────
    def _export_overview(self):
        self._export_opt()

    def _preview_opt(self):
        """Erstellt das PDF in einem temporären Ordner und öffnet es."""
        if not self.opt_result:
            return
        labs, cost, cov, min_n, target_n = self.opt_result
        import tempfile
        rv, product, comment, art_nrs = self._last_export_meta
        n_proben, n_ref = self._export_counts()
        try:
            self.config(cursor='watch'); self.update_idletasks()
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', prefix='WZ_Vorschau_', delete=False)
            tmp.close()
            self._build_pdf(tmp.name, labs, cov,
                            min_n, target_n, n_proben=n_proben, n_ref=n_ref,
                            ref_lab_vars=self.opt_ref_lab_vars, comment=comment,
                            batches=self._get_batches(), rv=rv, product=product,
                            art_nrs=art_nrs or self._art_nrs)
            _open_file(tmp.name)
            self._set_status('Vorschau geöffnet.', 'ok')
        except Exception as e:
            import traceback; traceback.print_exc()
            messagebox.showerror('Vorschau fehlgeschlagen', str(e), parent=self)
        finally:
            self.config(cursor='')

    def _export_opt(self):
        if not self.opt_result:
            self._set_status('Zuerst optimieren oder „Alle Labore übernehmen“.', 'warn')
            return
        labs, cost, cov, min_n, target_n = self.opt_result
        meta = self._ask_export_meta(labs)
        if meta is None:
            return
        rv, product, comment, art_nrs = meta
        n_proben, n_ref = self._export_counts()
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.pdf',
            filetypes=[('PDF','*.pdf')], initialfile=self._default_stem(labs, rv, product) + '.pdf')
        if not path:
            return
        try:
            self.config(cursor='watch'); self.update_idletasks()
            self._build_pdf(path, labs, cov,
                            min_n, target_n, n_proben=n_proben, n_ref=n_ref,
                            ref_lab_vars=self.opt_ref_lab_vars, comment=comment,
                            batches=self._get_batches(), rv=rv, product=product,
                            art_nrs=art_nrs)
            self._toast(f'PDF gespeichert: {os.path.basename(path)}', open_path=path)
        except Exception as e:
            import traceback; traceback.print_exc()
            messagebox.showerror('Export fehlgeschlagen', str(e), parent=self)
        finally:
            self.config(cursor='')

    def _on_close(self):
        if self._busy:
            if not messagebox.askyesno('Beenden', 'Es werden gerade PDFs eingelesen.\nTrotzdem beenden?',
                                       parent=self):
                return
        elif not self._confirm_discard():
            return
        self.destroy()

    def _build_pdf(self, path, results, coverage, min_n, target_n,
                   n_proben=0, n_ref=0, ref_lab_vars=None, comment='',
                   batches=None, rv='', product='', art_nrs=None):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                        Paragraph, Spacer, KeepTogether,
                                        PageBreak)
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm

        is_opt  = coverage is not None
        W       = 167 * mm   # usable width (A4 - 30mm margins)
        GRAY7   = colors.HexColor('#888888')
        LGRAY   = colors.HexColor('#f0f0f0')
        STRIPE  = colors.HexColor('#f8f8f8')
        GREEN   = colors.HexColor('#e8f5e9')
        YELLOW  = colors.HexColor('#fff9e6')
        RED     = colors.HexColor('#fdecea')

        doc = SimpleDocTemplate(path, pagesize=A4,
            leftMargin=15*mm, rightMargin=15*mm,
            topMargin=15*mm, bottomMargin=15*mm)

        def P(t, **kw):
            return Paragraph(t, ParagraphStyle('x', **kw))
        def SP(h=4):
            return Spacer(1, h * mm)
        def HDR(txt):
            return P(txt, fontName='Helvetica-Bold', fontSize=9, spaceAfter=3)
        def tbl_style(extra=None):
            base = [
                ('FONTNAME',      (0,0),(-1,0),  'Helvetica-Bold'),
                ('FONTSIZE',      (0,0),(-1,-1), 8),
                ('LINEBELOW',     (0,0),(-1,0),  0.5, colors.black),
                ('TOPPADDING',    (0,0),(-1,-1), 2),
                ('BOTTOMPADDING', (0,0),(-1,-1), 2),
                ('LEFTPADDING',   (0,0),(-1,-1), 4),
                ('RIGHTPADDING',  (0,0),(-1,-1), 4),
                ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, STRIPE]),
            ]
            return base + (extra or [])

        story = []

        # ── Header ───────────────────────────────────────────────────────
        story += [
            P('Planung der Wertezuweisung', fontName='Helvetica-Bold',
              fontSize=13, spaceAfter=2),
        ]
        if product:
            story.append(P(product, fontName='Helvetica-Bold', fontSize=10,
                           textColor=GRAY7, spaceAfter=1))
        meta_parts = ['medichem diagnostica', datetime.date.today().strftime('%d.%m.%Y')]
        if rv:
            meta_parts.insert(0, f'RV {rv}')
        story.append(P(' · '.join(meta_parts),
                       fontName='Helvetica', fontSize=8,
                       textColor=GRAY7, spaceAfter=8))

        # ── Kommentar ────────────────────────────────────────────────────
        if comment:
            cb = Table([[P(comment.replace('\n','<br/>'), fontName='Helvetica',
                           fontSize=8, leading=12)]],
                       colWidths=[W])
            cb.setStyle(TableStyle([
                ('BOX',          (0,0),(-1,-1), 0.5, colors.HexColor('#cccccc')),
                ('BACKGROUND',   (0,0),(-1,-1), colors.HexColor('#fafafa')),
                ('TOPPADDING',   (0,0),(-1,-1), 5),
                ('BOTTOMPADDING',(0,0),(-1,-1), 5),
                ('LEFTPADDING',  (0,0),(-1,-1), 7),
                ('RIGHTPADDING', (0,0),(-1,-1), 7),
            ]))
            story += [HDR('Kommentar'), cb, SP(6)]

        # ── Analytabdeckung ──────────────────────────────────────────────
        labs  = [r['lab'] for r in results]
        # Alle Analyten inkl. nicht-validierter
        all_a = sorted(
            {a for r in results for a in r.get('all_analytes', r['analytes'])},
            key=sort_key)

        n_w = 10*mm
        a_w = 50*mm
        l_w = max(10*mm, min(28*mm, (W - a_w - n_w) / max(len(labs), 1)))
        col_w = [a_w] + [l_w]*len(labs) + [n_w]

        tdata, tags = [['Analyt'] + labs + ['n']], [None]
        cur_g = None
        for analyte in all_a:
            grp = get_group(analyte)
            if grp != cur_g:
                cur_g = grp
                tdata.append([grp.upper()] + ['']*(len(labs)+1))
                tags.append('group')
            row  = [analyte]
            cnt  = 0
            for r in results:
                lab      = r['lab']
                runs_d   = r.get('runs', {})
                sel_runs = r.get('selected_runs', list(runs_d.keys()))
                mcount   = self.lab_measure_count.get(lab, 1)
                mprefix  = f'{mcount}' if mcount != 1 else ''
                if is_opt and sel_runs and runs_d:
                    active_runs = [rl for rl in sel_runs
                                   if f"{lab}-{rl}" not in self.masked_runs]
                    has_it = any(
                        analyte.lower() in [a.lower() for a in runs_d.get(rl, {}).get('analytes', [])]
                        for rl in active_runs
                    )
                else:
                    has_it = analyte in r['analytes']
                if has_it:
                    cnt += mcount
                row.append((mprefix + '✓') if has_it else '')
            row.append(str(cnt) if cnt else '')
            if is_opt and coverage:
                c = cnt
                tags.append('ok5' if c >= target_n else ('ok3' if c >= min_n else 'low'))
            else:
                tags.append(None)
            tdata.append(row)

        atbl = Table(tdata, colWidths=col_w)
        ats  = tbl_style([
            ('ALIGN',   (1,0),(-1,-1), 'CENTER'),
            ('ALIGN',   (0,0),(0,-1),  'LEFT'),
            ('FONTSIZE',(0,0),(-1,-1), 7),
        ])
        for i, tag in enumerate(tags[1:], 1):
            if tag == 'group':
                ats += [('FONTNAME',  (0,i),(0,i),  'Helvetica-Bold'),
                        ('FONTSIZE',  (0,i),(0,i),  6),
                        ('TEXTCOLOR', (0,i),(0,i),  GRAY7),
                        ('BACKGROUND',(0,i),(-1,i), LGRAY),
                        ('SPAN',      (0,i),(-1,i))]
            elif tag == 'ok5':
                ats.append(('BACKGROUND',(0,i),(-1,i), GREEN))
            elif tag == 'ok3':
                ats.append(('BACKGROUND',(0,i),(-1,i), YELLOW))
            elif tag == 'low':
                ats.append(('BACKGROUND',(0,i),(-1,i), RED))
        atbl.setStyle(TableStyle(ats))
        story += [HDR('Analytabdeckung'), atbl]

        # Legende
        if is_opt:
            leg = Table([['■', f'n ≥ {target_n}  (Ziel)'],
                         ['■', f'n ≥ {min_n}  (Minimum)'],
                         ['■', f'n < {min_n}  (unter Minimum)']],
                        colWidths=[8*mm, 70*mm])
            leg.setStyle(TableStyle([
                ('FONTSIZE',      (0,0),(-1,-1), 7),
                ('TOPPADDING',    (0,0),(-1,-1), 1),
                ('BOTTOMPADDING', (0,0),(-1,-1), 1),
                ('BACKGROUND',    (0,0),(0,0),   GREEN),
                ('BACKGROUND',    (0,1),(0,1),   YELLOW),
                ('BACKGROUND',    (0,2),(0,2),   RED),
            ]))
            story += [SP(3), leg]

        # ── Kosten pro Probe ─────────────────────────────────────────────
        story += [SP(6)]
        # Pro Labor eine eigene kleine Tabelle
        lab_tables = []
        total = 0.0
        col_w = [22*mm, 14*mm, 58*mm, 34*mm, 34*mm]

        for r in results:
            lab      = r['lab']
            runs_d   = r.get('runs', {})
            sel_runs = r.get('selected_runs', [])
            lab_cost = 0.0

            ldata = [['Run', '1 Analyse', 'Doppelt']]
            if is_opt and sel_runs:
                for rl in sel_runs:
                    key    = f"{lab}-{rl}"
                    masked = key in self.masked_runs
                    rc     = runs_d.get(rl, {}).get('cost') or 0
                    c1     = '–' if masked else fmt_eur(rc)
                    c2     = '–' if masked else fmt_eur(rc*2)
                    ldata.append([f'Run {rl}', c1, c2])
                    if not masked: lab_cost += rc
                ldata.append(['gesamt:', fmt_eur(lab_cost), fmt_eur(lab_cost*2)])
            else:
                lab_cost = r.get('cost') or 0
                ldata.append(['–', fmt_eur(lab_cost) if lab_cost else '–',
                              fmt_eur(lab_cost*2) if lab_cost else '–'])

            total += lab_cost

            lts = [
                ('FONTNAME',      (0,0),(-1,0),  'Helvetica-Bold'),
                ('FONTSIZE',      (0,0),(-1,-1), 7),
                ('LINEBELOW',     (0,0),(-1,0),  0.4, colors.black),
                ('TOPPADDING',    (0,0),(-1,-1), 1),
                ('BOTTOMPADDING', (0,0),(-1,-1), 1),
                ('ALIGN',         (1,0),(-1,-1), 'RIGHT'),
                ('ALIGN',         (0,0),(0,-1),  'LEFT'),
                ('ROWBACKGROUNDS',(0,1),(-1,-2), [colors.white, colors.HexColor('#f8f8f8')]),
                ('FONTNAME',      (0,-1),(-1,-1),'Helvetica-Oblique'),
                ('FONTSIZE',      (0,-1),(-1,-1), 7),
                ('LINEABOVE',     (0,-1),(-1,-1), 0.3, GRAY7),
                ('BACKGROUND',    (0,-1),(-1,-1), colors.HexColor('#f0f0f0')),
            ]
            ltbl = Table(ldata, colWidths=[40*mm, 65*mm, 55*mm], hAlign='LEFT')
            ltbl.setStyle(TableStyle(lts))

            lab_tables.append(KeepTogether([
                SP(4),
                P(f'<b>{lab}</b>', fontName='Helvetica-Bold', fontSize=9, spaceAfter=2),
                ltbl,
                SP(1),
            ]))
        gtbl = Table([['GESAMT', fmt_eur(total), fmt_eur(total*2)]],
                     colWidths=[40*mm, 65*mm, 55*mm], hAlign='LEFT')
        gtbl.setStyle(TableStyle([
            ('FONTNAME',  (0,0),(-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE',  (0,0),(-1,-1), 8),
            ('LINEABOVE', (0,0),(-1,0),  0.8, colors.black),
            ('ALIGN',     (1,0),(-1,-1), 'RIGHT'),
            ('ALIGN',     (0,0),(0,-1),  'LEFT'),
            ('TOPPADDING',(0,0),(-1,-1), 3),
        ]))

        story += [SP(6), HDR('Kostenplanung')] + lab_tables + [gtbl]

        # ── Probenplanung ────────────────────────────────────────────────
        if n_proben or n_ref or batches:
            ref_masked  = (batches or {}).get('ref_masked_runs', set())
            sec = [HDR('Probenplanung')]

            # Chargen-Tabelle
            p_ch = [c for c in ((batches or {}).get('probe', {}) or {}).values() if c]
            r_ch = [c for c in ((batches or {}).get('ref',   {}) or {}).values() if c]
            if p_ch or r_ch:
                n_rows = max(len(p_ch), len(r_ch))
                bdata  = [['#', 'Probe-Charge', 'Referenz-Charge']]
                for i in range(n_rows):
                    bdata.append([str(i+1),
                                  p_ch[i] if i < len(p_ch) else '–',
                                  r_ch[i] if i < len(r_ch) else '–'])
                btbl = Table(bdata, colWidths=[10*mm, 78*mm, 79*mm])
                btbl.setStyle(TableStyle(tbl_style([
                    ('ALIGN', (0,0),(0,-1), 'CENTER'),
                    ('ALIGN', (1,0),(-1,-1),'LEFT'),
                ])))
                sec += [btbl, SP(4)]

            # Pro Labor
            if n_proben or n_ref:
                for r in results:
                    lab      = r['lab']
                    orig     = next((x for x in results if x['lab'] == lab), r)
                    runs_d   = orig.get('runs', {})
                    sel_runs = r.get('selected_runs', list(runs_d.keys()))
                    ref_incl = ref_lab_vars.get(
                        lab, type('_',(),{'get':lambda s:True})()).get() \
                        if ref_lab_vars else True

                    c_probe = sum((runs_d.get(rl,{}).get('cost') or 0)
                                  for rl in sel_runs
                                  if f"{lab}-{rl}" not in self.masked_runs)
                    skipped_probe = [rl for rl in sel_runs if f"{lab}-{rl}" in self.masked_runs]
                    skipped = [rl for rl in sel_runs if f"{lab}-{rl}" in ref_masked]
                    c_ref   = sum((runs_d.get(rl,{}).get('cost') or 0)
                                  for rl in sel_runs
                                  if f"{lab}-{rl}" not in ref_masked) \
                              if ref_incl else 0.0

                    lines = [f'<b>{lab}</b>']
                    if n_proben:
                        lines.append(
                            f'{n_proben} Probe{"n" if n_proben>1 else ""} '
                            f'à Doppelbestimmung: <b>{fmt_eur(c_probe*2*n_proben)}</b>')
                        if skipped_probe:
                            lines.append(
                                f'<font color="#888888">* ohne Run '
                                f'{", ".join(skipped_probe)}</font>')
                    if n_ref and ref_incl:
                        lines.append(
                            f'{n_ref} Referenz{"en" if n_ref>1 else ""} '
                            f'à Doppelbestimmung: <b>{fmt_eur(c_ref*2*n_ref)}</b>')
                        if skipped:
                            lines.append(
                                f'<font color="#888888">* ohne Run '
                                f'{", ".join(skipped)}</font>')
                    sec.append(P('<br/>'.join(lines), fontName='Helvetica',
                                 fontSize=8, leading=13, spaceAfter=8))

            story += [SP(6), KeepTogether(sec)]

        # ── Für SelectLine ───────────────────────────────────────────────
        if (n_proben or n_ref) and results:
            art_nrs = art_nrs or {}
            ref_masked_sl = (batches or {}).get('ref_masked_runs', set())
            sl_rows  = []
            sl_total = 0.0
            sl_total_analysen = 0
            for r in results:
                lab      = r['lab']
                orig     = next((x for x in results if x['lab'] == lab), r)
                runs_d   = orig.get('runs', {})
                sel_runs = r.get('selected_runs', list(runs_d.keys()))
                ref_incl = ref_lab_vars.get(
                    lab, type('_',(),{'get':lambda s:True})()).get() \
                    if ref_lab_vars else True
                c_probe  = sum((runs_d.get(rl,{}).get('cost') or 0)
                               for rl in sel_runs
                               if f"{lab}-{rl}" not in self.masked_runs)
                c_ref    = sum((runs_d.get(rl,{}).get('cost') or 0)
                               for rl in sel_runs
                               if f"{lab}-{rl}" not in ref_masked_sl) \
                           if ref_incl else 0.0
                lab_sum  = c_probe*2*n_proben + c_ref*2*n_ref
                sl_total += lab_sum
                art      = art_nrs.get(lab, '')

                # Analysen-Formel: n Probe(n) [+ n Referenz(en)] × Doppelbestimmung = X Analysen
                _parts = []
                _n_analysen = 0
                if n_proben and c_probe:
                    _parts.append(f"{n_proben} Probe{'n' if n_proben != 1 else ''}")
                    _n_analysen += n_proben * 2
                if n_ref and ref_incl and c_ref:
                    _parts.append(f"{n_ref} Referenz{'en' if n_ref != 1 else ''}")
                    _n_analysen += n_ref * 2
                if _parts:
                    analysen_txt = ' + '.join(_parts) + f' × Doppelbestimmung = {_n_analysen} Analysen'
                else:
                    analysen_txt = '–'
                sl_total_analysen += _n_analysen

                sl_rows.append([lab, art, analysen_txt, fmt_eur(lab_sum)])
            sl_rows.append(['GESAMT', '', f'{sl_total_analysen} Analysen', fmt_eur(sl_total)])

            sltbl = Table([['Labor', 'Artikelnummer', 'Analysen', 'Betrag']] + sl_rows,
                          colWidths=[22*mm, 35*mm, 62*mm, 48*mm])
            slts  = tbl_style([
                ('ALIGN',   (3,0),(3,-1),  'RIGHT'),
                ('ALIGN',   (0,0),(0,-1),  'LEFT'),
                ('ALIGN',   (2,0),(2,-1),  'LEFT'),
                ('FONTSIZE',(0,0),(-1,-1), 7),
                ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
                ('LINEABOVE',(0,-1),(-1,-1),0.5, colors.black),
            ])
            sltbl.setStyle(TableStyle(slts))
            story += [SP(6), KeepTogether([HDR('Für SelectLine'), sltbl])]

        # ── Kontakte ─────────────────────────────────────────────────────
        if any(r.get('contact') for r in results):
            PS  = lambda t, **kw: Paragraph(t, ParagraphStyle('c', **kw))
            hdr_s = dict(fontName='Helvetica-Bold', fontSize=7, textColor=GRAY7, leading=10)
            val_s = dict(fontName='Helvetica',      fontSize=8, leading=11)
            em_s  = dict(fontName='Helvetica',      fontSize=8, leading=11,
                         textColor=colors.HexColor('#1a5fa8'))

            cdata = [[PS('Kürzel',**hdr_s), PS('Labor',**hdr_s), PS('Ansprechpartner',**hdr_s), PS('E-Mail',**hdr_s)]]
            for r in results:
                ct = r.get('contact') or {}
                lab_name = ct.get('lab_name') or r['lab']
                addr     = ct.get('address','')
                lab_cell = PS(
                    f"<b>{lab_name}</b><br/>"
                    f"<font size='7' color='#888888'>{addr}</font>"
                    if addr else f"<b>{lab_name}</b>",
                    fontName='Helvetica', fontSize=8, leading=11)
                cdata.append([PS(r['lab'], **val_s),
                               lab_cell,
                               PS(ct.get('person') or '–', **val_s),
                               PS(ct.get('email')  or '–', **em_s)])

            ctbl = Table(cdata, colWidths=[18*mm, 50*mm, 40*mm, 59*mm])
            ctbl.setStyle(TableStyle([
                ('LINEBELOW',    (0,0),(-1,0),  0.5, colors.HexColor('#cccccc')),
                ('TOPPADDING',   (0,0),(-1,-1), 4),
                ('BOTTOMPADDING',(0,0),(-1,-1), 4),
                ('LEFTPADDING',  (0,0),(-1,-1), 4),
                ('RIGHTPADDING', (0,0),(-1,-1), 4),
                ('VALIGN',       (0,0),(-1,-1), 'TOP'),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, STRIPE]),
                ('BOX',          (0,0),(-1,-1), 0.5, colors.HexColor('#e0e0e0')),
                ('LINEBELOW',    (0,1),(-1,-2), 0.3, colors.HexColor('#eeeeee')),
            ]))
            story += [SP(6), KeepTogether([HDR('Kontakte'), ctbl])]

        # ── Versandetails (ausfüllbare Seite) ───────────────────────────
        from reportlab.platypus import Flowable
        _res_v  = list(results)
        _cols_v = colors
        _pw_v, _ph_v = doc.pagesize
        _m_v = 15 * mm

        class _VersandDraw(Flowable):
            def __init__(self):
                super().__init__()
                self.width  = 0
                self.height = 0
            def wrap(self, aw, ah):
                return (0, 0)
            def drawOn(self, canvas, x, y, _sW=0):
                c   = canvas
                acf = c.acroForm
                m   = _m_v
                uw  = _pw_v - 2 * m
                yy  = _ph_v - m - 14*mm
                BOX = 8
                GAP = 3

                c.setFillColorRGB(0, 0, 0)
                c.setFont('Helvetica-Bold', 14)
                c.drawString(m, yy, 'Versandetails')
                yy -= 14*mm

                STATUS = ['Freigabe angefragt', 'Freigegeben', 'Labor angefragt', 'Zusage Labor', 'Versendet']
                col_w  = uw / len(STATUS)

                for r in _res_v:
                    if yy < m + 50*mm:
                        c.showPage()
                        yy = _ph_v - m - 14*mm

                    lab      = r['lab']
                    ct       = r.get('contact') or {}
                    lab_name = ct.get('lab_name') or lab

                    # Labor-Header
                    c.setFillColorRGB(0, 0, 0)
                    c.setFont('Helvetica-Bold', 9)
                    c.drawString(m, yy, lab)
                    lw = c.stringWidth(lab, 'Helvetica-Bold', 9)
                    c.setFont('Helvetica', 9)
                    c.setFillColorRGB(0.45, 0.45, 0.45)
                    c.drawString(m + lw + 4, yy, f'— {lab_name}')
                    c.setFillColorRGB(0, 0, 0)
                    yy -= 9*mm

                    # Checkboxen auf einer Linie
                    cx = m
                    baseline = yy - 2*mm
                    for status in STATUS:
                        # Kästchen
                        c.setStrokeColorRGB(0.3, 0.3, 0.3)
                        c.setFillColorRGB(1, 1, 1)
                        c.rect(cx, baseline, BOX, BOX, fill=1, stroke=1)
                        # acroForm overlay
                        try:
                            acf.checkbox(
                                name=f'cb_{lab}_{status}',
                                x=cx, y=baseline, size=BOX,
                                buttonStyle='check',
                                borderColor=_cols_v.white,
                                fillColor=_cols_v.white,
                                textColor=_cols_v.black,
                                borderWidth=0,
                            )
                        except Exception:
                            pass
                        # Label auf gleicher Höhe wie Kästchen-Mitte
                        c.setFillColorRGB(0, 0, 0)
                        c.setFont('Helvetica', 8)
                        c.drawString(cx + BOX + GAP, baseline + 1, status)
                        cx += col_w
                    yy -= 9*mm

                    # Versendet am / Werte erhalten am
                    half = uw / 2
                    field_h = 5*mm
                    for lbl, fname, ox in [
                        ('Versendet am:',      f'td_versand_{lab}',  0),
                        ('Werte erhalten am:', f'td_eingang_{lab}',  half),
                    ]:
                        lx = m + ox
                        fw = c.stringWidth(lbl, 'Helvetica', 8) + 4
                        # Feld
                        try:
                            acf.textfield(
                                name=fname, tooltip=lbl,
                                x=lx + fw, y=yy - field_h,
                                width=half - fw - 4*mm, height=field_h,
                                borderStyle='underlined',
                                borderColor=_cols_v.HexColor('#bbbbbb'),
                                fillColor=_cols_v.white,
                                textColor=_cols_v.black,
                                fontSize=8, forceBorder=True,
                            )
                        except Exception:
                            pass
                        # Label — baseline = field bottom + 1pt
                        c.setFillColorRGB(0, 0, 0)
                        c.setFont('Helvetica', 8)
                        c.drawString(lx, yy - field_h + 1, lbl)
                    yy -= field_h + 3*mm

                    # Bemerkungen
                    bw = c.stringWidth('Bemerkungen:', 'Helvetica', 8) + 4
                    try:
                        acf.textfield(
                            name=f'td_bem_{lab}', tooltip='Bemerkungen',
                            x=m + bw, y=yy - field_h,
                            width=uw - bw, height=field_h,
                            borderStyle='underlined',
                            borderColor=_cols_v.HexColor('#bbbbbb'),
                            fillColor=_cols_v.white,
                            textColor=_cols_v.black,
                            fontSize=8, forceBorder=True,
                        )
                    except Exception:
                        pass
                    c.setFillColorRGB(0, 0, 0)
                    c.setFont('Helvetica', 8)
                    c.drawString(m, yy - field_h + 1, 'Bemerkungen:')
                    yy -= field_h + 4*mm

                    # Trennlinie
                    c.setStrokeColorRGB(0.85, 0.85, 0.85)
                    c.line(m, yy + 4*mm, m + uw, yy + 4*mm)
                    c.setStrokeColorRGB(0, 0, 0)
                    yy -= 3*mm

        story.append(PageBreak())
        story.append(_VersandDraw())

        # ── Quelldateien (eigene Seite ganz am Ende) ─────────────────────
        now   = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
        fdata = [['Dateiname','Analysiert am']] + \
                [[r['filename'], now] for r in results]
        ft = Table(fdata, colWidths=[120*mm, 47*mm], repeatRows=1)
        ft.setStyle(TableStyle(tbl_style([
            ('ALIGN', (1,0),(-1,-1), 'RIGHT'),
        ])))
        story += [PageBreak(), SP(6), KeepTogether([HDR('Quelldateien'), ft])]

        doc.build(story)


if __name__ == '__main__':
    App().mainloop()
