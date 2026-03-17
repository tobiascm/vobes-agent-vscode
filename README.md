# VOBES Agent VS Code Workspace

VS Code Workspace mit KI-Agent-Konfiguration für die VOBES/Bordnetz-Entwicklung. Kombiniert GitHub Copilot mit domänenspezifischen Skills, einem lokalen RAG-System und MCP-Integrationen für Confluence/Jira.

## Überblick

| Komponente | Beschreibung |
|---|---|
| **AGENTS.md** | Steuerungsdatei für den KI-Agent (Skill-Routing, Tool-Prioritäten, Regeln) |
| **Local RAG** | Lokaler MCP-Server für Wissensabfragen zu VOBES, VEC, KBL, Prozessen u. a. |
| **MCP Atlassian** | Docker-basierter MCP-Server für Confluence- und Jira-Operationen |
| **Skills** | 5 domänenspezifische Skills unter `.agents/skills/` |

## Quick Start

### 1. Voraussetzungen

- VS Code mit GitHub Copilot Extension
- Docker Desktop (für MCP Atlassian)
- Umgebungsvariablen: `JIRA_PAT` und `CONFLUENCE_PAT`
- Lokaler RAG-Server auf `http://localhost:8000/mcp`
- Chrome Extension: Playwright MCP Bridge (Store-ID: mmlmfjhmonkocbjadbfplnigmagldckm)

### 2. MCP Atlassian Container starten

```powershell
# Via VS Code Task (empfohlen)
Ctrl+Shift+P → "Tasks: Run Task" → "MCP Atlassian: Start"

# Oder via PowerShell
.\scripts\mcp-atlassian\start.ps1
```

### 3. In Copilot Chat nutzen

```
@workspace Liste alle Seiten im Confluence Space EKEK1
@workspace Suche Issues im Projekt VKON2
@workspace Was ist der VEC?
```

## Projektstruktur

```
├── AGENTS.md                          # Agent-Steuerung (Skills, Regeln, Tool-Priorität)
├── .agents/skills/                    # Domänenspezifische Skills
│   ├── skill-knowledge-bordnetz-vobes/  # RAG-basierte Wissensabfragen
│   ├── skill-important-pages-links-and-urls/  # Standard-Links & Referenzseiten
│   ├── skill-protokoll-confluence/      # Protokollseiten erstellen/speichern
│   ├── skill-update-confluence-page/    # Confluence-Seiten aktualisieren
│   └── skill-jira-sys-flow/             # SYS-FLOW Jira-Board abfragen
├── .vscode/
│   ├── mcp.json                       # MCP-Server-Konfiguration (local-rag, mcp-atlassian)
│   ├── tasks.json                     # VS Code Tasks
│   └── settings.json                  # Workspace-Einstellungen
├── docs/
│   ├── mcp-atlassian/                 # MCP Atlassian Dokumentation
│   │   ├── MCP-ATLASSIAN-QUICKSTART.md
│   │   └── MCP-ATLASSIAN-SETUP.md
│   └── protokollseite-vibe-coding.md  # Beispiel-Protokollseite
├── scripts/
│   ├── mcp-atlassian/                 # Container-Management (start, stop, logs)
│   └── windows/                       # Utilities (Hibernate Scheduler)
└── userdata/                          # Arbeitsdaten (Rollen, Listen)
```

## MCP-Server

Konfiguriert in `.vscode/mcp.json`:

| Server | Typ | Beschreibung |
|---|---|---|
| `local-rag` | HTTP (`localhost:8000`) | Lokales RAG-System mit mehreren Knowledgebases (default, datenmodelle, jira-vkon2, ldorado, chd, prozesse) |
| `mcp-atlassian` | stdio (Docker) | Confluence- und Jira-Zugriff über Docker-Container |

## Skills

| Skill | Zweck |
|---|---|
| `skill-knowledge-bordnetz-vobes` | RAG-Abfragen zu VOBES, Bordnetz, VEC, KBL, Prozessen |
| `skill-important-pages-links-and-urls` | Referenz-Links für Confluence/Jira Spaces und Dashboards |
| `skill-protokoll-confluence` | Protokollseiten für Regeltermine erstellen und in Confluence speichern |
| `skill-update-confluence-page` | Standardisierter Ablauf zum Aktualisieren von Confluence-Seiten |
| `skill-jira-sys-flow` | Informationen aus dem Jira-Projekt SYS-FLOW abrufen |

## VS Code Tasks

| Task | Beschreibung |
|---|---|
| `MCP Atlassian: Start` | Docker-Container starten |
| `MCP Atlassian: Stop` | Docker-Container stoppen |
| `MCP Atlassian: Show Logs` | Container-Logs anzeigen |
| `Windows: Hibernate Scheduler` | GUI zum Planen eines einmaligen Hibernate-Zeitpunkts |

## Dokumentation

- [MCP Atlassian Quick Start](docs/mcp-atlassian/MCP-ATLASSIAN-QUICKSTART.md)
- [MCP Atlassian Setup (Detail)](docs/mcp-atlassian/MCP-ATLASSIAN-SETUP.md)
- [Protokollseite Vibe-Coding](docs/protokollseite-vibe-coding.md)

## Verfügbare Spaces

- **Confluence**: VOBES, VSUP, EKEK1
- **Jira**: VKON2, SYS-FLOW

## Ressourcen

- **VW Devstack Jira**: https://devstack.vwgroup.com/jira
- **VW Devstack Confluence**: https://devstack.vwgroup.com/confluence
- **MCP Atlassian GitHub**: https://github.com/sooperset/mcp-atlassian

# VS Code Einstellungen

## Markdown
In VS Code kannst du Markdown-Dateien standardmäßig direkt als gerenderte Vorschau öffnen, statt als reinen Texteditor. Dafür gibt es offiziell die Einstellung ```workbench.editorAssociations mit *.md -> vscode.markdown.preview.editor```
Noch besser wird es mit dem Markdown WYSIWYG-Editor "Markdown For Humans WYSIWYG" 

Damit der aber nicht für DIFFS verwendet wird, trage in deine settings.json ein:

```
"workbench.editorAssociations": {
    "{git}:/**/*.{md}": "vscode.markdown.preview.editor",
    "{git-index}:/**/*.{md}": "vscode.markdown.preview.editor",
    "*.md": "markdownForHumans.editor"
}
```

Damit werden .md-Dateien beim Öffnen als Markdown-Preview angezeigt. VS Code nennt das den Markdown Preview Custom Editor

## Tipps und Tricks

### Skills für alle Agents

orignial in -agents/skills (Github CoPilot und CODEX)
per symlnk spiegeln in .claude/skills

PowerShell
```
New-Item -ItemType Directory -Force .agents\skills | Out-Null
New-Item -ItemType Directory -Force .claude | Out-Null

if (Test-Path .claude\skills) {
    Remove-Item .claude\skills -Force -Recurse
}

New-Item -ItemType Junction -Path .claude\skills -Target (Resolve-Path .agents\skills).Path
```