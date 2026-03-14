import csv

with open(r'c:\Daten\Python\vobes_agent_vscode\userdata\tmp\20260314_BPlus_Export_EKEK1.csv', 'r', encoding='utf-8') as f:
    first = f.read(3)
    has_bom = first.startswith('\ufeff')
    f.seek(0)
    reader = csv.DictReader(f)
    rows = list(reader)
    cols = list(rows[0].keys())

print('=== QUALITAETS-CHECK ===')
print(f'BOM vorhanden: {has_bom}')
print(f'Spalten ({len(cols)}): {cols}')
print(f'Zeilen: {len(rows)}')
print()

ws_ea = sum(1 for r in rows if r['ea'] != r['ea'].strip())
ws_title = sum(1 for r in rows if r['title'] != r['title'].strip())
print(f'ea mit trailing WS: {ws_ea}')
print(f'title mit trailing WS: {ws_title}')

nl = sum(1 for r in rows if '\n' in r.get('bm_text', ''))
print(f'bm_text mit Newlines: {nl}')

punkt = sum(1 for r in rows if '.' in r['planned_value'])
komma = sum(1 for r in rows if ',' in r['planned_value'])
print(f'planned_value mit Punkt: {punkt}')
print(f'planned_value mit Komma: {komma}')

try:
    vals = [int(r['planned_value']) for r in rows]
    print('planned_value alle Ganzzahl: JA')
except Exception:
    print('planned_value alle Ganzzahl: NEIN')
    for r in rows[:5]:
        print(f'  Beispiel: {repr(r["planned_value"])}')

keine = sum(1 for r in rows if r['projektfamilie'] == 'KEINE')
print(f'projektfamilie=KEINE: {keine}')

# Status-Check
statuses = set(r['status'] for r in rows)
print(f'\nStatus-Werte: {sorted(statuses)}')

print('\n--- Beispielzeile ---')
for k, v in rows[0].items():
    print(f'  {k}: {repr(v)}')
