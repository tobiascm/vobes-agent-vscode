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
from collections import defaultdict

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
    """Zahl als Euro-Betrag formatieren"""
    return f"{val:,.2f} \u20ac".replace(',', 'X').replace('.', ',').replace('X', '.')


def display_status(row):
    """Erzeugt lesbaren Status aus workFlowStatus + status"""
    wf = row.get('workFlowStatus', '')
    sub = row.get('status', '').strip()
    base = STATUS_MAP.get(wf, wf)
    if wf == 'WF_In_Planen_BM' and sub:
        return f"{base}: {sub}"
    return base


def load_csv(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f, delimiter=';'))


def filter_rows(data, firma=None, status=None, ea=None, projekt=None, oe=None):
    result = data
    if firma:
        q = firma.lower()
        result = [r for r in result if q in r.get('company', '').lower()]
    if status:
        q = status.lower()
        result = [r for r in result if q in display_status(r).lower()]
    if ea:
        q = ea.lower()
        result = [r for r in result if q in r.get('eaTitel', '').lower()]
    if projekt:
        q = projekt.lower()
        result = [r for r in result if q in r.get('projektfamilie', '').lower()]
    if oe:
        q = oe.lower()
        result = [r for r in result if q in r.get('orgUnitName', '').lower()]
    return result


def print_vorgaenge(rows):
    total = 0
    for r in rows:
        wert = parse_wert(r.get('plannedValue', ''))
        total += wert
        konzept = r.get('concept', '?').strip()
        ea = r.get('eaTitel', '').strip()[:35]
        titel = r.get('title', '').strip()[:50]
        print(f"  Konzept {konzept:>8}"
              f" | EA: {ea:35}"
              f" | Status: {display_status(r):35}"
              f" | Wert: {format_eur(wert):>14}"
              f" | {titel}")
    print(f"\n  SUMME: {format_eur(total)}  ({len(rows)} Vorgaenge)")
    return total


def print_by_status(rows):
    status_sums = defaultdict(lambda: [0, 0.0])
    for r in rows:
        st = display_status(r)
        wert = parse_wert(r.get('plannedValue', ''))
        status_sums[st][0] += 1
        status_sums[st][1] += wert
    for st, (cnt, sm) in sorted(status_sums.items()):
        print(f"  {st:45} | {cnt:3} Vorgaenge | {format_eur(sm):>16}")


def print_by_firma(rows, top_n=None):
    firmen = defaultdict(lambda: [0, 0.0])
    for r in rows:
        firma = r.get('company', '').strip()
        if firma:
            wert = parse_wert(r.get('plannedValue', ''))
            firmen[firma][0] += 1
            firmen[firma][1] += wert
    sorted_firmen = sorted(firmen.items(), key=lambda x: -x[1][1])
    if top_n:
        sorted_firmen = sorted_firmen[:top_n]
    for firma, (cnt, sm) in sorted_firmen:
        print(f"  {firma:55} | {cnt:3} Vorgaenge | {format_eur(sm):>16}")


def main():
    parser = argparse.ArgumentParser(description='BPLUS-NG API-Export Analyse')
    parser.add_argument('csv_file', help='Pfad zur API-Export CSV-Datei')
    parser.add_argument('--firma', help='Filter nach Firma (Teilstring, case-insensitive)')
    parser.add_argument('--status', help='Filter nach Status (Teilstring, case-insensitive)')
    parser.add_argument('--ea', help='Filter nach EA-Titel (Teilstring, case-insensitive)')
    parser.add_argument('--projekt', help='Filter nach Projektfamilie (Teilstring, case-insensitive)')
    parser.add_argument('--oe', help='Filter nach OE (Teilstring, case-insensitive)')
    parser.add_argument('--top', type=int, default=None, help='Nur Top-N Firmen anzeigen')
    args = parser.parse_args()

    data = load_csv(args.csv_file)
    filtered = filter_rows(data, firma=args.firma, status=args.status,
                           ea=args.ea, projekt=args.projekt, oe=args.oe)

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

    print(f"=== BPLUS-NG API-Auswertung{filter_str} ===")
    print(f"Gesamt Datensaetze: {len(data)} | Gefiltert: {len(filtered)}")

    if not filtered:
        print("\nKeine Treffer gefunden.")
        sys.exit(0)

    if args.firma or args.ea or args.projekt:
        print(f"\n--- Vorgaenge ---")
        print_vorgaenge(filtered)

    print(f"\n--- Aufschluesselung nach Status ---")
    print_by_status(filtered)

    print(f"\n--- Aufschluesselung nach Firma ---")
    print_by_firma(filtered, top_n=args.top)


if __name__ == '__main__':
    main()
