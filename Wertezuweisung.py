# VERSION: 2026-05-12-LSD-FIX
#!/usr/bin/env python3
"""
Analyte Comparison Tool  –  medichem diagnostica
pip install pdfplumber reportlab
python analyte_comparison.py
"""

import os, sys, re, threading, itertools, datetime
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
BG, FG, GRAY, LIGHT, BORDER = '#ffffff', '#111111', '#888888', '#f2f2f2', '#e0e0e0'
FONT     = ('Arial', 10)
FONT_SM  = ('Arial', 9)
FONT_XS  = ('Arial', 8)
FONT_B   = ('Arial', 10, 'bold')
FONT_SMB = ('Arial', 9, 'bold')

def fmt_eur(v):
    s = f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    return s + ' EUR'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Analyte Comparison')
        self.geometry('1400x900')
        self.minsize(900, 600)
        self.state('zoomed')  # Vollbild beim Start
        self.configure(bg=BG)
        self.files      = []
        self.results    = []
        self.masked     = set()   # masked labs
        self.masked_runs     = set()  # masked runs für Probe: 'LAB-RUN'
        self.forced_runs     = set()  # manually forced runs: 'LAB-RUN'
        self.fixed_runs      = set()  # explicitly pinned via Fix-checkbox
        self.ref_masked_runs = set()  # runs die für Referenz NICHT gemessen werden: 'LAB-RUN'
        self.lab_measure_count = {}   # lab -> Anzahl Messungen (Multiplikator), default 1
        self.lod_mode = tk.StringVar(value='ohne')  # 'ohne' oder 'mit' — LOD-Anzeige in Tabellen
        self.opt_probe_var = None
        self.opt_ref_var   = None
        self.opt_probe_lbl = None
        self._opt_total_cost = 0.0
        self.opt_result = None
        self._planning_path = None   # aktuell geöffnete .wz-Datei
        self._archive_dir   = None   # Archiv-Ordner (persistent via settings)
        self._setup_styles()
        self._build()

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('Treeview', background=BG, foreground=FG, rowheight=20,
                    fieldbackground=BG, font=FONT_SM)
        s.configure('Treeview.Heading', background=LIGHT, foreground=GRAY,
                    font=('Arial', 8), relief='flat', padding=(4,3))
        s.map('Treeview', background=[('selected','#e8e8e8')],
                          foreground=[('selected',FG)])
        s.configure('TNotebook', background='#f8f8f8', borderwidth=0)
        s.configure('TNotebook.Tab', font=FONT_SM, padding=[14,5],
                    background='#f0f0f0', foreground=GRAY)
        s.map('TNotebook.Tab', background=[('selected',BG)],
                               foreground=[('selected',FG)])
        s.configure('TProgressbar', background=FG, troughcolor=LIGHT)

    def _build(self):
        # ── Topbar: alles in einer Zeile ──────────────────────
        topbar = tk.Frame(self, bg=BG, padx=16, pady=8)
        topbar.pack(fill='x')

        # Logo links
        logo = tk.Frame(topbar, bg=BG)
        logo.pack(side='left')
        tk.Label(logo, text='ANALYTE COMPARISON', font=('Arial',12,'bold'),
                 bg=BG, fg=FG).pack(anchor='w')
        tk.Label(logo, text='medichem diagnostica', font=FONT_XS,
                 bg=BG, fg=GRAY).pack(anchor='w')

        # Planung-Buttons links neben Logo
        plan_row = tk.Frame(topbar, bg=BG)
        plan_row.pack(side='left', padx=(16,0))
        self._btn_small(plan_row, '💾 Speichern',   lambda: self._save_planning(),    primary=False).pack(side='left', padx=(0,4))
        self._btn_small(plan_row, '📂 Laden',        lambda: self._load_planning(),    primary=False).pack(side='left', padx=(0,4))
        self._btn_small(plan_row, '🗄 Archivieren',  lambda: self._archive_planning(), primary=False).pack(side='left', padx=(0,12))
        self._btn_small(plan_row, '＋ Neue Planung', lambda: self._new_planning(),     primary=False).pack(side='left')

        # Aktions-Buttons ganz rechts in Topbar
        btn_row = tk.Frame(topbar, bg=BG)
        btn_row.pack(side='right')
        self.run_btn = self._btn_small(btn_row, 'Analysieren →', self._run, primary=True)
        self.run_btn.pack(side='right', padx=(6,0))
        lod_row = tk.Frame(btn_row, bg=BG)
        lod_row.pack(side='right', padx=(6,0))
        self.lod_btn_mit  = self._btn_small(lod_row, 'Mit LOD',  lambda: self._set_lod_mode('mit'),  primary=False)
        self.lod_btn_mit.pack(side='left', padx=(2,0))
        self.lod_btn_ohne = self._btn_small(lod_row, 'Ohne LOD', lambda: self._set_lod_mode('ohne'), primary=True)
        self.lod_btn_ohne.pack(side='left')
        self._btn_small(btn_row, 'Entfernen', self._remove_file, primary=False).pack(side='right', padx=(6,0))
        self._btn_small(btn_row, '+ Dateien', self._add_files, primary=False).pack(side='right')

        tk.Frame(self, bg=BORDER, height=1).pack(fill='x')

        # ── Statuszeile ───────────────────────────────────────
        sbar = tk.Frame(self, bg=LIGHT, padx=16, pady=3)
        sbar.pack(fill='x')
        self.status_var = tk.StringVar(value='Dateien hinzufügen und Analysieren klicken.')
        tk.Label(sbar, textvariable=self.status_var, font=FONT_XS,
                 fg=GRAY, bg=LIGHT).pack(side='left')
        self.progress = ttk.Progressbar(sbar, length=120, mode='determinate')
        self.progress.pack(side='right')

        tk.Frame(self, bg=BORDER, height=1).pack(fill='x')

        # ── Hauptbereich: Dateiliste rechts, Tabs links ───────
        content = tk.Frame(self, bg=BG)
        content.pack(fill='both', expand=True)

        # Dateiliste als feste rechte Spalte
        tk.Frame(content, bg=BORDER, width=1).pack(side='right', fill='y', pady=8)
        file_col = tk.Frame(content, bg=BG, width=260)
        file_col.pack(side='right', fill='y', padx=(0,8), pady=8)
        file_col.pack_propagate(False)
        tk.Label(file_col, text='DATEIEN', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(anchor='w', pady=(0,4))
        fl = tk.Frame(file_col, bg=BORDER, padx=1, pady=1)
        fl.pack(fill='both', expand=True)
        fi = tk.Frame(fl, bg=BG)
        fi.pack(fill='both', expand=True)
        sb_y = tk.Scrollbar(fi, orient='vertical')
        self.file_lb = tk.Listbox(fi, yscrollcommand=sb_y.set, font=FONT_SM,
            bg=BG, fg=FG, selectbackground='#e8e8e8', relief='flat',
            bd=0, activestyle='none')
        sb_y.config(command=self.file_lb.yview)
        sb_y.pack(side='right', fill='y')
        self.file_lb.pack(side='left', fill='both', expand=True, padx=4, pady=2)

        # Notebook
        self.nb = ttk.Notebook(content)
        self.nb.pack(fill='both', expand=True)
        self._build_tab_overview()
        self._build_tab_opt()

    def _btn_small(self, parent, text, cmd, primary=True):
        return tk.Button(parent, text=text, command=cmd, font=FONT_SM,
            bg=FG if primary else BG, fg=BG if primary else FG,
            relief='flat', padx=10, pady=4,
            activebackground='#333' if primary else LIGHT,
            activeforeground=BG if primary else FG,
            cursor='hand2', bd=0)

    def _btn(self, parent, text, cmd, primary=True):
        b = self._btn_small(parent, text, cmd, primary)
        b.pack(fill='x', pady=2)
        return b

    def _tree(self, parent):
        t = ttk.Treeview(parent, show='headings', selectmode='none')
        vsb = ttk.Scrollbar(parent, orient='vertical', command=t.yview)
        hsb = ttk.Scrollbar(parent, orient='horizontal', command=t.xview)
        t.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side='bottom', fill='x')
        vsb.pack(side='right', fill='y')
        t.pack(fill='both', expand=True)
        t.tag_configure('group',    background='#f4f4f4', font=FONT_SMB)
        t.tag_configure('alt',      background='#fafafa')
        t.tag_configure('normal',   background=BG)
        t.tag_configure('inactive', background='#f0f0f0', foreground='#aaaaaa')
        t.tag_configure('ok5',      background='#e8f5e9')
        t.tag_configure('ok3',      background='#fff9e6')
        t.tag_configure('low',      background='#fdecea')
        return t

    # ── Tab 1: Übersicht ──────────────────────────────────────
    def _build_tab_overview(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text='  Übersicht  ')

        # Hauptbereich: Tabelle + rechtes Panel
        main = tk.Frame(tab, bg=BG)
        main.pack(fill='both', expand=True)

        # Tabelle nimmt fast alles
        tf = tk.Frame(main, bg=BG)
        tf.pack(side='left', fill='both', expand=True, padx=(8,0), pady=8)
        self.tree = self._tree(tf)
        self.tree.bind('<Button-3>', self._overview_rightclick)

        # Probe-Rechner Vars (nur im Opt-Tab genutzt, hier als Stubs)
        self.n_proben_var = tk.IntVar(value=0)
        self.n_ref_var    = tk.IntVar(value=0)
        self.ref_lab_vars = {}
        self.probe_lbl    = None
        self.ref_check_frame = tk.Frame(self, bg=BG)  # unsichtbarer Stub
        self.export_btn = tk.Button(self, state='disabled')  # Stub, nie sichtbar

    def _build_probe_rechner(self):
        pass  # Probenrechner nur im Opt-Tab

    def _update_probe(self):
        try:
            n  = int(self.n_proben_var.get())
            nr = int(self.n_ref_var.get())
        except:
            return
        active = [r for r in self.results if r['lab'] not in self.masked]
        if not active or (n == 0 and nr == 0):
            if self.probe_lbl: self.probe_lbl.config(text='')
            return

        # Kosten Probe: alle aktiven Labore
        cost_probe = sum(r.get('cost') or 0 for r in active)
        # Kosten Referenz: nur Labore mit gesetzter Checkbox
        cost_ref = sum(
            r.get('cost') or 0 for r in active
            if self.ref_lab_vars.get(r['lab'], tk.BooleanVar(value=True)).get()
        )

        if cost_probe == 0 and cost_ref == 0:
            if self.probe_lbl: self.probe_lbl.config(text='')
            return

        lines = []
        if n:
            lines.append(f'Einfachbestimmung Probe:   {fmt_eur(cost_probe*n)}')
            lines.append(f'Doppelbestimmung Probe:    {fmt_eur(cost_probe*2*n)}')
        if nr:
            lines.append(f'Doppelbestimmung Referenz: {fmt_eur(cost_ref*2*nr)}')
        if n and nr:
            lines.append(f'\u2211 Einfach:  {fmt_eur(cost_probe*n + cost_ref*nr)}')
            lines.append(f'\u2211 Doppelt:  {fmt_eur(cost_probe*2*n + cost_ref*2*nr)}')
        if self.probe_lbl: self.probe_lbl.config(text='\n'.join(lines))

    # ── Tab 2: Optimierung ────────────────────────────────────
    def _build_tab_opt(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text='  Optimierung  ')

        # Kontrollleiste
        ctrl = tk.Frame(tab, bg=LIGHT, padx=12, pady=8)
        ctrl.pack(fill='x')

        def lbl(t): return tk.Label(ctrl, text=t, font=FONT_SM, bg=LIGHT, fg=FG)
        def spin(var): return tk.Spinbox(ctrl, from_=1, to=20, width=4, textvariable=var, font=FONT_SM)

        lbl('Min. Abdeckung (n ≥)').pack(side='left', padx=(0,4))
        self.min_n_var = tk.IntVar(value=3)
        spin(self.min_n_var).pack(side='left', padx=(0,14))

        lbl('Ziel-Abdeckung (n ≥)').pack(side='left', padx=(0,4))
        self.tgt_n_var = tk.IntVar(value=5)
        spin(self.tgt_n_var).pack(side='left', padx=(0,14))

        lbl('Max. Abdeckung (n ≤)').pack(side='left', padx=(0,4))
        self.max_n_var = tk.IntVar(value=6)
        spin(self.max_n_var).pack(side='left', padx=(0,14))

        self.opt_btn = tk.Button(ctrl, text='Optimieren →', command=self._run_opt,
            font=FONT_SM, bg=FG, fg=BG, relief='flat', padx=12, pady=4,
            cursor='hand2', bd=0)
        self.opt_btn.pack(side='left', padx=(0,8))

        self.opt_export_btn = tk.Button(ctrl, text='Export PDF', command=self._export_opt,
            font=FONT_SM, bg=BG, fg=FG, relief='flat', padx=12, pady=4,
            cursor='hand2', bd=0, state='disabled')
        self.opt_export_btn.pack(side='left', padx=(0,4))

        self.opt_preview_btn = tk.Button(ctrl, text='Vorschau',
            command=self._preview_opt,
            font=FONT_SM, bg=LIGHT, fg=FG, relief='flat', padx=10, pady=4,
            cursor='hand2', bd=0, state='disabled')
        self.opt_preview_btn.pack(side='left', padx=(0,14))

        self.opt_status = tk.StringVar(value='PDFs laden → Analysieren → Optimieren klicken.')
        tk.Label(ctrl, textvariable=self.opt_status, font=FONT_XS,
                 fg=GRAY, bg=LIGHT).pack(side='left')

        tk.Frame(tab, bg=BORDER, height=1).pack(fill='x')

        # Body
        body = tk.Frame(tab, bg=BG)
        body.pack(fill='both', expand=True)

        # Verfügbare Labore — eigene Spalte ganz links
        mask_col = tk.Frame(body, bg=BG, width=130, padx=8, pady=10)
        mask_col.pack(side='left', fill='y')
        mask_col.pack_propagate(False)
        tk.Label(mask_col, text='VERFÜGBARE\nLABORE', font=FONT_XS,
                 fg=GRAY, bg=BG, justify='left').pack(anchor='w', pady=(0,4))
        self.mask_frame = tk.Frame(mask_col, bg=BG)
        self.mask_frame.pack(fill='x')
        tk.Frame(body, bg=BORDER, width=1).pack(side='left', fill='y', pady=8)

        # Linkes Panel: scrollbar
        left_outer = tk.Frame(body, bg=BG, width=300)
        left_outer.pack(side='left', fill='y')
        left_outer.pack_propagate(False)

        left_canvas = tk.Canvas(left_outer, bg=BG, highlightthickness=0, width=290)
        left_sb = ttk.Scrollbar(left_outer, orient='vertical', command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_sb.set)
        left_sb.pack(side='right', fill='y')
        left_canvas.pack(side='left', fill='both', expand=True)

        left = tk.Frame(left_canvas, bg=BG, padx=12, pady=10)
        left_canvas.create_window((0,0), window=left, anchor='nw')

        def _on_left_configure(e):
            left_canvas.configure(scrollregion=left_canvas.bbox('all'))
        left.bind('<Configure>', _on_left_configure)

        def _on_mousewheel(e):
            left_canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        left_canvas.bind_all('<MouseWheel>', _on_mousewheel)

        tk.Label(left, text='OPTIMALE AUSWAHL', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(anchor='w', pady=(0,4))
        self.opt_lab_frame = tk.Frame(left, bg=BG)
        self.opt_lab_frame.pack(fill='x')

        # Ganz rechts: Chargen-Spalte
        tk.Frame(body, bg=BORDER, width=1).pack(side='right', fill='y', pady=8)
        chargen_col = tk.Frame(body, bg=BG, width=180, padx=8, pady=10)
        chargen_col.pack(side='right', fill='y')
        chargen_col.pack_propagate(False)
        tk.Label(chargen_col, text='CHARGEN', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(anchor='w', pady=(0,4))
        # Zusammenfassung fest oben in Chargen-Spalte
        self.opt_probe_lbl = tk.Label(chargen_col, text='', font=FONT_SM,
                                      fg=FG, bg=BG, anchor='w', justify='left',
                                      wraplength=160)
        self.opt_probe_lbl.pack(anchor='w', fill='x')
        tk.Frame(chargen_col, bg=BORDER, height=1).pack(fill='x', pady=(6,4))
        self._batch_container_outer = tk.Frame(chargen_col, bg=BG)
        self._batch_container_outer.pack(fill='both', expand=True)

        tk.Frame(body, bg=BORDER, width=1).pack(side='right', fill='y', pady=8)

        # Kosten + Probenrechner (mittlere rechte Spalte)
        cost_right = tk.Frame(body, bg=BG, width=250, padx=10, pady=10)
        cost_right.pack(side='right', fill='y')
        cost_right.pack_propagate(False)

        # Trennlinie links von Tabelle
        tk.Frame(body, bg=BORDER, width=1).pack(side='left', fill='y', pady=8)

        # Mitte: Abdeckungstabelle
        right = tk.Frame(body, bg=BG, padx=8, pady=10)
        right.pack(side='left', fill='both', expand=True)

        # Toolbar
        tbar = tk.Frame(right, bg=BG)
        tbar.pack(fill='x', pady=(0,4))
        tk.Label(tbar, text='ABDECKUNG', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(side='left')
        tk.Button(tbar, text='Alle Labore anzeigen',
                  font=FONT_XS, bg=LIGHT, fg=FG, relief='flat',
                  padx=8, pady=2, cursor='hand2', bd=0,
                  command=self._show_all_labs_overview).pack(side='right')

        tf = tk.Frame(right, bg=BG)
        tf.pack(fill='both', expand=True)
        self.opt_tree = self._tree(tf)
        self.opt_tree.bind('<Button-3>', self._opt_rightclick)

        tk.Label(cost_right, text='KOSTEN PRO PROBE', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(anchor='w', pady=(0,6))
        self.opt_cost_frame_container = tk.Frame(cost_right, bg=BG)
        self.opt_cost_frame_container.pack(fill='x')
        self.opt_cost_frame = tk.Frame(self.opt_cost_frame_container, bg=BG)
        self.opt_cost_frame.pack(fill='x')

        tk.Frame(cost_right, bg=BORDER, height=1).pack(fill='x', pady=(12,10))
        tk.Label(cost_right, text='PROBENRECHNER', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(anchor='w', pady=(0,6))

        # Scrollbarer Bereich für Spinboxen + Checkboxen
        self.opt_probe_outer = tk.Frame(cost_right, bg=BG)
        self.opt_probe_outer.pack(fill='x', anchor='n')
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title='PDF-Dateien auswählen',
            filetypes=[('PDF','*.pdf')])
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                self.file_lb.insert('end', os.path.basename(p))
        if paths:
            self.status_var.set(f'{len(self.files)} Datei(en) bereit.')

    def _remove_file(self):
        sel = self.file_lb.curselection()
        if not sel: return
        idx = sel[0]
        self.file_lb.delete(idx)
        self.files.pop(idx)
        self.status_var.set(f'{len(self.files)} Datei(en) bereit.')

    def _run(self):
        if not self.files:
            messagebox.showwarning('Keine Dateien', 'Bitte erst PDF-Dateien hinzufügen.')
            return
        self.run_btn.config(state='disabled')
        self.results = []
        self.masked  = set()
        self.progress['maximum'] = len(self.files)
        self.progress['value']   = 0
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        errors = []
        for i, path in enumerate(self.files):
            self.status_var.set(f'Lese {i+1}/{len(self.files)}: {os.path.basename(path)}…')
            try:
                r = parse_pdf(path)
                self.results.append(r)
            except Exception as e:
                errors.append(f'{os.path.basename(path)}: {e}')
                self.results.append({'lab': os.path.basename(path)[:15],
                                     'analytes': [], 'cost': None,
                                     'filename': os.path.basename(path)})
            self.progress['value'] = i + 1
        self.after(0, self._on_done, errors)

    def _on_done(self, errors):
        n_ok = sum(1 for r in self.results if r['analytes'])
        self.status_var.set(f'{len(self.results)} verarbeitet, {n_ok} mit Daten.')
        self.run_btn.config(state='normal')
        if errors:
            messagebox.showerror('Fehler', '\n'.join(errors))
        self._refresh_overview()
        self._refresh_mask_panel()
        self.export_btn.config(state='normal' if self.results else 'disabled')

    # ── Übersicht rendern ─────────────────────────────────────
    def _active(self):
        return [r for r in self.results if r['lab'] not in self.masked]

    def _refresh_overview(self):
        active = self._active()
        self._render_table(self.tree, active, show_all_analytes=True)
        self._render_costs(active) if hasattr(self, 'cost_frame') else None
        self._rebuild_ref_checks(active)
        self._update_probe()

    def _rebuild_ref_checks(self, active):
        """Checkboxen: welche Labore bekommen Referenzproben."""
        for w in self.ref_check_frame.winfo_children():
            w.destroy()
        if not active: return
        tk.Label(self.ref_check_frame, text='Referenz an:',
                 font=FONT_XS, fg=GRAY, bg=BG).pack(anchor='w')
        for r in active:
            lab = r['lab']
            if lab not in self.ref_lab_vars:
                self.ref_lab_vars[lab] = tk.BooleanVar(value=True)
            var = self.ref_lab_vars[lab]
            cb = tk.Checkbutton(self.ref_check_frame, text=lab,
                                variable=var, font=FONT_SM,
                                bg=BG, fg=FG, activebackground=BG,
                                command=self._update_probe)
            cb.pack(anchor='w', pady=1)

    def _render_table(self, tree, results, coverage=None,
                      min_n=None, target_n=None, show_all_analytes=False):
        # Vollständiger Reset — verhindert dass alte Spalten steckenbleiben
        tree.delete(*tree.get_children())
        try:
            tree['columns'] = []
        except Exception:
            pass
        self.update()
        if not results: return

        labs = [r['lab'] for r in results]
        # Alle bekannten Analyten — inkl. nicht-validierter (all_analytes)
        # Analyt-Liste immer aus allen bekannten PDFs (self.results) aufbauen
        all_a = sorted(
            {a for r in self.results
             for a in r.get('all_analytes', r['analytes'])},
            key=sort_key)

        # Spalten = alle geladenen Labore (optimierte + nicht-optimierte)
        all_results_for_cols = list(self.results)
        labs_cols = [r['lab'] for r in all_results_for_cols]

        cols = ['Analyt'] + labs_cols + ['n']
        tree['columns'] = cols
        tree.heading('Analyt', text='Analyt')
        tree.column('Analyt', width=200, minwidth=120, stretch=False)
        for lab in labs_cols:
            tree.heading(lab, text=lab)
            w = max(70, min(len(lab)*9, 160))
            tree.column(lab, width=w, minwidth=50, stretch=False, anchor='center')
        tree.heading('n', text='n')
        tree.column('n', width=36, minwidth=36, stretch=False, anchor='e')

        # Optimierte Labs als Set für schnelle Prüfung
        opt_labs_set = {r['lab'] for r in results}

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
                # Für optimierte Labs: sel_runs aus opt_result
                if in_opt:
                    r_opt = next((x for x in results if x['lab'] == lab), r)
                    runs = r_opt.get('runs', r.get('runs', {}))
                    sel_runs = r_opt.get('selected_runs', list(runs.keys()))
                else:
                    runs = r.get('runs', {})
                    sel_runs = []  # nicht optimiert → keine aktiven Runs
                orig = next((x for x in self.results if x['lab'] == lab), r)
                all_runs_lab = list(orig.get('runs', runs).keys())

                mcount = self.lab_measure_count.get(lab, 1)
                mprefix = f'{mcount}' if mcount != 1 else ''
                _lv = _lod_lookup.get(lab, {}).get(analyte.lower()) if lod_on else None

                if runs:
                    # Aktive (gewählte) Runs mit diesem Analyten
                    active_runs = []
                    for rl in sel_runs:
                        key = f"{lab}-{rl}"
                        if key not in self.masked_runs:
                            if any(a.lower()==analyte.lower()
                                   for a in runs.get(rl, {}).get('analytes', [])):
                                active_runs.append(rl)

                    # Nicht gewählte Runs mit diesem Analyten
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
                        # Vorhanden aber nicht gewählt — grau, zählt NICHT
                        cell = '○ (' + ','.join(inactive_runs) + ')' if coverage is not None else '○'
                        # has bleibt False → zählt nicht im n-Counter und nicht im Export
                    else:
                        cell = ''
                else:
                    has = any(a.lower() == analyte.lower() for a in r['analytes'])
                    if has:
                        cell = (f'{_lv:g}' if _lv is not None else '✓') if lod_on else (mprefix + '✓')
                    else:
                        cell = ''
                if lod_on and has and _lv is not None:
                    _row_lod.append((len(vals), _lv))
                vals.append(cell)
                if has: count += mcount
            vals.append(str(count) if count else '')

            if lod_on and _row_lod:
                _min_v = min(v for _, v in _row_lod)
                for _idx, _v in _row_lod:
                    if _v == _min_v:
                        vals[_idx] = '★' + vals[_idx]

            # Prüfen ob nur inaktive Treffer (~ Einträge) vorhanden
            only_inactive = (count == 0 and any(
                '✓' in v for v in vals[1:-1]
            ))

            if coverage is not None:
                c = count
                tag = 'ok5' if c >= target_n else 'ok3' if c >= min_n else 'low'
            else:
                if only_inactive:
                    tag = 'inactive'
                else:
                    tag = 'alt' if row_idx % 2 == 0 else 'normal'
            tree.insert('', 'end', values=vals, tags=(tag,))
            row_idx += 1

    def _render_costs(self, active):
        # Komplett neu aufbauen statt nur Widgets löschen
        self.cost_frame.destroy()
        self.cost_frame = tk.Frame(self.cost_container, bg=BG)
        self.cost_frame.pack(fill='x')
        if not active: return

        PAD = 10
        headers = ['Labor', '1 Analyse', '1 Probe', 'Doppelbestimmung']
        for col, h in enumerate(headers):
            anchor = 'w' if col == 0 else 'e'
            tk.Label(self.cost_frame, text=h, font=FONT_XS, fg=GRAY, bg=BG,
                     anchor=anchor).grid(row=0, column=col,
                     padx=(0,PAD) if col<3 else 0, pady=(0,2),
                     sticky='e' if col else 'w')
        tk.Frame(self.cost_frame, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=4, sticky='ew', pady=(0,2))

        total = 0.0
        for i, r in enumerate(active):
            c = r.get('cost')
            row = i + 2
            tk.Label(self.cost_frame, text=r['lab'], font=FONT_SM,
                     fg=FG, bg=BG, anchor='w').grid(row=row, column=0,
                     padx=(0,PAD), pady=0, sticky='w')
            if c is not None:
                for col, val in [(1,c),(2,c),(3,c*2)]:
                    tk.Label(self.cost_frame, text=fmt_eur(val), font=FONT_SM,
                             fg=FG, bg=BG, anchor='e').grid(row=row, column=col,
                             padx=(0,PAD) if col<3 else 0, sticky='e')
                total += c
            else:
                for col in range(1,4):
                    tk.Label(self.cost_frame, text='–', font=FONT_SM,
                             fg=GRAY, bg=BG, anchor='e').grid(row=row, column=col,
                             padx=(0,PAD) if col<3 else 0, sticky='e')

        sr = len(active)+2
        tk.Frame(self.cost_frame, bg=BORDER, height=1).grid(
            row=sr, column=0, columnspan=4, sticky='ew', pady=(3,2))
        tk.Label(self.cost_frame, text='Gesamt', font=FONT_SMB,
                 fg=FG, bg=BG, anchor='w').grid(row=sr+1, column=0,
                 padx=(0,PAD), sticky='w')
        for col, val in [(1,total),(2,total),(3,total*2)]:
            tk.Label(self.cost_frame, text=fmt_eur(val), font=FONT_SMB,
                     fg=FG, bg=BG, anchor='e').grid(row=sr+1, column=col,
                     padx=(0,PAD) if col<3 else 0, sticky='e')

    # ── Optimierung ───────────────────────────────────────────
    def _refresh_mask_panel(self):
        for w in self.mask_frame.winfo_children():
            w.destroy()
        for r in self.results:
            lab    = r['lab']
            masked = lab in self.masked
            color  = GRAY if masked else FG
            symbol = '⊘' if masked else '✓'
            lbl = tk.Label(self.mask_frame,
                           text=f'{symbol} {lab}',
                           font=FONT_SM, fg=color, bg=BG,
                           anchor='w', cursor='hand2')
            lbl.pack(fill='x', pady=1)
            lbl.bind('<Button-1>', lambda e, l=lab: self._toggle_mask(l))
            lbl.bind('<Button-3>', lambda e, l=lab: self._toggle_mask(l))
            # Maskierte Runs anzeigen
            if not masked:
                for key in sorted(self.masked_runs):
                    if key.startswith(lab + '-'):
                        rl = key.split('-', 1)[1]
                        sub = tk.Label(self.mask_frame,
                                       text=f'  ⊘ Run {rl}',
                                       font=('Arial',8), fg=GRAY, bg=BG,
                                       anchor='w', cursor='hand2')
                        sub.pack(fill='x')
                        sub.bind('<Button-1>', lambda e, k=key: self._toggle_run_mask(k, True))

    def _toggle_mask(self, lab):
        if lab in self.masked:
            self.masked.discard(lab)
        else:
            self.masked.add(lab)
        self._refresh_mask_panel()
        self._refresh_overview()
        # Wenn Optimierungsergebnis vorhanden: sofort neu berechnen
        if self.opt_result is not None:
            self._rerun_opt_after_mask()
        self.update()

    def _overview_rightclick(self, event):
        """Rechtsklick auf einen Laborkopf in der Übersicht: Messanzahl setzen."""
        region = self.tree.identify_region(event.x, event.y)
        col    = self.tree.identify_column(event.x)
        if region != 'heading':
            return
        try:
            idx = int(col.replace('#', '')) - 1
            cols = list(self.tree['columns'])
            if idx < 0 or idx >= len(cols):
                return
            lab = cols[idx]
        except Exception:
            return
        if lab in ('Analyt', 'n'):
            return
        self._ask_lab_measure_count(lab)

    def _ask_lab_measure_count(self, lab):
        """Fragt ab, wie oft ein Labor gemessen hat, und aktualisiert alle Ansichten."""
        current = self.lab_measure_count.get(lab, 1)
        n = simpledialog.askinteger(
            'Anzahl Messungen',
            f'Wie oft hat Labor {lab} gemessen?',
            initialvalue=current, minvalue=1, parent=self)
        if n is None:
            return
        if n == 1:
            self.lab_measure_count.pop(lab, None)
        else:
            self.lab_measure_count[lab] = n
        self._refresh_overview()
        if self.opt_result:
            labs, cost, cov, min_n, target_n = self.opt_result
            self._render_table(self.opt_tree, labs, coverage=cov,
                               min_n=min_n, target_n=target_n, show_all_analytes=True)

    def _set_lod_mode(self, mode):
        """Schaltet zwischen 'ohne LOD' (Haken) und 'mit LOD' (LOD-Werte) um."""
        self.lod_mode.set(mode)
        # Button-Optik aktualisieren
        self.lod_btn_ohne.config(
            bg=FG if mode == 'ohne' else BG, fg=BG if mode == 'ohne' else FG)
        self.lod_btn_mit.config(
            bg=FG if mode == 'mit' else BG, fg=BG if mode == 'mit' else FG)
        self._refresh_overview()
        if self.opt_result:
            labs, cost, cov, min_n, target_n = self.opt_result
            self._render_table(self.opt_tree, labs, coverage=cov,
                               min_n=min_n, target_n=target_n, show_all_analytes=True)

    def _toggle_ref_run_mask(self, key):
        """Schaltet einen Run für die Referenz an/aus."""
        if key in self.ref_masked_runs:
            self.ref_masked_runs.discard(key)
        else:
            self.ref_masked_runs.add(key)
        if self.opt_result:
            labs, cost, _, _, _ = self.opt_result
            self._render_opt_labs(labs, cost)

    def _show_all_labs_overview(self):
        """Zeigt alle aktiven Labore ohne Optimierung — finaler Überblick."""
        active = self._active()
        if not active:
            return
        # Labs mit selected_runs aufbauen (alle Runs jedes Labors)
        labs = []
        for r in active:
            lab_copy = dict(r)
            runs_d = r.get('runs', {})
            lab_copy['selected_runs'] = list(runs_d.keys())
            lab_copy['selected_cost'] = sum(
                (rd.get('cost') or 0) for rd in runs_d.values())
            labs.append(lab_copy)
        total = sum(r['selected_cost'] for r in labs)
        self._render_table(self.opt_tree, labs,
                           coverage=None, min_n=None, target_n=None,
                           show_all_analytes=True)
        self._render_opt_costs(labs, total)
        self.opt_export_btn.config(state='normal')
        self.opt_preview_btn.config(state='normal')
        self.opt_result = (labs, total, {}, 0, 0)
        self.opt_status.set(f'Überblick: {len(labs)} Labore — keine Optimierung')

    def _rerun_opt_after_mask(self):
        """Optimierung mit aktuell aktiven Laboren neu berechnen.

        Wichtig: Alle Runs, die im aktuellen Ergebnis ausgewählt sind,
        werden als erzwungen behandelt — außer explizit maskierten.
        So ändert das Maskieren/Erzwingen eines einzelnen Runs nie die
        Auswahl der anderen Labore (kein unerwartetes Umsortieren).
        """
        active = self._active()
        if not active:
            self.opt_result = None
            self._render_opt_labs([], 0)
            self._render_table(self.opt_tree, [], None, None, None)
            self.opt_status.set('Alle Labore maskiert.')
            self.opt_export_btn.config(state='disabled')
            self.opt_preview_btn.config(state='disabled')
            return
        prev_labs, _, _, min_n, target_n = self.opt_result
        max_n = self.max_n_var.get()
        self.opt_status.set('Aktualisiere…')

        masked_runs = set(self.masked_runs)
        # Alle momentan gewählten Runs einfrieren, damit nur die explizite
        # Änderung wirkt und der Rest stabil bleibt.
        pinned = set(self.forced_runs)
        for r in prev_labs:
            for rl in r.get('selected_runs', []):
                key = f"{r['lab']}-{rl}"
                if key not in masked_runs:
                    pinned.add(key)

        def worker():
            try:
                labs, cost, cov = optimize(active, min_n, target_n, max_n, masked_runs, pinned)
                self.after(0, self._on_opt_done, labs, cost, cov, min_n, target_n)
            except Exception as e:
                import traceback; traceback.print_exc()
                msg = str(e)
                self.after(0, lambda m=msg: self.opt_status.set(f'Fehler: {m}'))

        threading.Thread(target=worker, daemon=True).start()

    def _run_opt(self):
        active = self._active()
        if not active:
            messagebox.showwarning('Keine Daten', 'Zuerst PDFs laden oder Maskierung aufheben.')
            return
        min_n    = self.min_n_var.get()
        target_n = self.tgt_n_var.get()
        max_n    = self.max_n_var.get()
        self.opt_btn.config(state='disabled')
        self.opt_status.set('Optimierung läuft…')

        # Auch maskierte Runs ausschließen
        active_runs = [
            r for r in active
        ]
        masked_runs = set(self.masked_runs)
        forced_runs = set(self.forced_runs)

        def worker():
            try:
                labs, cost, cov = optimize(active_runs, min_n, target_n, max_n, masked_runs, forced_runs)
                self.after(0, self._on_opt_done, labs, cost, cov, min_n, target_n)
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: [
                    self.opt_btn.config(state='normal'),
                    self.opt_status.set(f'Fehler: {m}'),
                    messagebox.showerror('Fehler', m)
                ])

        threading.Thread(target=worker, daemon=True).start()

    def _render_opt_costs(self, labs, total_cost):
        """Kostentabelle + Probenrechner rechts im Opt-Tab."""
        # Kostentabelle
        self.opt_cost_frame.destroy()
        self.opt_cost_frame = tk.Frame(self.opt_cost_frame_container, bg=BG)
        self.opt_cost_frame.pack(fill='x')

        PAD = 8
        self.opt_cost_frame.columnconfigure(0, minsize=55)
        self.opt_cost_frame.columnconfigure(1, minsize=65)
        self.opt_cost_frame.columnconfigure(2, minsize=65)
        headers = ['', '1×', '2×']
        for col, h in enumerate(headers):
            tk.Label(self.opt_cost_frame, text=h, font=FONT_XS, fg=GRAY, bg=BG,
                     anchor='e').grid(row=0, column=col, padx=(0,PAD) if col<2 else 0,
                pady=(0,2), sticky='e' if col else 'w')
        tk.Frame(self.opt_cost_frame, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=3, sticky='ew', pady=(0,2))

        total = 0.0
        row_idx = 2
        for r in labs:
            orig      = next((x for x in self.results if x['lab'] == r['lab']), r)
            runs_data = orig.get('runs', {})
            sel_runs  = r.get('selected_runs', list(runs_data.keys()))

            c_probe = sum((runs_data.get(rl, {}).get('cost') or 0)
                         for rl in sel_runs
                         if f"{r['lab']}-{rl}" not in self.masked_runs)
            c_ref   = sum((runs_data.get(rl, {}).get('cost') or 0)
                         for rl in sel_runs
                         if f"{r['lab']}-{rl}" not in self.ref_masked_runs)
            total  += c_probe + c_ref

            # Labor-Name
            tk.Label(self.opt_cost_frame, text=r['lab'], font=FONT_SMB,
                     fg=FG, bg=BG, anchor='w').grid(
                row=row_idx, column=0, columnspan=3, sticky='w', pady=(4,0))
            row_idx += 1

            for lbl, c in [('  Probe', c_probe), ('  Ref', c_ref)]:
                tk.Label(self.opt_cost_frame, text=lbl, font=FONT_XS,
                         fg=GRAY, bg=BG, anchor='w').grid(
                    row=row_idx, column=0, sticky='w')
                tk.Label(self.opt_cost_frame,
                         text=fmt_eur(c) if c else '–',
                         font=FONT_XS, fg=FG, bg=BG, anchor='e').grid(
                    row=row_idx, column=1, sticky='e', padx=(0,PAD))
                tk.Label(self.opt_cost_frame,
                         text=fmt_eur(c*2) if c else '–',
                         font=FONT_XS, fg=FG, bg=BG, anchor='e').grid(
                    row=row_idx, column=2, sticky='e')
                row_idx += 1

        tk.Frame(self.opt_cost_frame, bg=BORDER, height=1).grid(
            row=row_idx, column=0, columnspan=3, sticky='ew', pady=(3,2))
        tk.Label(self.opt_cost_frame, text='Gesamt', font=FONT_SMB,
                 fg=FG, bg=BG).grid(row=row_idx+1, column=0, padx=(0,PAD), sticky='w')
        self._opt_gesamt_var1 = tk.StringVar(value=fmt_eur(total))
        self._opt_gesamt_var2 = tk.StringVar(value=fmt_eur(total*2))
        tk.Label(self.opt_cost_frame, textvariable=self._opt_gesamt_var1,
                 font=FONT_SMB, fg=FG, bg=BG).grid(
            row=row_idx+1, column=1, padx=(0,PAD), sticky='e')
        tk.Label(self.opt_cost_frame, textvariable=self._opt_gesamt_var2,
                 font=FONT_SMB, fg=FG, bg=BG).grid(
            row=row_idx+1, column=2, sticky='e')

        # Probenrechner
        for w in self.opt_probe_outer.winfo_children():
            w.destroy()
        if self.opt_probe_var is None:
            self.opt_probe_var = tk.IntVar(value=0)
        if self.opt_ref_var is None:
            self.opt_ref_var = tk.IntVar(value=0)

        # Sicherstellen dass batch-dicts existieren
        if not hasattr(self, 'probe_batch_vars'):
            self.probe_batch_vars = {}   # idx -> StringVar
        if not hasattr(self, 'ref_batch_vars'):
            self.ref_batch_vars   = {}

        # Spinboxen: Proben, Referenzproben, Messtage
        if not hasattr(self, 'opt_messtage_var') or self.opt_messtage_var is None:
            self.opt_messtage_var = tk.IntVar(value=1)

        for label, var in [('Proben', self.opt_probe_var),
                           ('Referenzproben', self.opt_ref_var),
                           ('Messtage', self.opt_messtage_var)]:
            row = tk.Frame(self.opt_probe_outer, bg=BG)
            row.pack(fill='x', pady=2)
            tk.Label(row, text=label, font=FONT_SM, fg=FG, bg=BG,
                     anchor='w').pack(side='left', fill='x', expand=True)
            sb = tk.Spinbox(row, from_=0 if label != 'Messtage' else 1,
                            to=9999, width=6,
                            textvariable=var, font=FONT_SM,
                            command=lambda: self._rebuild_batch_fields(total_cost, labs))
            sb.pack(side='right')
            var.trace_add('write', lambda *_, tc=total_cost, ls=labs:
                          self._rebuild_batch_fields(tc, ls))

        tk.Frame(self.opt_probe_outer, bg=BORDER, height=1).pack(fill='x', pady=(6,4))

        # Referenz-Checkboxen
        tk.Label(self.opt_probe_outer, text='Referenz an:',
                 font=FONT_XS, fg=GRAY, bg=BG).pack(anchor='w', pady=(6,2))
        if not hasattr(self, 'opt_ref_lab_vars'):
            self.opt_ref_lab_vars = {}
        for r in labs:
            lab = r['lab']
            if lab not in self.opt_ref_lab_vars:
                self.opt_ref_lab_vars[lab] = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(self.opt_probe_outer, text=lab,
                                variable=self.opt_ref_lab_vars[lab],
                                font=FONT_SM, bg=BG, fg=FG, activebackground=BG,
                                command=lambda tc=total_cost, ls=labs:
                                    self._calc_opt_probe(tc, ls))
            cb.pack(anchor='w')

        # Chargen in eigener Spalte rechts
        if hasattr(self, '_batch_container_outer'):
            for w in self._batch_container_outer.winfo_children():
                try: w.destroy()
                except: pass
            self._batch_container = self._batch_container_outer
        else:
            self._batch_container = tk.Frame(self.opt_probe_outer, bg=BG)
            self._batch_container.pack(fill='x')

        self._batch_labs  = labs
        self._batch_total = total_cost

        self._opt_total_cost = total_cost
        self._rebuild_batch_fields(total_cost, labs)

    def _calc_opt_probe(self, total_cost=None, labs=None):
        try:
            n  = int(self.opt_probe_var.get())
            nr = int(self.opt_ref_var.get())
            mt = max(1, int(self.opt_messtage_var.get())) \
                 if hasattr(self, 'opt_messtage_var') and self.opt_messtage_var else 1
        except: return
        lbl = self.opt_probe_lbl
        if lbl is None: return
        try:
            if n == 0 and nr == 0:
                lbl.config(text=''); return

            # Probe-Kosten live berechnen
            if labs is None and self.opt_result:
                labs = self.opt_result[0]
            if not labs: lbl.config(text=''); return

            cost_probe = 0.0
            cost_ref   = 0.0
            for r in labs:
                lab = r['lab']
                orig = next((x for x in self.results if x['lab'] == lab), r)
                runs_data = orig.get('runs', {})
                sel_runs  = r.get('selected_runs', list(runs_data.keys()))
                for rl in sel_runs:
                    rc = runs_data.get(rl, {}).get('cost') or 0
                    if f"{lab}-{rl}" not in self.masked_runs:
                        cost_probe += rc
                    ref_incl = getattr(self, 'opt_ref_lab_vars', {}).get(
                        lab, tk.BooleanVar(value=True)).get()
                    if ref_incl and f"{lab}-{rl}" not in self.ref_masked_runs:
                        cost_ref += rc

            lines = []
            if mt > 1:
                lines.append(f'× {mt} Messtage')
            if n:
                lines.append(f'Probe ×1:   {fmt_eur(cost_probe*n*mt)}')
                lines.append(f'Probe ×2:   {fmt_eur(cost_probe*2*n*mt)}')
            if nr:
                lines.append(f'Ref ×1:     {fmt_eur(cost_ref*nr*mt)}')
                lines.append(f'Ref ×2:     {fmt_eur(cost_ref*2*nr*mt)}')
            if n and nr:
                lines.append(f'∑ ×1:  {fmt_eur(cost_probe*n*mt + cost_ref*nr*mt)}')
                lines.append(f'∑ ×2:  {fmt_eur(cost_probe*2*n*mt + cost_ref*2*nr*mt)}')

            # Gesamt-Labels immer aktualisieren
            total1 = cost_probe*n*mt + cost_ref*nr*mt
            total2 = cost_probe*2*n*mt + cost_ref*2*nr*mt
            if hasattr(self, '_opt_gesamt_var1') and self._opt_gesamt_var1:
                try:
                    self._opt_gesamt_var1.set(fmt_eur(total1))
                    self._opt_gesamt_var2.set(fmt_eur(total2))
                except Exception:
                    pass
            lbl.config(text=chr(10).join(lines))
        except Exception:
            pass

    def _rebuild_batch_fields(self, total_cost=None, labs=None):
        """Baut Chargen-Felder dynamisch nach Proben/Referenz-Anzahl."""
        self._calc_opt_probe()

        container = getattr(self, '_batch_container', None)
        if container is None: return
        try:
            container.winfo_exists()  # wirft Exception wenn zerstört
            if not container.winfo_exists(): return
            children = container.winfo_children()
        except Exception:
            return

        for w in children:
            try: w.destroy()
            except Exception: pass

        try: n_probe = int(self.opt_probe_var.get())
        except: n_probe = 0
        try: n_ref = int(self.opt_ref_var.get())
        except: n_ref = 0

        if n_probe == 0 and n_ref == 0:
            return

        # Bestehende Werte sichern
        old_probe = {k: v.get() for k, v in self.probe_batch_vars.items()}
        old_ref   = {k: v.get() for k, v in self.ref_batch_vars.items()}
        self.probe_batch_vars = {}
        self.ref_batch_vars   = {}

        def section(parent, title, n, old_vals, store):
            if n == 0: return
            tk.Label(parent, text=title, font=FONT_XS, fg=GRAY,
                     bg=BG).pack(anchor='w', pady=(6,1))
            for i in range(n):
                row = tk.Frame(parent, bg=BG)
                row.pack(fill='x', pady=1)
                tk.Label(row, text=f'{i+1}.',
                         font=FONT_XS, fg=GRAY, bg=BG, width=2).pack(side='left')
                var = tk.StringVar(value=old_vals.get(i, ''))
                store[i] = var
                tk.Entry(row, textvariable=var, font=FONT_SM,
                         bg=LIGHT, fg=FG, relief='flat', bd=3).pack(
                         side='left', fill='x', expand=True)

        section(container, 'Probe-Chargen', n_probe,
                old_probe, self.probe_batch_vars)
        section(container, 'Referenz-Chargen', n_ref,
                old_ref,   self.ref_batch_vars)

    def _get_batches(self):
        """Liest aktuelle Chargen-Eingaben als dict für PDF-Export."""
        probe = {i: v.get().strip()
                 for i, v in getattr(self, 'probe_batch_vars', {}).items()}
        ref   = {i: v.get().strip()
                 for i, v in getattr(self, 'ref_batch_vars', {}).items()}
        return {'probe': probe, 'ref': ref,
                'ref_masked_runs': set(self.ref_masked_runs)}

    def _on_opt_done(self, labs, cost, cov, min_n, target_n):
        self.opt_btn.config(state='normal')
        if not labs or not cov:
            self.opt_status.set('Keine Lösung gefunden – alle Labore maskiert?')
            return
        total = len(cov)
        n_min = sum(1 for c in cov.values() if c >= min_n)
        n_tgt = sum(1 for c in cov.values() if c >= target_n)
        self.opt_status.set(
            f'{len(labs)} Labore · {fmt_eur(cost)} · '
            f'{n_min}/{total} ≥{min_n}× · {n_tgt}/{total} ≥{target_n}×')
        self.opt_result = (labs, cost, cov, min_n, target_n)
        self._render_opt_labs(labs, cost)
        self._render_table(self.opt_tree, labs, coverage=cov,
                           min_n=min_n, target_n=target_n, show_all_analytes=True)
        self.opt_export_btn.config(state='normal')
        self.opt_preview_btn.config(state='normal')

    def _render_opt_labs(self, labs, total_cost):
        for w in self.opt_lab_frame.winfo_children():
            w.destroy()

        # Alle Labore anzeigen — optimierte normal, nicht-optimierte ausgegraut
        opt_labs = {r['lab'] for r in labs}
        all_results = list(self.results)

        for r in all_results:
            lab_in_opt = r['lab'] in opt_labs
            # Für optimierte Labs: opt-Result nutzen; sonst: alle Runs ausgegraut
            if lab_in_opt:
                r_display = next((x for x in labs if x['lab'] == r['lab']), r)
            else:
                r_display = r
            sel_runs  = r_display.get('selected_runs', []) if lab_in_opt else []
            orig = next((x for x in self.results if x['lab'] == r['lab']), None)
            runs_data = orig['runs'] if orig else r.get('runs', {})
            all_runs  = sorted(runs_data.keys())

            # Kosten live: Probe (nicht in masked_runs) + Ref (nicht in ref_masked_runs)
            cost_probe = sum(
                (runs_data.get(rl, {}).get('cost') or 0)
                for rl in sel_runs
                if f"{r['lab']}-{rl}" not in self.masked_runs
            )
            cost_ref = sum(
                (runs_data.get(rl, {}).get('cost') or 0)
                for rl in sel_runs
                if f"{r['lab']}-{rl}" not in self.ref_masked_runs
            )
            sel_cost = cost_probe + cost_ref

            # Labor-Header
            hdr = tk.Frame(self.opt_lab_frame, bg=BG)
            hdr.pack(fill='x', pady=(6,1))
            tk.Label(hdr, text=r['lab'], font=FONT_SMB, bg=BG, fg=FG,
                     anchor='w').pack(side='left')

            # Alle Runs anzeigen — gewählte und nicht gewählte
            # Header-Zeile für Probe/Ref-Spalten
            hdr2 = tk.Frame(self.opt_lab_frame, bg=BG)
            hdr2.pack(fill='x', padx=(10,0))
            tk.Label(hdr2, text='', font=FONT_XS, bg=BG, width=19,
                     anchor='w').pack(side='left')
            tk.Label(hdr2, text='Probe', font=FONT_XS, fg=GRAY,
                     bg=BG, width=6, anchor='center').pack(side='left')
            tk.Label(hdr2, text='Ref', font=FONT_XS, fg=GRAY,
                     bg=BG, width=4, anchor='center').pack(side='left')
            tk.Label(hdr2, text='Fix', font=FONT_XS, fg=GRAY,
                     bg=BG, width=4, anchor='center').pack(side='right', padx=(0,4))

            for rl in all_runs:
                rd  = runs_data.get(rl, {})
                rc  = rd.get('cost') or 0
                key = f"{r['lab']}-{rl}"
                masked_probe = key in self.masked_runs
                masked_ref   = key in self.ref_masked_runs
                selected     = rl in sel_runs
                not_chosen   = not selected and not masked_probe and lab_in_opt
                # Nicht-optimierte Labore: alle Runs ausgegraut
                if not lab_in_opt:
                    not_chosen = True

                sub = tk.Frame(self.opt_lab_frame,
                               bg=LIGHT if not_chosen else BG)
                sub.pack(fill='x', padx=(10,0), pady=1)

                # Fix-Checkbox rechts
                fix_var = tk.BooleanVar(value=key in self.fixed_runs)
                def _on_fix(k=key, v=fix_var):
                    if v.get():
                        self.fixed_runs.add(k)
                        self.forced_runs.add(k)
                        self.masked_runs.discard(k)
                    else:
                        self.fixed_runs.discard(k)
                        self.forced_runs.discard(k)
                    self._refresh_mask_panel()
                    if self.opt_result:
                        self._rerun_opt_after_mask()
                fix_cb = tk.Checkbutton(sub, variable=fix_var, command=_on_fix,
                                        bg=sub['bg'], activebackground=sub['bg'],
                                        padx=0, pady=0, bd=0, cursor='hand2')
                fix_cb.pack(side='right', padx=(0,4))

                # Run-Name + Kosten — klickbar für Toggle
                if not_chosen:
                    run_col = '#cccccc'
                elif masked_probe:
                    run_col = '#aaaaaa'
                else:
                    run_col = FG

                run_lbl = tk.Label(sub,
                    text=f"Run {rl}  {fmt_eur(rc)}",
                    font=('Arial', 8), bg=sub['bg'], fg=run_col,
                    anchor='w', width=18, cursor='hand2')
                run_lbl.pack(side='left')
                def _is_active(k, lab_, rl_):
                    in_sel = any(
                        rl_ in (res.get('selected_runs') or [])
                        for res in (self.opt_result[0] if self.opt_result else [])
                        if res['lab'] == lab_
                    ) or k in self.forced_runs
                    return in_sel and k not in self.masked_runs

                def _toggle_both(e, k=key, lab_=r['lab'], rl_=rl):
                    if _is_active(k, lab_, rl_):
                        self.masked_runs.add(k)
                        self.ref_masked_runs.add(k)
                        self.forced_runs.discard(k)
                    else:
                        self.masked_runs.discard(k)
                        self.ref_masked_runs.discard(k)
                        self.forced_runs.add(k)
                    self._refresh_mask_panel()
                    if self.opt_result:
                        self._rerun_opt_after_mask()
                run_lbl.bind('<Button-1>', _toggle_both)

                # Probe-Toggle
                if not_chosen:
                    p_sym, p_col = '○', '#cccccc'
                elif masked_probe:
                    p_sym, p_col = '⊘', '#aaaaaa'
                else:
                    p_sym, p_col = '✓', FG
                probe_lbl = tk.Label(sub, text=p_sym, font=('Arial', 8),
                                     bg=sub['bg'], fg=p_col, width=6,
                                     anchor='center', cursor='hand2')
                probe_lbl.pack(side='left')
                def _toggle_probe(e, k=key, lab_=r['lab'], rl_=rl):
                    if _is_active(k, lab_, rl_):
                        self.masked_runs.add(k)
                        self.forced_runs.discard(k)
                    else:
                        self.masked_runs.discard(k)
                        self.forced_runs.add(k)
                    self._refresh_mask_panel()
                    if self.opt_result:
                        self._rerun_opt_after_mask()
                probe_lbl.bind('<Button-1>', _toggle_probe)

                # Ref-Toggle
                if not_chosen:
                    r_sym, r_col = '○', '#cccccc'
                elif masked_ref:
                    r_sym, r_col = '⊘', '#aaaaaa'
                else:
                    r_sym, r_col = '✓', FG
                ref_lbl = tk.Label(sub, text=r_sym, font=('Arial', 8),
                                   bg=sub['bg'], fg=r_col, width=4,
                                   anchor='center', cursor='hand2')
                ref_lbl.pack(side='left')
                ref_lbl.bind('<Button-1>', lambda e, k=key:
                             self._toggle_ref_run_mask(k))

                n_analytes = len(rd.get('analytes', []))
                tk.Label(sub, text=f"({n_analytes})",
                         font=('Arial',8), bg=sub['bg'],
                         fg='#cccccc' if not_chosen else BORDER).pack(side='right')

        # Kostentabelle + Probenrechner rechts neu aufbauen
        self._render_opt_costs(labs, total_cost)

        if self.opt_probe_lbl is not None:
            try: self.opt_probe_lbl.destroy()
            except: pass
        self.opt_probe_lbl = tk.Label(self.opt_lab_frame, text='', font=FONT_SM,
                                      fg=FG, bg=BG, anchor='w', justify='left')
        self.opt_probe_lbl.pack(anchor='w', pady=(4,0))
        self._opt_total_cost = total_cost

        def _calc(*_):
            try:
                n  = int(self.opt_probe_var.get())
                nr = int(self.opt_ref_var.get())
            except: return
            tc = self._opt_total_cost
            lbl = self.opt_probe_lbl
            if lbl is None: return
            try:
                if tc == 0 or (n == 0 and nr == 0):
                    lbl.config(text=''); return
                lines = []
                if n:
                    lines.append(f'Einfachbestimmung Probe:   {fmt_eur(tc*n)}')
                    lines.append(f'Doppelbestimmung Probe:    {fmt_eur(tc*2*n)}')
                if nr:
                    lines.append(f'Doppelbestimmung Referenz: {fmt_eur(tc*2*nr)}')
                if n and nr:
                    lines.append(f'∑ Einfach:  {fmt_eur(tc*n + tc*nr)}')
                    lines.append(f'∑ Doppelt:  {fmt_eur(tc*2*n + tc*2*nr)}')
                lbl.config(text=chr(10).join(lines))
            except Exception:
                pass

        self.opt_probe_var.trace_add('write', _calc)
        self.opt_ref_var.trace_add('write', _calc)
        _calc()  # Sofort neu berechnen mit bestehenden Werten

    def _opt_rightclick(self, event):
        """Rechtsklick auf Zeile: zeige Runs für diesen Analyten zum Maskieren."""
        region = self.opt_tree.identify_region(event.x, event.y)
        col    = self.opt_tree.identify_column(event.x)

        # Spaltenheader-Klick: Labor maskieren / Messanzahl setzen
        if region == 'heading':
            try:
                idx = int(col.replace('#','')) - 1
                cols = list(self.opt_tree['columns'])
                if idx < 0 or idx >= len(cols): return
                name = cols[idx]
            except: return
            if name in ('Analyt','n'): return
            menu = tk.Menu(self, tearoff=0)
            label = 'Einblenden' if name in self.masked else 'Maskieren'
            menu.add_command(label=f'{label}: {name}',
                command=lambda: self._toggle_mask(name))
            n_now = self.lab_measure_count.get(name, 1)
            menu.add_command(label=f'Anzahl Messungen setzen (aktuell: {n_now}×)',
                command=lambda: self._ask_lab_measure_count(name))
            menu.tk_popup(event.x_root, event.y_root)
            return

        row_id = self.opt_tree.identify_row(event.y)
        if not row_id: return

        # Zeilen-Klick: Run-Optionen anbieten
        if not self.opt_result: return
        labs, cost, cov, min_n, target_n = self.opt_result
        menu = tk.Menu(self, tearoff=0)
        added = False
        for r in labs:
            sel_runs = r.get('selected_runs', [])
            for rl in sel_runs:
                key = f"{r['lab']}-{rl}"
                rd = r.get('runs', {}).get(rl, {})
                rc = rd.get('cost', 0) or 0
                label = f"{'Einblenden' if key in self.masked_runs else 'Maskieren'}: {r['lab']} Run {rl} ({fmt_eur(rc)})"
                menu.add_command(label=label,
                    command=lambda k=key: self._toggle_run_mask(k))
                added = True
        if added:
            menu.tk_popup(event.x_root, event.y_root)

    def _toggle_run_mask(self, key, selected):
        """
        Dreizustand:
        - Gewählt + nicht maskiert → maskieren
        - Maskiert → wieder aktivieren (unmaskieren)
        - Nicht gewählt → erzwingen (forced_runs)
        - Erzwungen → zurücksetzen
        """
        if selected:
            # Gewählter Run: toggle maskieren
            if key in self.masked_runs:
                self.masked_runs.discard(key)
            else:
                self.masked_runs.add(key)
        else:
            # Nicht gewählter Run: toggle erzwingen
            if key in self.forced_runs:
                self.forced_runs.discard(key)
            else:
                self.forced_runs.add(key)
        self._refresh_mask_panel()
        if self.opt_result:
            self._rerun_opt_after_mask()

    # ── Planung Speichern / Laden / Archivieren ───────────────
    def _state_to_dict(self):
        """Serialisiert den kompletten App-Zustand als dict."""
        import json
        opt = None
        if self.opt_result:
            labs, cost, cov, min_n, target_n = self.opt_result
            opt = {
                'labs': [
                    {k: v for k, v in r.items()
                     if k not in ('_result',)}
                    for r in labs
                ],
                'cost': cost,
                'cov':  cov,
                'min_n': min_n,
                'target_n': target_n,
            }
        return {
            'version':      2,
            'files':        self.files,
            'masked':       list(self.masked),
            'masked_runs':     list(self.masked_runs),
            'ref_masked_runs': list(self.ref_masked_runs),
            'forced_runs':     list(self.forced_runs),
            'fixed_runs':      list(self.fixed_runs),
            'lab_measure_count': dict(self.lab_measure_count),
            'min_n':        self.min_n_var.get()  if hasattr(self, 'min_n_var')  else 3,
            'target_n':     self.tgt_n_var.get()  if hasattr(self, 'tgt_n_var')  else 5,
            'max_n':        self.max_n_var.get()  if hasattr(self, 'max_n_var')  else 6,
            'n_proben':     self.n_proben_var.get() if self.n_proben_var else 0,
            'n_ref':        self.n_ref_var.get()    if self.n_ref_var    else 0,
            'opt_n_proben': self.opt_probe_var.get() if self.opt_probe_var else 0,
            'opt_n_ref':    self.opt_ref_var.get()   if self.opt_ref_var  else 0,
            'opt_messtage': self.opt_messtage_var.get() if hasattr(self, 'opt_messtage_var') and self.opt_messtage_var else 1,
            'opt_result':   opt,
            'archive_dir':  self._archive_dir,
            'results_meta': [
                {'lab': r['lab'], 'filename': r['filename'],
                 'product': r.get('product',''),
                 'contact': r.get('contact', {})}
                for r in self.results
            ],
        }

    def _state_from_dict(self, d):
        """Stellt App-Zustand aus dict wieder her (PDFs werden neu geparst)."""
        self.files       = d.get('files', [])
        self.masked      = set(d.get('masked', []))
        self.masked_runs = set(d.get('masked_runs', []))
        self.forced_runs     = set(d.get('forced_runs', []))
        self.fixed_runs      = set(d.get('fixed_runs', []))
        self.ref_masked_runs = set(d.get('ref_masked_runs', []))
        self.lab_measure_count = dict(d.get('lab_measure_count', {}))
        self._archive_dir    = d.get('archive_dir')

        if hasattr(self, 'min_n_var'):  self.min_n_var.set(d.get('min_n', 3))
        if hasattr(self, 'tgt_n_var'):  self.tgt_n_var.set(d.get('target_n', 5))
        if hasattr(self, 'max_n_var'):  self.max_n_var.set(d.get('max_n', 6))

        # Dateiliste UI aktualisieren
        self.file_lb.delete(0, 'end')
        missing = []
        for p in list(self.files):
            if os.path.exists(p):
                self.file_lb.insert('end', os.path.basename(p))
            else:
                missing.append(p)
                self.files.remove(p)
        if missing:
            messagebox.showwarning('Fehlende Dateien',
                'Folgende PDFs wurden nicht gefunden und wurden entfernt:\n' +
                '\n'.join(os.path.basename(p) for p in missing))

        # PDFs neu parsen
        if self.files:
            self.results = []
            self.run_btn.config(state='disabled')
            self.progress['maximum'] = len(self.files)
            self.progress['value']   = 0
            saved_state = d

            def worker():
                for i, path in enumerate(self.files):
                    self.status_var.set(f'Lade {i+1}/{len(self.files)}: {os.path.basename(path)}…')
                    try:
                        r = parse_pdf(path)
                        self.results.append(r)
                    except Exception as e:
                        self.results.append({'lab': os.path.basename(path)[:15],
                                             'analytes': [], 'cost': None,
                                             'filename': os.path.basename(path)})
                    self.progress['value'] = i + 1
                self.after(0, self._on_load_done, saved_state)

            threading.Thread(target=worker, daemon=True).start()

    def _on_load_done(self, d):
        self.run_btn.config(state='normal')
        if hasattr(self, 'opt_btn'):
            self.opt_btn.config(state='normal')
        self._refresh_overview()
        self._refresh_mask_panel()
        self.export_btn.config(state='normal' if self.results else 'disabled')

        if self.n_proben_var: self.n_proben_var.set(d.get('n_proben', 0))
        if self.n_ref_var:    self.n_ref_var.set(d.get('n_ref', 0))

        # Optimierungsergebnis wiederherstellen
        opt = d.get('opt_result')
        if opt:
            try:
                labs_raw = opt['labs']
                # Ergebnis-Labore mit echten results verknüpfen
                labs = []
                for lr in labs_raw:
                    orig = next((r for r in self.results if r['lab'] == lr['lab']), None)
                    if orig:
                        r2 = dict(orig)
                        r2['selected_runs'] = lr.get('selected_runs', [])
                        r2['selected_cost'] = lr.get('selected_cost', 0)
                        labs.append(r2)
                cov      = opt['cov']
                min_n    = opt['min_n']
                target_n = opt['target_n']
                cost     = opt['cost']
                self.opt_result = (labs, cost, cov, min_n, target_n)
                self._render_opt_labs(labs, cost)
                self._render_table(self.opt_tree, labs, coverage=cov,
                                   min_n=min_n, target_n=target_n, show_all_analytes=True)
                self.opt_export_btn.config(state='normal')
                self.opt_preview_btn.config(state='normal')
                if self.opt_probe_var:
                    self.opt_probe_var.set(d.get('opt_n_proben', 0))
                if self.opt_ref_var:
                    self.opt_ref_var.set(d.get('opt_n_ref', 0))
                if hasattr(self, 'opt_messtage_var') and self.opt_messtage_var:
                    self.opt_messtage_var.set(d.get('opt_messtage', 1))
                n_min = sum(1 for c in cov.values() if c >= min_n)
                n_tgt = sum(1 for c in cov.values() if c >= target_n)
                self.opt_status.set(
                    f'{len(labs)} Labore · {fmt_eur(cost)} · '
                    f'{n_min}/{len(cov)} ≥{min_n}× · {n_tgt}/{len(cov)} ≥{target_n}×')
            except Exception as e:
                self.opt_status.set(f'Optimierung konnte nicht wiederhergestellt werden: {e}')

        self.status_var.set(f'Planung geladen · {len(self.results)} Labore.')

    def _new_planning(self):
        if self.results or self.files:
            if not messagebox.askyesno('Neue Planung',
                    'Aktuelle Planung verwerfen und neu beginnen?'):
                return
        # Zustand zurücksetzen
        self.files        = []
        self.results      = []
        self.masked       = set()
        self.masked_runs  = set()
        self.forced_runs  = set()
        self.fixed_runs   = set()
        self.ref_masked_runs = set()
        self.lab_measure_count = {}
        self.opt_result   = None
        self._planning_path = None
        self.probe_batch_vars = {}
        self.ref_batch_vars   = {}

        # UI zurücksetzen
        self.file_lb.delete(0, 'end')
        self.title('Analyte Comparison')
        self.status_var.set('Bereit.')
        self.progress['value'] = 0
        self.export_btn.config(state='disabled')

        # Übersicht leeren
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Opt-Tab leeren
        for w in self.opt_lab_frame.winfo_children():
            w.destroy()
        for w in self.opt_cost_frame.winfo_children():
            w.destroy()
        for w in self.opt_probe_outer.winfo_children():
            w.destroy()
        for item in self.opt_tree.get_children():
            self.opt_tree.delete(item)
        self.opt_status.set('')
        self.opt_export_btn.config(state='disabled')
        self.opt_preview_btn.config(state='disabled')
        self.opt_result = None
        self.opt_probe_var = None
        self.opt_ref_var   = None
        self.opt_probe_lbl = None

        # Masken-Panel leeren
        for w in self.mask_frame.winfo_children():
            w.destroy()

    def _save_planning(self):
        import json
        if not self.results:
            messagebox.showwarning('Nichts zu speichern', 'Zuerst PDFs laden.')
            return
        path = self._planning_path or filedialog.asksaveasfilename(
            defaultextension='.wz',
            filetypes=[('WZ-Planung','*.wz'), ('Alle','*.*')],
            initialfile='Planung.wz')
        if not path: return
        try:
            import json
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._state_to_dict(), f, ensure_ascii=False, indent=2)
            self._planning_path = path
            self.title(f'Analyte Comparison — {os.path.basename(path)}')
            self.status_var.set(f'Gespeichert: {os.path.basename(path)}')
        except Exception as e:
            messagebox.showerror('Fehler', str(e))

    def _load_planning(self):
        import json
        path = filedialog.askopenfilename(
            filetypes=[('WZ-Planung','*.wz'), ('Alle','*.*')])
        if not path: return
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            self._planning_path = path
            self.title(f'Analyte Comparison — {os.path.basename(path)}')
            self._state_from_dict(d)
        except Exception as e:
            messagebox.showerror('Fehler', str(e))

    def _archive_planning(self):
        """Speichert Planung als .wz + exportiert PDF in Archiv-Ordner."""
        import json
        if not self.results:
            messagebox.showwarning('Nichts zu archivieren', 'Zuerst PDFs laden.')
            return

        # Archiv-Ordner bestimmen
        arch_dir = self._archive_dir
        if not arch_dir or not os.path.isdir(arch_dir):
            arch_dir = filedialog.askdirectory(title='Archiv-Ordner wählen')
            if not arch_dir: return
            self._archive_dir = arch_dir

        # Export-Metadaten abfragen (RV, Produkt, Kommentar, Chargen)
        results_for_meta = (
            [r for r, _ in zip(
                (next((r for r in self.results if r['lab']==lr['lab']), None)
                 for lr in self.opt_result[0]), range(100))
             if r] if self.opt_result else self._active()
        )
        meta = self._ask_export_meta(results_for_meta or self._active())
        if meta is None: return
        rv, product, comment, art_nrs = meta if len(meta) == 4 else (*meta, {})
        batches  = self._get_batches()
        n_proben = self.opt_probe_var.get() if self.opt_probe_var else 0
        n_ref    = self.opt_ref_var.get()   if self.opt_ref_var   else 0
        mt       = max(1, self.opt_messtage_var.get()) if hasattr(self, 'opt_messtage_var') and self.opt_messtage_var else 1
        n_proben = n_proben * mt
        n_ref    = n_ref    * mt

        date_str  = datetime.date.today().strftime('%d.%m.%Y')
        rv_part   = f"RV_{rv}_" if rv else ''
        prod_part = re.sub(r'[^\w\-]', '_', product)[:30] + '_' if product else ''
        active    = self._active()
        labs_used = (self.opt_result[0] if self.opt_result else active)
        _all_labs = [r['lab'] for r in labs_used]
        lab_codes = '_'.join(_all_labs[:8])
        if len(_all_labs) > 8:
            lab_codes += f'_+{len(_all_labs)-8}weitere'
        stem      = f"{rv_part}WZ-Planung_{prod_part}{lab_codes}_{date_str}"

        pdf_path = os.path.join(arch_dir, stem + '.pdf')
        wz_path  = os.path.join(arch_dir, stem + '.wz')

        try:
            # PDF exportieren
            if self.opt_result:
                labs, cost, cov, min_n, target_n = self.opt_result
                ref_vars = getattr(self, 'opt_ref_lab_vars', {})
                self._build_pdf(pdf_path, labs, cov, min_n, target_n,
                                n_proben=n_proben, n_ref=n_ref,
                                ref_lab_vars=ref_vars, comment=comment,
                                batches=batches)
            else:
                self._build_pdf(pdf_path, active, None, None, None,
                                n_proben=n_proben, n_ref=n_ref,
                                ref_lab_vars=self.ref_lab_vars,
                                comment=comment, batches=batches)
            # Planung speichern
            with open(wz_path, 'w', encoding='utf-8') as f:
                json.dump(self._state_to_dict(), f, ensure_ascii=False, indent=2)
            self._planning_path = wz_path
            self.title(f'Analyte Comparison — {os.path.basename(wz_path)}')
            self._toast(f'✓  Archiviert: {os.path.basename(pdf_path)}')
        except Exception as e:
            messagebox.showerror('Fehler', str(e))

    # ── PDF Export ────────────────────────────────────────────
    def _toast(self, message, duration=2500):
        """Zeigt eine kurze Erfolgsmeldung mittig auf dem Bildschirm."""
        dlg = tk.Toplevel(self)
        dlg.overrideredirect(True)
        dlg.attributes('-topmost', True)
        dlg.configure(bg='#2d6a2d')

        # Inhalt
        inner = tk.Frame(dlg, bg='#2d6a2d', padx=28, pady=20)
        inner.pack()
        tk.Label(inner, text='✓', font=('Arial', 28), bg='#2d6a2d',
                 fg='white').pack()
        tk.Label(inner, text=message, font=FONT_SM, bg='#2d6a2d',
                 fg='white', wraplength=320, justify='center').pack(pady=(6,14))
        tk.Button(inner, text='OK', font=FONT_B, bg='white', fg='#2d6a2d',
                  relief='flat', padx=24, pady=6, cursor='hand2', bd=0,
                  command=dlg.destroy).pack()

        # Zentrieren
        dlg.update_idletasks()
        w = dlg.winfo_reqwidth()
        h = dlg.winfo_reqheight()
        x = self.winfo_x() + self.winfo_width()  // 2 - w // 2
        y = self.winfo_y() + self.winfo_height() // 2 - h // 2
        dlg.geometry(f'+{x}+{y}')

        # Auch nach duration automatisch schließen
        dlg.after(duration, lambda: dlg.destroy() if dlg.winfo_exists() else None)

    def _ask_export_meta(self, results):
        products = [r.get('product','') for r in results if r.get('product')]
        default_product = max(set(products), key=products.count) if products else ''

        dlg = tk.Toplevel(self)
        dlg.title('Export-Informationen')
        dlg.resizable(True, True)
        dlg.grab_set()
        dlg.configure(bg=BG)
        dlg.minsize(440, 400)

        self.update_idletasks()
        x = self.winfo_x() + self.winfo_width()  // 2 - 220
        y = self.winfo_y() + self.winfo_height() // 2 - 250
        dlg.geometry(f'460x500+{x}+{y}')

        result = [None]
        art_entries = {}  # lab -> Entry

        def _ok():
            rv_raw = rv_entry.get().strip()
            if rv_raw == 'z.B. 25-26': rv_raw = ''
            art_nrs = {lab: e.get().strip() for lab, e in art_entries.items()}
            result[0] = (rv_raw, prod_entry.get().strip(),
                         txt.get('1.0', 'end').strip(), art_nrs)
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        dlg.bind('<Escape>',         lambda e: _cancel())
        dlg.bind('<Control-Return>', lambda e: _ok())

        # Buttons unten (fest)
        sep = tk.Frame(dlg, bg=BORDER, height=1)
        sep.pack(side='bottom', fill='x')
        btn_row = tk.Frame(dlg, bg=BG, padx=16, pady=10)
        btn_row.pack(side='bottom', fill='x')
        tk.Button(btn_row, text='Abbrechen', command=_cancel,
                  font=FONT_SM, bg=BG, fg=GRAY, relief='flat',
                  padx=12, pady=5, cursor='hand2', bd=0).pack(side='right', padx=(8,0))
        tk.Button(btn_row, text='PDF exportieren', command=_ok,
                  font=FONT_SM, bg=FG, fg=BG, relief='flat',
                  padx=12, pady=5, cursor='hand2', bd=0).pack(side='right')

        # Formular (scrollbar)
        outer = tk.Frame(dlg, bg=BG)
        outer.pack(fill='both', expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        form = tk.Frame(canvas, bg=BG, padx=20, pady=16)
        win_id = canvas.create_window((0,0), window=form, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_id, width=e.width))
        form.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        tk.Label(form, text='Export PDF', font=FONT_B,
                 bg=BG, fg=FG).pack(anchor='w', pady=(0,12))

        def labeled_entry(label, default='', hint=''):
            tk.Label(form, text=label, font=FONT_XS, fg=GRAY,
                     bg=BG).pack(anchor='w', pady=(0,2))
            e = tk.Entry(form, font=FONT_SM, bg=LIGHT, fg=FG, relief='flat', bd=4)
            e.pack(fill='x', pady=(0,10))
            if default:
                e.insert(0, default)
            elif hint:
                e.insert(0, hint); e.config(fg=GRAY)
                def _fi(ev, en=e, h=hint):
                    if en.get()==h: en.delete(0,'end'); en.config(fg=FG)
                def _fo(ev, en=e, h=hint):
                    if not en.get(): en.insert(0,h); en.config(fg=GRAY)
                e.bind('<FocusIn>', _fi); e.bind('<FocusOut>', _fo)
            return e

        rv_entry   = labeled_entry('RV-Nummer', hint='z.B. 25-26')
        prod_entry = labeled_entry('Produkt', default=default_product)

        tk.Label(form, text='Kommentar / Notizen', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(anchor='w', pady=(0,2))
        txt_frame = tk.Frame(form, bg=BORDER, padx=1, pady=1)
        txt_frame.pack(fill='x', pady=(0,12))
        txt = tk.Text(txt_frame, font=FONT_SM, bg=BG, fg=FG,
                      relief='flat', bd=0, wrap='word', height=2,
                      padx=6, pady=4)
        txt.pack(fill='x')

        # Artikelnummern pro Labor
        tk.Frame(form, bg=BORDER, height=1).pack(fill='x', pady=(4,8))
        tk.Label(form, text='Artikelnummern (für SelectLine)', font=FONT_XS,
                 fg=GRAY, bg=BG).pack(anchor='w', pady=(0,6))
        for r in results:
            lab = r['lab']
            row = tk.Frame(form, bg=BG)
            row.pack(fill='x', pady=2)
            tk.Label(row, text=lab, font=FONT_SM, fg=FG, bg=BG,
                     width=8, anchor='w').pack(side='left')
            e = tk.Entry(row, font=FONT_SM, bg=LIGHT, fg=FG,
                         relief='flat', bd=4, width=20)
            # Vorausfüllen aus gespeicherten Artikelnummern
            saved = getattr(self, '_art_nrs', {}).get(lab, '')
            if saved:
                e.insert(0, saved)
            e.pack(side='left', fill='x', expand=True)
            art_entries[lab] = e

        rv_entry.focus_set()
        self.wait_window(dlg)
        # Artikelnummern für nächsten Export merken
        if result[0]:
            self._art_nrs = result[0][3]
        return result[0]

    def _export_overview(self):
        """Delegiert an _export_opt — exportiert immer die Optimierung."""
        self._export_opt()

    def _preview_opt(self):
        """Erstellt PDF in temp-Ordner und öffnet es direkt."""
        if not self.opt_result: return
        labs, cost, cov, min_n, target_n = self.opt_result
        import tempfile
        try:
            n_proben = self.opt_probe_var.get() if self.opt_probe_var else 0
            n_ref    = self.opt_ref_var.get()   if self.opt_ref_var   else 0
            mt       = max(1, self.opt_messtage_var.get()) if hasattr(self, 'opt_messtage_var') and self.opt_messtage_var else 1
            n_proben = n_proben * mt
            n_ref    = n_ref    * mt
            batches  = self._get_batches()
            ref_vars = getattr(self, 'opt_ref_lab_vars', {})

            # Letzte Export-Metadaten verwenden (rv, product, comment, art_nrs)
            last = getattr(self, '_last_export_meta', ('', '', '', {}))
            rv, product, comment = last[0], last[1], last[2]
            art_nrs = last[3] if len(last) > 3 else {}

            tmp = tempfile.NamedTemporaryFile(
                suffix='.pdf', prefix='WZ_Vorschau_', delete=False)
            tmp.close()

            self._build_pdf(tmp.name, labs, cov, min_n, target_n,
                            n_proben=n_proben, n_ref=n_ref,
                            ref_lab_vars=ref_vars, comment=comment,
                            batches=batches, rv=rv, product=product,
                            art_nrs=art_nrs)
            os.startfile(tmp.name)
        except Exception as e:
            import traceback
            messagebox.showerror('Fehler', traceback.format_exc())

    def _export_opt(self):
        if not self.opt_result: return
        labs, cost, cov, min_n, target_n = self.opt_result
        meta = self._ask_export_meta(labs)
        if meta is None: return
        rv, product, comment, art_nrs = meta if len(meta) == 4 else (*meta, {})
        self._last_export_meta = (rv, product, comment, art_nrs)
        batches  = self._get_batches()
        n_proben = self.opt_probe_var.get() if self.opt_probe_var else 0
        n_ref    = self.opt_ref_var.get()   if self.opt_ref_var   else 0
        mt       = max(1, self.opt_messtage_var.get()) if hasattr(self, 'opt_messtage_var') and self.opt_messtage_var else 1
        n_proben = n_proben * mt
        n_ref    = n_ref    * mt
        date_str  = datetime.date.today().strftime('%d.%m.%Y')
        _all_labs = [r['lab'] for r in labs]
        lab_codes = '_'.join(_all_labs[:8])
        if len(_all_labs) > 8:
            lab_codes += f'_+{len(_all_labs)-8}weitere'
        rv_part   = f"RV_{rv}_" if rv else ''
        prod_part = re.sub(r'[^\w\-]', '_', product)[:30] + '_' if product else ''
        default   = f"{rv_part}WZ-Planung_{prod_part}{lab_codes}_{date_str}.pdf"
        path = filedialog.asksaveasfilename(defaultextension='.pdf',
            filetypes=[('PDF','*.pdf')], initialfile=default)
        if not path: return
        try:
            ref_vars = getattr(self, 'opt_ref_lab_vars', {})
            self._build_pdf(path, labs, cov, min_n, target_n,
                            n_proben=n_proben, n_ref=n_ref, ref_lab_vars=ref_vars,
                            comment=comment, batches=batches, rv=rv, product=product, art_nrs=art_nrs)
            self._toast(f'✓  PDF gespeichert: {os.path.basename(path)}')
        except Exception as e:
            import traceback
            messagebox.showerror('Fehler', traceback.format_exc())

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