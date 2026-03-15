"""
BPLUS-NG Vorgangsuebersicht Analyse-Script
==========================================
Universelles Script zur Auswertung der CSV-Exportdaten aus BPLUS-NG.

Verwendung:
  python analyze_bplus.py <csv-datei> [--firma <suchbegriff>] [--status <suchbegriff>] [--top <n>]

Beispiele:
  python analyze_bplus.py ExportedData.csv                        # Gesamtuebersicht aller Firmen
  python analyze_bplus.py ExportedData.csv --firma 4soft          # Nur 4soft-Vorgaenge
  python analyze_bplus.py ExportedData.csv --firma edag           # Nur EDAG-Vorgaenge
  python analyze_bplus.py ExportedData.csv --status bestellt      # Nur Status "Bestellt"
  python analyze_bplus.py ExportedData.csv --firma 4soft --status bestellt  # Kombination
  python analyze_bplus.py ExportedData.csv --top 5                # Top 5 Firmen
"""

import csv
import argparse
import sys
from collections import defaultdict


def parse_wert(s):
    """Euro-Wert aus BPLUS-CSV parsen (z.B. '37.980,00 €' -> 37980.0)"""
    s = s.replace('\u20ac', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def format_eur(val):
    """Zahl als Euro-Betrag formatieren"""
    return f"{val:,.2f} \u20ac".replace(',', 'X').replace('.', ',').replace('X', '.')


def load_csv(path):
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def filter_rows(data, firma=None, status=None):
    result = data
    if firma:
        firma_lower = firma.lower()
        result = [r for r in result if firma_lower in r.get('Firma', '').lower()]
    if status:
        status_lower = status.lower()
        result = [r for r in result if status_lower in r.get('Status', '').lower()]
    return result


def print_vorgaenge(rows):
    total = 0
    for m in rows:
        wert = parse_wert(m.get('Wert', ''))
        total += wert
        print(f"  Konzept {m.get('Konzept', '?'):>8}"
              f" | Status: {m.get('Status', '?'):42}"
              f" | Wert: {m.get('Wert', '?'):>15}"
              f" | {m.get('Titel', '')[:60]}")
    print(f"\n  SUMME: {format_eur(total)}")
    return total


def print_by_status(rows):
    status_sums = defaultdict(lambda: [0, 0.0])
    for m in rows:
        st = m.get('Status', 'unbekannt')
        wert = parse_wert(m.get('Wert', ''))
        status_sums[st][0] += 1
        status_sums[st][1] += wert
    for st, (cnt, sm) in sorted(status_sums.items()):
        print(f"  {st:45} | {cnt:3} Vorgaenge | {format_eur(sm):>16}")


def print_by_firma(rows, top_n=None):
    firmen = defaultdict(lambda: [0, 0.0])
    for r in rows:
        firma = r.get('Firma', '').strip()
        if firma:
            wert = parse_wert(r.get('Wert', ''))
            firmen[firma][0] += 1
            firmen[firma][1] += wert
    sorted_firmen = sorted(firmen.items(), key=lambda x: -x[1][1])
    if top_n:
        sorted_firmen = sorted_firmen[:top_n]
    for firma, (cnt, sm) in sorted_firmen:
        print(f"  {firma:55} | {cnt:3} Vorgaenge | {format_eur(sm):>16}")


def main():
    parser = argparse.ArgumentParser(description='BPLUS-NG Vorgangsuebersicht Analyse')
    parser.add_argument('csv_file', help='Pfad zur CSV-Datei')
    parser.add_argument('--firma', help='Filter nach Firma (Teilstring, case-insensitive)')
    parser.add_argument('--status', help='Filter nach Status (Teilstring, case-insensitive)')
    parser.add_argument('--top', type=int, default=None, help='Nur Top-N Firmen anzeigen')
    args = parser.parse_args()

    data = load_csv(args.csv_file)
    filtered = filter_rows(data, firma=args.firma, status=args.status)

    filter_info = []
    if args.firma:
        filter_info.append(f"Firma='{args.firma}'")
    if args.status:
        filter_info.append(f"Status='{args.status}'")
    filter_str = f" (Filter: {', '.join(filter_info)})" if filter_info else ""

    print(f"=== BPLUS-NG Auswertung{filter_str} ===")
    print(f"Gesamt Datensaetze: {len(data)} | Gefiltert: {len(filtered)}")

    if not filtered:
        print("\nKeine Treffer gefunden.")
        sys.exit(0)

    if args.firma:
        print(f"\n--- Vorgaenge ---")
        print_vorgaenge(filtered)

    print(f"\n--- Aufschluesselung nach Status ---")
    print_by_status(filtered)

    print(f"\n--- Aufschluesselung nach Firma ---")
    print_by_firma(filtered, top_n=args.top)


if __name__ == '__main__':
    main()
