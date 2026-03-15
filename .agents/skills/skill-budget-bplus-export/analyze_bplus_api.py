"""
BPLUS-NG API-JSON Analyse-Script
=================================
Universelles Script zur Auswertung der API-Exportdaten (CSV mit API-Feldnamen)
aus BPLUS-NG, erzeugt durch export_bplus_api.ps1.

Die API-CSV verwendet andere Spaltennamen als der Playwright-Excel-Export:
  concept, title, workFlowStatus, status, plannedValue, orgUnitName,
  company, creatorName, projektfamilie, eaTitel, pbmText, ...

Verwendung:
  python analyze_bplus_api.py <csv-datei> [--firma <suchbegriff>] [--status <suchbegriff>]
                                          [--ea <suchbegriff>] [--projekt <suchbegriff>]
                                          [--oe <suchbegriff>] [--top <n>]

Beispiele:
  python analyze_bplus_api.py export.csv                          # Gesamtuebersicht
  python analyze_bplus_api.py export.csv --firma 4soft            # Nur 4soft-Vorgaenge
  python analyze_bplus_api.py export.csv --status bestellt        # Nur Status "Bestellt"
  python analyze_bplus_api.py export.csv --ea "IDS.8"             # Nur EA-Titel mit IDS.8
  python analyze_bplus_api.py export.csv --projekt MEB            # Nur Projektfamilie MEB
  python analyze_bplus_api.py export.csv --firma edag --status bestellt  # Kombination
  python analyze_bplus_api.py export.csv --top 5                  # Top 5 Firmen
"""

import csv
import argparse
import sys
import os
from collections import defaultdict
from datetime import date
from io import StringIO

# Status-Mapping: API workFlowStatus -> Anzeige-Praefix
STATUS_MAP = {
    'WF_Created': '01_In Erstellung',
    'WF_In_process_BM_Team': '06_In Bearbeitung BM-Team',
    'WF_In_Planen_BM': '07_In Planen-BM',
    'WF_Rejected': '97_Abgelehnt',
    'WF_Canceled': '98_Storniert',
    'WF_Archived': '99_Archiviert',
}


def parse_wert(s):
    """Numerischen Wert aus API-CSV parsen (z.B. '37980.5' oder '37980,5')"""
    if not s:
        return 0.0
    s = s.replace(',', '.').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def format_eur(val):
    """Zahl als Euro-Betrag formatieren (Ganzzahl, deutsches Format)"""
    return f"{int(round(val)):,}".replace(',', '.')


def display_status(row):
    """Erzeugt lesbaren Status — API-CSV hat bereits kombinierten Status."""
    return row.get('status', '').strip()


def load_csv(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f, delimiter=','))


def filter_rows(data, firma=None, status=None, ea=None, projekt=None, oe=None):
    result = data
    if firma:
        q = firma.lower()
        result = [r for r in result if q in r.get('company', '').lower()]
    if status:
        q = status.lower()
        result = [r for r in result if q in r.get('status', '').lower()]
    if ea:
        q = ea.lower()
        result = [r for r in result if q in r.get('ea', '').lower()]
    if projekt:
        q = projekt.lower()
        result = [r for r in result if q in r.get('projektfamilie', '').lower()]
    if oe:
        q = oe.lower()
        result = [r for r in result if q in r.get('org_unit', '').lower()]
    return result


def print_vorgaenge(rows, out):
    """Gibt alle Einzelvorgaenge als Markdown-Tabelle aus."""
    total = 0
    out.write("| Konzept | EA-Nummer | EA-Titel | BM-Titel | Wert | Firma | Status |\n")
    out.write("|---|---|---|---|---:|---|---|\n")
    for r in rows:
        wert = parse_wert(r.get('planned_value', ''))
        total += wert
        konzept = r.get('concept', '?').strip()
        ea_titel = r.get('ea', '').strip()
        dev = r.get('dev_order', '').strip()
        bm_titel = r.get('title', '').strip()
        firma = r.get('company', '').strip()
        status = r.get('status', '').strip()
        out.write(f"| {konzept} | {dev} | {ea_titel} | {bm_titel} | {format_eur(wert)} | {firma} | {status} |\n")
    out.write(f"| | | | **Summe** | **{format_eur(total)}** | | |\n")
    out.write(f"\n{len(rows)} Vorgaenge, Gesamtwert: {format_eur(total)} EUR\n")
    return total


def print_by_status(rows, out):
    """Gibt Status-Zusammenfassung als Markdown-Tabelle und Mermaid Pie Chart aus."""
    status_sums = defaultdict(lambda: [0, 0.0])
    for r in rows:
        st = r.get('status', 'unbekannt').strip()
        wert = parse_wert(r.get('planned_value', ''))
        status_sums[st][0] += 1
        status_sums[st][1] += wert
    out.write("| Status | Anzahl | Wert |\n")
    out.write("|---|---:|---:|\n")
    for st, (cnt, sm) in sorted(status_sums.items()):
        out.write(f"| {st} | {cnt} | {format_eur(sm)} |\n")
    out.write("\n```mermaid\npie\n    title Status-Verteilung\n")
    for st, (cnt, sm) in sorted(status_sums.items()):
        out.write(f'    "{st}: {format_eur(sm)} EUR" : {int(round(sm))}\n')
    out.write("```\n")


