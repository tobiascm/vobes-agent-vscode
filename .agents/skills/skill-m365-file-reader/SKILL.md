---
name: skill-m365-file-reader
description: "Dateien aus SharePoint und OneDrive ueber die Graph API lesen. Unterstuetzte Formate: PPTX (Text pro Folie), XLSX (als CSV), DOCX (Volltext), PDF (Text-Extraktion), Bilder (Download + Metadaten). Trigger: Datei aus SharePoint lesen, OneDrive-Datei oeffnen, PPTX-Inhalt anzeigen, Excel aus SharePoint als CSV, Bild aus OneDrive herunterladen, was steht in der Datei im SharePoint, M365 Datei lesen."
---

# Skill: M365 File Reader (Graph API)

Liest **Dateien aus SharePoint und OneDrive** ueber die Graph API und gibt den Inhalt als Text aus — ohne Browser, ohne Download-Dialog.

> **Script:** `scripts/m365_file_reader.py`, Pfad relativ zum **Repo-Root**

## Wann verwenden?

- Der User moechte den **Inhalt einer Datei** aus SharePoint/OneDrive lesen
- Der User hat eine **SharePoint-URL** und will wissen, was drin steht
- Der User moechte eine **PPTX, XLSX, DOCX, PDF oder ein Bild** aus M365 verarbeiten
- Der User fragt: "Was steht in der Datei X?", "Lies die Praesentation aus dem SharePoint"
- Nach einer `$skill-m365-copilot-file-search` den gefundenen Treffer **tatsaechlich lesen**

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| Datei in SharePoint/OneDrive **suchen** | `$skill-m365-copilot-file-search` |
| Confluence/Jira lesen | `local_rag` oder `mcp-atlassian` |
| Lokale Dateien lesen | `read_file` Tool direkt |
| Webseiten oeffnen/navigieren | `$skill-browse-intranet` |

## Unterstuetzte Formate

| Format | Ausgabe |
|--------|---------|
| **.pptx** | Text pro Folie (inkl. Tabellen und Notes) |
| **.xlsx / .xls** | Alle Sheets als CSV (Semikolon-getrennt), ausgegeben als einzelne `### Sheet:`-Abschnitte auf stdout |
| **.docx** | Volltext mit Ueberschriften (Heading 1/2/3) |
| **.pdf** | Text pro Seite (benoetigt `pdfplumber`) |
| **.png/.jpg/.jpeg/.gif/.bmp/.tiff/.svg/.webp** | Auto-Download nach `userdata/tmp/` + Bild-Metadaten (Abmessungen, Modus) |
| **.csv** | Erste 200 Zeilen als Markdown-Tabelle |
| **.txt/.md/.json/.xml/.html** | Plaintext |

## Voraussetzungen

1. **Graph API Token** — wird zentral ueber `scripts/m365_copilot_graph_token.py` aufgeloest
2. **Python-Pakete:** `requests`, `python-pptx`, `openpyxl`, `python-docx` (alle vorinstalliert)
3. **Optional:** `pdfplumber` (fuer PDF), `Pillow` (fuer Bild-Dimensionen)

## Workflow

### Schritt 1: Datei lesen

Es gibt drei Eingabe-Formate:

**A) SharePoint/OneDrive URL:**
```bash
python scripts/m365_file_reader.py read "https://volkswagengroup.sharepoint.com/.../datei.pptx"
```

**B) Dateiname (wird automatisch gesucht):**
```bash
python scripts/m365_file_reader.py read "BN-SK_Abkündigung_CHD-LD_Toolsuite_20260316_tcm.pptx"
```

Hinweis: Bei exaktem Dateinamen kann `read "<dateiname>"` die Datei direkt finden; ein separater `search`-Aufruf ist dann nicht erforderlich.

**C) driveId|itemId (aus vorheriger Suche):**
```bash
python scripts/m365_file_reader.py read "b!MVdXi...|01XAS2D2..."
```

### Exit-Codes

- **Exit 0** → Inhalt wird auf stdout ausgegeben. Fertig.
- **Exit 2** → `TOKEN_EXPIRED`. Weiter zu Schritt 2.
- **Exit 1** → Sonstiger Fehler.

### Schritt 2: Token erneuern (nur bei Exit 2)

Der File Reader nutzt denselben zentralen Resolver wie die Copilot File Search:

```bash
python scripts/m365_copilot_graph_token.py ensure
python scripts/m365_file_reader.py read "URL_ODER_NAME"
```

Fuer einen frischen Token:

```bash
python scripts/m365_copilot_graph_token.py ensure --force
python scripts/m365_file_reader.py read "URL_ODER_NAME"
```

### Optionaler Download

Datei zusaetzlich lokal speichern:
```bash
python scripts/m365_file_reader.py read "URL" --download "userdata/tmp/datei.pptx"
```

Bilder werden automatisch nach `userdata/tmp/` gespeichert (ohne `--download`).

### Datei vorher suchen

Falls die genaue URL nicht bekannt ist, zuerst suchen:
```bash
python scripts/m365_file_reader.py search "Dateiname oder Stichwort"
```

Liefert eine Tabelle mit Name, Groesse, driveId, itemId.

---

## Typischer Ablauf: Copilot Search → File Reader

```bash
# 1. Datei finden
python scripts/copilot_search.py search "Abkündigung LDorado pptx"

# 2. URL aus Ergebnis nehmen und lesen
python scripts/m365_file_reader.py read "https://volkswagengroup.sharepoint.com/.../datei.pptx"
```

## Script-Befehle (Referenz)

| Befehl | Zweck |
|--------|-------|
| `python scripts/m365_file_reader.py search "query"` | Datei suchen (Graph Search API) |
| `python scripts/m365_file_reader.py read URL` | Datei lesen (URL, Name oder driveId\|itemId) |
| `python scripts/m365_file_reader.py read URL --download PFAD` | Lesen + lokal speichern |
