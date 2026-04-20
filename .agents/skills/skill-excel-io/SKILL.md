---
name: skill-excel-io
description: Excel (.xlsx) lesen, schreiben, bearbeiten per CLI. Nutze diesen Skill bei Excel-Dateien — Zellen lesen, Werte aendern, Formatierung (bold, Farbe, Border, Number-Format) setzen, Sheets schreiben, Tabellen extrahieren.
---

# Skill: Excel I/O

CLI-Tool `excel_cli.py` fuer alle gaengigen Excel-Operationen. Token-schonend — Output als Markdown/JSON/CSV auf stdout, keine Inline-openpyxl-Programmierung noetig.

## Wann verwenden

- Excel-Datei lesen (ein Sheet, Range oder alle Sheets)
- Zellwerte aendern, Formatierung setzen (bold, Farbe, Border, Number-Format)
- Daten aus CSV/JSON in neue oder bestehende .xlsx schreiben
- Struktur einer .xlsx inspizieren (Sheets, Groessen)

## Workflow

```bash
# Struktur pruefen
python .agents/skills/skill-excel-io/scripts/excel_cli.py info datei.xlsx

# Lesen (Default: Markdown-Tabelle auf stdout)
python .agents/skills/skill-excel-io/scripts/excel_cli.py read datei.xlsx --sheet Daten
python .agents/skills/skill-excel-io/scripts/excel_cli.py read datei.xlsx --sheet all --as json
python .agents/skills/skill-excel-io/scripts/excel_cli.py read datei.xlsx --range A1:D10

# Bearbeiten — Wert und/oder Format
python .agents/skills/skill-excel-io/scripts/excel_cli.py edit datei.xlsx --cell B2 --value 42
python .agents/skills/skill-excel-io/scripts/excel_cli.py edit datei.xlsx --cell A1 \
    --value "Titel" --bold --font-size 14 --bg D9E2F3 --align center
python .agents/skills/skill-excel-io/scripts/excel_cli.py edit datei.xlsx \
    --cell B2:D5 --border thin --number-format "#,##0.00"

# Bulk-Edits (empfohlen fuer viele Aenderungen)
python .agents/skills/skill-excel-io/scripts/excel_cli.py edit datei.xlsx \
    --batch ops.json --output neu.xlsx

# Schreiben aus CSV/JSON
python .agents/skills/skill-excel-io/scripts/excel_cli.py write neu.xlsx \
    --from daten.csv --sheet Daten
```

## Style-Flags (edit)

| Flag | Effekt |
|---|---|
| `--bold`, `--italic` | Schrift fett/kursiv |
| `--font-size N` | Schriftgroesse |
| `--color RRGGBB` | Schriftfarbe (Hex ohne `#`) |
| `--bg RRGGBB` | Hintergrundfarbe |
| `--align left\|center\|right` | Horizontal |
| `--valign top\|center\|bottom` | Vertikal |
| `--wrap` | Textumbruch |
| `--border thin\|medium\|thick\|none` + `--border-color RRGGBB` | Rahmen rundum |
| `--number-format FMT` | z.B. `"#,##0.00"`, `"0%"`, `"yyyy-mm-dd"` |
| `--style-json JSON` | Komplettes Style-Dict (wird mit Flags gemergt) |

Styles sind **additiv** — nicht gesetzte Properties bleiben unveraendert. `--cell A1:C3` wendet Value und/oder Style auf den ganzen Bereich an.

## Batch-Format (ops.json)

```json
[
  {"cell": "A1", "value": "Header", "style": {"bold": true, "bg": "D9E2F3"}},
  {"cell": "B2:D2", "style": {"border": "thin", "align": "right", "number-format": "#,##0"}}
]
```

Keys im `style`-Dict: `bold`, `italic`, `size`, `color`, `fill` (oder `bg`), `align`, `valign`, `wrap`, `border`, `border-color`, `number-format`. Alternativ `"font": {...}` fuer verschachtelte Font-Props.

## Write — Eingabeformate

- **CSV:** erste Zeile = Header, Autocast (Int/Float/Formel `=SUM(...)`).
- **JSON-Liste aus Dicts:** Keys = Header, Values = Zeilen.
- **JSON-Liste aus Listen:** direkt als Zeilen.
- **JSON-Dict of sheets:** `--sheet NAME` waehlt welchen Key.

`--append` haengt an vorhandenes Sheet; sonst wird ueberschrieben. Existiert die Zieldatei nicht, wird sie neu angelegt.

## Hinweise

- **Safety:** `--output NEW.xlsx` schreibt in neue Datei, Original bleibt. Ohne `--output` wird in-place gespeichert.
- **Formeln:** Lesen liefert zuletzt berechnete Werte (`data_only=True`). Schreiben akzeptiert `=SUM(A1:A5)` als Formel.
- **Grosse Dateien:** `read`/`info` nutzen `read_only` — RAM-schonend.
- **Absolute Pfade bevorzugen**, insbesondere bei `--from` und `--output`.

## Abhaengigkeiten

`openpyxl` (bereits im Repo genutzt).
