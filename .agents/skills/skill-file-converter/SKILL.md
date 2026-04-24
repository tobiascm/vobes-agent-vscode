---
name: skill-file-converter
description: "Lokale Dateien nach PDF (via Office COM oder Markdown via markdown-pdf) oder Markdown (via lightrag LLM-Pipeline) konvertieren. Trigger: Datei konvertieren, PPTX nach PDF, Word nach PDF, Excel nach PDF, Markdown nach PDF, md-to-pdf, Datei nach Markdown, Dokument in Markdown umwandeln."
---

# Skill: File Converter

Konvertiert **lokale Dateien** nach **PDF** oder **Markdown**.

- **→ PDF:** Windows COM-Automation (PowerPoint, Word, Excel)
- **Markdown → PDF:** `markdown-pdf` (MarkdownPdf + Section)
- **→ Markdown (LLM):** Delegiert an `lightrag_test/scripts/convert_to_markdown.py` (Docling + Claude)
- **→ Markdown (non-LLM):** Lokale Extraktion via `file_parsers.py` (python-pptx, openpyxl, python-docx, pdfplumber)

> **Scripts:** `.agents/skills/skill-file-converter/scripts/`
> - `file_converter.py` — CLI-Router (Einstiegspunkt)
> - `file_parsers.py` — Format-Parser fuer non-LLM Extraktion
> - `file_llm_converter.py` — LLM-Pipeline + COM-Automation

## Wann verwenden?

- Der User moechte eine **lokale Datei** nach PDF oder Markdown konvertieren
- Der User hat ein PPTX/DOCX/XLSX und braucht ein PDF daraus
- Der User hat Markdown und braucht daraus ein PDF
- Der User moechte den Inhalt einer Datei als Markdown extrahieren (LLM-gestuetzt oder schnell ohne LLM)
- Der User fragt: "Konvertiere diese Datei nach PDF", "Markdown nach PDF", "Mach daraus ein Markdown"

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| Datei aus SharePoint/OneDrive **lesen** | `$skill-m365-file-reader` |
| Datei in SharePoint **suchen** | `$skill-m365-copilot-file-search` |

## Unterstuetzte Formate

### → PDF (COM-Automation)

| Eingabe | Office-App |
|---------|------------|
| `.pptx`, `.ppt` | PowerPoint |
| `.docx`, `.doc` | Word |
| `.xlsx`, `.xls`, `.xlsm`, `.xltx`, `.xltm` | Excel |

### Markdown → PDF (markdown-pdf)

| Eingabe | Methode |
|---------|---------|
| `.md`, `.markdown` | markdown-pdf (`MarkdownPdf`, `Section`) |

### → Markdown (LLM via lightrag_test)

PDF, DOCX, XLSX, PPTX, ODT, ODP, TXT, XML, PNG, JPG, TIFF, BMP, WEBP, HTML und mehr.

> **Hinweis:** LLM-basierte Konvertierung (insbesondere Bilder) kann bis zu **3 Minuten** dauern.

### → Markdown (non-LLM via file_parsers)

| Eingabe | Methode |
|---------|---------|
| `.pptx` | python-pptx (Text, Tabellen, Notes pro Folie) |
| `.docx` | python-docx (Volltext mit Ueberschriften) |
| `.xlsx`, `.xls` | openpyxl (alle Sheets als CSV) |
| `.pdf` | pdfplumber (Text-Extraktion) |
| `.csv` | Erste 200 Zeilen als Markdown-Tabelle |
| `.txt`, `.md`, `.json`, `.xml`, `.html` | Plaintext |
| Bilder | Metadaten (Groesse, Modus) |

> **Hinweis:** Non-LLM extrahiert keinen Text aus Bildern in PPTX-Folien und kein SmartArt.

## Voraussetzungen