def print_by_ea(rows, out):
    """Gibt EA-Zusammenfassung als Markdown-Tabelle aus."""
    eas = defaultdict(lambda: {'title': '', 'count': 0, 'sum': 0.0, 'statuses': defaultdict(float)})
    for r in rows:
        dev = r.get('dev_order', '').strip()
        if not dev:
            dev = '(ohne EA)'
        wert = parse_wert(r.get('planned_value', ''))
        eas[dev]['title'] = r.get('ea', '').strip()
        eas[dev]['count'] += 1
        eas[dev]['sum'] += wert
        st = r.get('status', '').strip()
        eas[dev]['statuses'][st] += wert
    sorted_eas = sorted(eas.items(), key=lambda x: -x[1]['sum'])
    total = 0
    out.write("| EA-Nummer | EA-Titel | Anzahl | Wert | Status-Detail |\n")
    out.write("|---|---|---:|---:|---|\n")
    for dev, info in sorted_eas:
        total += info['sum']
        status_detail = "; ".join(f"{st}: {format_eur(sv)}" for st, sv in sorted(info['statuses'].items()))
        out.write(f"| {dev} | {info['title']} | {info['count']} | {format_eur(info['sum'])} | {status_detail} |\n")
    out.write(f"| | **Gesamt** | **{sum(i['count'] for i in eas.values())}** | **{format_eur(total)}** | |\n")


def print_by_firma(rows, out, top_n=None):
    """Gibt Firmen-Zusammenfassung als Markdown-Tabelle aus."""
    firmen = defaultdict(lambda: [0, 0.0])
    for r in rows:
        firma = r.get('company', '').strip()
        if firma:
            wert = parse_wert(r.get('planned_value', ''))
            firmen[firma][0] += 1
            firmen[firma][1] += wert
    sorted_firmen = sorted(firmen.items(), key=lambda x: -x[1][1])
    if top_n:
        sorted_firmen = sorted_firmen[:top_n]
    out.write("| Firma | Anzahl | Wert |\n")
    out.write("|---|---:|---:|\n")
    for firma, (cnt, sm) in sorted_firmen:
        out.write(f"| {firma} | {cnt} | {format_eur(sm)} |\n")


def main():
    parser = argparse.ArgumentParser(description='BPLUS-NG API-Export Analyse')
    parser.add_argument('csv_file', help='Pfad zur API-Export CSV-Datei')
    parser.add_argument('--firma', help='Filter nach Firma (Teilstring, case-insensitive)')
    parser.add_argument('--status', help='Filter nach Status (Teilstring, case-insensitive)')
    parser.add_argument('--ea', help='Filter nach EA-Titel (Teilstring, case-insensitive)')
    parser.add_argument('--projekt', help='Filter nach Projektfamilie (Teilstring, case-insensitive)')
    parser.add_argument('--oe', help='Filter nach OE (Teilstring, case-insensitive)')
    parser.add_argument('--top', type=int, default=None, help='Nur Top-N Firmen anzeigen')
    parser.add_argument('--output', help='Pfad zur Ausgabedatei (.md). Default: userdata/sessions/')
    args = parser.parse_args()

    data = load_csv(args.csv_file)
    filtered = filter_rows(data, firma=args.firma, status=args.status,
                           ea=args.ea, projekt=args.projekt, oe=args.oe)

    # Ausgabedatei bestimmen
    if args.output:
        out_path = args.output
    else:
        workspace = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        tmp_dir = os.path.join(workspace, 'userdata', 'sessions')
        os.makedirs(tmp_dir, exist_ok=True)
        label = args.firma or args.ea or args.status or args.projekt or args.oe or 'gesamt'
        label = label.lower().replace(' ', '_')[:20]
        out_path = os.path.join(tmp_dir, f"{date.today().strftime('%Y%m%d')}_bplus_{label}.md")

    out = StringIO()

    filter_info = []
    if args.firma:
        filter_info.append(f"Firma='{args.firma}'")
    if args.status:
        filter_info.append(f"Status='{args.status}'")
    if args.ea:
        filter_info.append(f"EA='{args.ea}'")
    if args.projekt:
        filter_info.append(f"Projekt='{args.projekt}'")
    if args.oe:
        filter_info.append(f"OE='{args.oe}'")
    filter_str = f" (Filter: {', '.join(filter_info)})" if filter_info else ""

    out.write(f"## BPLUS-NG Auswertung{filter_str}\n")
    out.write(f"Gesamt: {len(data)} | Gefiltert: {len(filtered)}\n")

    if not filtered:
        out.write("\nKeine Treffer gefunden.\n")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(out.getvalue())
        print(out_path)
        sys.exit(0)

    if args.firma or args.ea or args.projekt:
        out.write(f"\n### Einzelvorgaenge\n")
        print_vorgaenge(filtered, out)

        if len(set(r.get('dev_order', '') for r in filtered)) > 1:
            out.write(f"\n### Nach EA\n")
            print_by_ea(filtered, out)

    out.write(f"\n### Nach Status\n")
    print_by_status(filtered, out)

    if not args.firma:
        out.write(f"\n### Nach Firma\n")
        print_by_firma(filtered, out, top_n=args.top)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out.getvalue())
    print(out_path)


if __name__ == '__main__':
    main()
