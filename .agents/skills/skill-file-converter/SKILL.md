---
name: skill-file-converter
description: "Lokale Dateien nach PDF (via Office COM) oder Markdown (via lightrag LLM-Pipeline) konvertieren. Trigger: Datei konvertieren, PPTX nach PDF, Word nach PDF, Excel nach PDF, Datei nach Markdown, Dokument in Markdown umwandeln."
---

# Skill: File Converter

Konvertiert **lokale Dateien** nach **PDF** oder **Markdown**.

- **→ PDF:** Windows COM-Automation (PowerPoint, Word, Excel)
- **→ Markdown:** Delegiert an `lightrag_test/scripts/convert_to_markdown.py` (LLM-basiert)

> **Script:** `.agents/skills/skill-file-converter/scripts/file_converter.py`

## Wann verwenden?

- Der User moechte eine **lokale Datei** nach PDF oder Markdown konvertieren
- Der User hat ein PPTX/DOCX/XLSX und braucht ein PDF daraus
- Der User moechte den Inhalt einer Datei als Markdown extrahieren (LLM-gestuetzt)
- Der User fragt: "Konvertiere diese Datei nach PDF", "Mach daraus ein Markdown"

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

### → Markdown (LLM via lightrag_test)

PDF, DOCX, XLSX, PPTX, ODT, ODP, TXT, XML, PNG, JPG, TIFF, BMP, WEBP, HTML und mehr.

## Voraussetzungen

1. **PDF:** Microsoft Office (PowerPoint, Word, Excel) muss installiert sein
2. **Markdown:** `C:\Daten\Python\lightrag_test` muss vorhanden sein (LLM-Pipeline)
3. **Python-Pakete:** `pywin32` (bereits in pyproject.toml)

## CLI-Befehle

### Datei → PDF

```bash
python .agents/skills/skill-file-converter/scripts/file_converter.py to-pdf INPUT [OUTPUT]
```

Ohne OUTPUT wird die PDF neben die Eingabedatei gelegt (`<stem>.pdf`).

### Datei → Markdown

```bash
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown INPUT [OUTPUT]
```

Optionale Flags:
- `--no-llm-pdf` — PDF-Extraktion ohne LLM (pymupdf4llm statt Claude)
- `--all-sheets` — Excel: alle Worksheets einzeln konvertieren

Ohne OUTPUT wird die Markdown-Datei neben die Eingabedatei gelegt (`<stem>.md`).

## Exit-Codes

| Code | Bedeutung |
|------|-----------|
| `0` | Erfolg |
| `1` | Fehler |
| `2` | Format nicht unterstuetzt |
| `3` | Abhaengigkeit fehlt (Office nicht installiert, lightrag_test nicht gefunden) |

## Typischer Ablauf

```bash
# PPTX → PDF
python .agents/skills/skill-file-converter/scripts/file_converter.py to-pdf C:\Users\VWRR6B4\Downloads\praesentation.pptx

# DOCX → Markdown (LLM-gestuetzt)
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown C:\Users\VWRR6B4\Downloads\bericht.docx

# PDF → Markdown ohne LLM
python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown bericht.pdf --no-llm-pdf
```