1. **PDF (to-pdf):** Microsoft Office (PowerPoint, Word, Excel) muss installiert sein
2. **Markdown (LLM):** `C:\Daten\Python\lightrag_test` muss vorhanden sein (LLM-Pipeline)
3. **Markdown (non-LLM):** Keine externe Abhaengigkeit (python-pptx, openpyxl, python-docx in pyproject.toml)
4. **Markdown → PDF:** `markdown-pdf` (bereits in pyproject.toml)
5. **Python-Pakete:** `pywin32` (bereits in pyproject.toml)

## CLI-Befehle

### Datei → PDF

```bash
python .agents/skills/skill-file-converter/scripts/file_converter.py to-pdf INPUT [OUTPUT]
```

Ohne OUTPUT wird die PDF neben die Eingabedatei gelegt (`<stem>.pdf`).

### Markdown → PDF

```bash
python .agents/skills/skill-file-converter/scripts/file_converter.py md-to-pdf INPUT.md [OUTPUT.pdf]
```

Optionale Flags:
- `--title "..."` — PDF-Titel-Metadatum
- `--toc-level 3` — Bookmark/TOC-Tiefe (default: 2)
- `--no-optimize` — PDF-Optimierung deaktivieren
- `--css pfad\style.css` — CSS-Anpassung aus Datei laden

> **Hinweis:** Interne Anker-Links (`[Text](#heading)`) werden vor der Konvertierung
> automatisch gestripped, da pymupdf Anchor-HREFs URL-encoded aber Heading-IDs als
> raw UTF-8 behaelt (Umlaut-Mismatch). Das PDF-TOC via `--toc-level` ersetzt sie.

Ohne OUTPUT wird die PDF neben die Markdown-Datei gelegt (`<stem>.pdf`).

### Datei → Markdown

```bash
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown INPUT [OUTPUT]
```

Optionale Flags:
- `--no-llm` — Lokale Extraktion ohne LLM (PPTX, DOCX, XLSX, PDF, CSV, ...)
- `--no-llm-pdf` — Nur PDF ohne LLM extrahieren (pymupdf4llm statt Claude)
- `--all-sheets` — Excel: alle Worksheets einzeln konvertieren
- `--prompt "..."` — Custom-Prompt fuer Bild-Konvertierung (ersetzt den Standard-Prompt)
- `--clipboard` — Bild aus Windows-Zwischenablage statt Eingabedatei verwenden (INPUT entfaellt)

Ohne OUTPUT wird die Markdown-Datei neben die Eingabedatei gelegt (`<stem>.md`).

## Exit-Codes

| Code | Bedeutung |
|------|-----------|
| `0` | Erfolg |
| `1` | Fehler |
| `2` | Format nicht unterstuetzt |
| `3` | Abhaengigkeit fehlt (Office nicht installiert, lightrag_test oder markdown-pdf nicht gefunden) |

## Typischer Ablauf

```bash
# PPTX → PDF
python .agents/skills/skill-file-converter/scripts/file_converter.py to-pdf C:\Users\VWRR6B4\Downloads\praesentation.pptx

# Markdown → PDF
python .agents/skills/skill-file-converter/scripts/file_converter.py md-to-pdf bericht.md bericht.pdf --title "Bericht" --toc-level 2

# DOCX → Markdown (LLM-gestuetzt)
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown C:\Users\VWRR6B4\Downloads\bericht.docx

# PPTX → Markdown (schnell, ohne LLM)
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown praesentation.pptx --no-llm

# PDF → Markdown ohne LLM
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown bericht.pdf --no-llm-pdf

# Bild → Markdown mit Custom-Prompt (z.B. ONG-Screenshot)
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown screenshot.png --prompt "Extrahiere alle Tabellenwerte und Bauteilnummern aus dem Screenshot"

# Clipboard-Bild → Markdown (Screenshot aus Zwischenablage)
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown --clipboard

# Clipboard-Bild → Markdown mit Custom-Prompt
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown --clipboard --prompt "Extrahiere nur die Tabelle"

# Clipboard-Bild → Markdown mit explizitem Output-Pfad
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown --clipboard ergebnis.md
```
