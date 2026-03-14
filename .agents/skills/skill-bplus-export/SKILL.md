---
name: skill-bplus-export
description: Export aus BPLUS-NG (Vorgangsuebersicht, Abrufuebersicht, BM-Uebersicht) per Playwright herunterladen. Nutze diesen Skill wenn der User eine BPLUS-Uebersicht als Excel oder CSV exportieren moechte.
---

# Skill: BPLUS-NG Export per Playwright

Dieser Skill beschreibt den Workflow, um Uebersichten aus **BPLUS-NG/EK** (Konzeptuebersicht / Vorgangsuebersicht / Abrufuebersicht / BM-Uebersicht) als CSV- oder Excel-Datei herunterzuladen.

## Kontext

- Der Export umfasst ausschliesslich das Team **EKEK/1**.
- Ersteller im Team: **Bachmann Armin**, **Bartels Timo**, **Junge Christian**.

## Wann verwenden?

- Der User moechte eine Uebersicht aus BPLUS-NG als CSV oder Excel exportieren
- Der User erwaehnt BPLUS, Vorgangsuebersicht, Abrufuebersicht, BM-Uebersicht oder Konzeptuebersicht
- Der User moechte Daten aus dem Beschaffungstool BPLUS herunterladen

## Voraussetzungen

- **MCP Playwright** muss konfiguriert und aktiv sein
- Der User muss im VW-Netzwerk authentifiziert sein (SSO)
- KEINE Screenshots/Bilder herunterladen oder anschauen (Performance)

## URLs

| Uebersicht | URL |
|---|---|
| Konzeptuebersicht (BTL) | `https://bplus-ng-mig.r02.vwgroup.com/ek/btl` |

> Hinweis: Die URL kann sich aendern (z.B. Wechsel von `-mig` zu Produktion). Falls die Seite nicht laedt, den User nach der aktuellen URL fragen.

## Seitenstruktur (Accessibility-Tree)

Die geladene Seite hat folgende relevante Elemente:

### Header
- Sprache umschalten: Buttons **DE** / **EN**
- User-Icon oben rechts

### Filter-Bereich (chip area / listbox)
- **Jahr-Dropdown** (`combobox "Jahr"`): Standardmaessig aktuelles Jahr
- **Filter-Chips** in einer `listbox "chip area"`:
  - `option "EKEK/1-Export"` — OE-Vorfilter (Organisationseinheit)
  - `option "Status"` — Status-Filter (z.B. nur bestimmte Status anzeigen)
  - `option "OE"` — OE-Filter
  - Jeder Chip hat ein **Icon-Element** (letztes Kind-Element des Chips) zum **Entfernen** des Filters

### Aktions-Buttons
- `button "Meine Filter"` — Gespeicherte Filtersets
- `button "+ Konzept"` — Neues Konzept anlegen
- `button "31 Ausgeblendet"` — Spalten ein-/ausblenden
- `button "Export"` — **Export-Dropdown** oeffnen

### Export-Dropdown
Nach Klick auf den **Export**-Button erscheint eine `list` mit:
- `listitem` → `"Export als Excel"` (HTML-ID: `#btnExportExcel`)
- `listitem` → `"Export als CSV"`

### Datentabelle (grid)
- Spalten: ACTION, OP, Titel, Konzept, Status, Wert, OE, Firma, Ersteller, BM-Nr., Rahmen-AZ, Proj. Fam., EA-Nr., EA, BM-Text
- Summenzeile am Ende (z.B. `∑ 4.508.527,66`)

## Workflow: Export mit optionaler Filter-Aenderung

### Schritt 1: Seite laden

```
browser_navigate → https://bplus-ng-mig.r02.vwgroup.com/ek/btl
browser_wait_for → time: 4 (Sekunden warten bis Seite vollstaendig geladen)
```

### Schritt 2: Snapshot pruefen

```
browser_snapshot
```

Pruefen ob:
- Die Tabelle mit Daten geladen ist (Zeilen in `rowgroup` sichtbar)
- Die Filter-Chips sichtbar sind

### Schritt 3: Filter anpassen (optional)

Falls der User bestimmte Filter entfernen moechte (z.B. Status-Filter):

1. Den gewuenschten Filter-Chip in der `listbox "chip area"` finden (z.B. `option "Status"`)
2. Das **Icon-Element** (letztes Kind-Element innerhalb des Chips) anklicken — das ist der Entfernen-Button
3. Warten bis die Tabelle neu geladen hat (1-2 Sekunden)
4. Snapshot pruefen ob Filter entfernt wurde (Chip sollte verschwunden sein)

**Wichtig:** Den Chip selbst anklicken oeffnet/aktiviert ihn nur. Das **Icon-Element** (generic mit leerem Text oder cancel-Symbol) innerhalb des Chips **entfernt** den Filter.

Beispiel-Sequenz zum Entfernen des Status-Filters:
```
# Chip finden: option "Status" mit ref=eXXX
# Icon (letztes Kind) finden: generic ref=eYYY
browser_click → ref=eYYY (das Icon, NICHT den Chip selbst)
```

### Schritt 4: Export ausloesen

Standard ist **CSV**. Falls der User explizit Excel verlangt, stattdessen "Export als Excel" waehlen.

```
browser_click → Export-Button (button "Export")
# Warten bis Dropdown erscheint
browser_click → "Export als CSV" (listitem mit Text "Export als CSV")
# Alternativ fuer Excel:
# browser_click → "Export als Excel" (listitem mit Text "Export als Excel")
```

### Schritt 5: Download pruefen und nach userdata\tmp verschieben

```
# 3-4 Sekunden warten
browser_wait_for → time: 4

# Neueste CSV-Datei im Downloads-Ordner finden (bei Excel: *.xlsx):
$file = Get-ChildItem "$env:USERPROFILE\Downloads" -Filter "*.csv" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$file | Format-Table Name, LastWriteTime -AutoSize

# Nach userdata\tmp verschieben und umbenennen (YYYYMMDD_BPlus_Export_EKEK1.csv):
$dest = "<WORKSPACE>\userdata\tmp"
if (!(Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
$newName = "$(Get-Date -Format 'yyyyMMdd')_BPlus_Export_EKEK1.csv"
Move-Item -Path $file.FullName -Destination "$dest\$newName" -Force
Write-Host "Verschoben nach: $dest\$newName"
```

> **Wichtig:** `<WORKSPACE>` durch den tatsaechlichen Workspace-Pfad ersetzen (z.B. `c:\Daten\Python\vobes_agent_vscode`).

Die Datei wird umbenannt nach dem Schema:
```
YYYYMMDD_BPlus_Export_EKEK1.csv
# Beispiel: 20260314_BPlus_Export_EKEK1.csv
```

## Haeufige Probleme und Loesungen

| Problem | Loesung |
|---|---|
| Seite laedt nicht / leerer Snapshot | Laenger warten (5-8 Sek.) oder User nach Netzwerkstatus fragen |
| Filter-Chip laesst sich nicht entfernen | Das Icon-Element innerhalb des Chips anklicken, nicht den Chip selbst |
| Export-Dropdown erscheint nicht | Export-Button erneut klicken |
| Keine neue Datei im Downloads-Ordner | Laenger warten, ggf. nochmal exportieren |
| Datei nicht in userdata\tmp | Pruefen ob Move-Item fehlerfrei lief, Pfad pruefen |
| Andere Uebersicht gewuenscht | User nach konkreter URL fragen |

## Schritt 6: CSV auswerten (optional)

Im Skill-Verzeichnis liegt das Script `analyze_bplus.py` zur universellen Auswertung der CSV-Daten.

**Pfad:** `<WORKSPACE>/.agents/skills/skill-bplus-export/analyze_bplus.py`

### Verwendung

```powershell
# Gesamtuebersicht aller Firmen (sortiert nach Wert):
python "<WORKSPACE>\.agents\skills\skill-bplus-export\analyze_bplus.py" "<WORKSPACE>\userdata\tmp\ExportedData.csv"

# Nur eine bestimmte Firma (Teilstring, case-insensitive):
python "<WORKSPACE>\.agents\skills\skill-bplus-export\analyze_bplus.py" "<WORKSPACE>\userdata\tmp\ExportedData.csv" --firma 4soft

# Nur bestimmter Status:
python "<WORKSPACE>\.agents\skills\skill-bplus-export\analyze_bplus.py" "<WORKSPACE>\userdata\tmp\ExportedData.csv" --status bestellt

# Kombination Firma + Status:
python "<WORKSPACE>\.agents\skills\skill-bplus-export\analyze_bplus.py" "<WORKSPACE>\userdata\tmp\ExportedData.csv" --firma edag --status bestellt

# Top-N Firmen:
python "<WORKSPACE>\.agents\skills\skill-bplus-export\analyze_bplus.py" "<WORKSPACE>\userdata\tmp\ExportedData.csv" --top 5
```

### Ausgabe

Das Script liefert:
- **Vorgaenge** (bei Firma-Filter): Einzelauflistung mit Konzept, Status, Wert, Titel
- **Aufschluesselung nach Status**: Anzahl und Summe je Status
- **Aufschluesselung nach Firma**: Anzahl und Summe je Firma (absteigend nach Wert)

> **Wichtig:** `<WORKSPACE>` durch den tatsaechlichen Workspace-Pfad ersetzen.

## Beispiel-Interaktion

**User:** "Lade mir die Vorgangsuebersicht aus BPLUS ohne Status-Filter herunter."

**Agent:**
1. Seite laden → `browser_navigate` zur BTL-URL
2. Warten → `browser_wait_for` 4 Sek.
3. Snapshot → Filter-Chips pruefen
4. Status-Filter entfernen → Icon im Status-Chip klicken
5. Export → Export-Button → "Export als CSV"
6. Download pruefen → neueste .csv im Downloads-Ordner finden
7. Nach `userdata\tmp` verschieben → `Move-Item`

**User:** "Wie viel wurde von EDAG bestellt?"

**Agent:**
1. Schritte 1-7 ausfuehren (falls CSV nicht schon vorhanden)
2. Auswertung → `python analyze_bplus.py ExportedData.csv --firma edag --status bestellt`
