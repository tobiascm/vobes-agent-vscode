# VOBES Agent VS Code Workspace

Agenten-Toolset fuer die VOBES/Bordnetz-Entwicklung. Kombiniert domaenenspezifische Skills, ein lokales RAG-System, MCP-Integrationen (Confluence/Jira, Playwright, VOBES) sowie Python-Skripte und Tests fuer Budget-, M365-, Outlook- und Recherche-Workflows. Lauffaehig unter **Claude Code**, **GitHub Copilot** und **Codex** (gleiche Skills, zwei Steuerdateien).

## Überblick

- **`AGENTS.md`** — Steuerdatei fuer Copilot/Codex (Skill-Pflicht-Matrix, Tool-Prioritaet, Use-Cases)
- **`CLAUDE.md`** — Steuerdatei fuer Claude Code (inhaltsgleich mit AGENTS.md)
- **`.agents/skills/`** — 29 Skills (Budget, M365, Outlook, Confluence/Jira, Research, Utilities)
- **`.vscode/mcp.json`** — MCP-Server: `local-rag`, `local-rag-bridge`, `mcp-atlassian`, `playwright`
- **`scripts/`** — Python/PowerShell-Hilfsskripte (Budget-DB, MCP-Atlassian, Hooks, Token-Helper)
- **`tests/`** — pytest-Suite inkl. `e2e`-Tests (Outlook COM, LLM, M365)
- **`userdata/`** — Arbeitsdaten (Budget, Outlook, Sessions) — nicht eingecheckt


## Voraussetzungen

- **VS Code** mit GitHub Copilot Extension (optional: Claude Code CLI)
- **Python 3.11+** (siehe `pyproject.toml`)
- **Docker Desktop** (fuer MCP Atlassian)
- **Node.js** (fuer `npx @playwright/mcp`)
- **Chrome** mit Extension "Playwright MCP Bridge" (Store-ID `mmlmfjhmonkocbjadbfplnigmagldckm`)
- **Microsoft Edge** mit angemeldetem VW-Login (wird vom `local-rag-bridge` fuer Cookies gelesen)
- Umgebungsvariablen: `JIRA_PAT`, `CONFLUENCE_PAT`
- Lokaler RAG-Server auf `http://localhost:8000/mcp`

## Quick Start

### 1. Python-Paket installieren

```powershell
pip install -e ".[dev]"
pytest -q                # optional: Tests laufen lassen
```

### 2. MCP Atlassian Container starten

```powershell
# Via VS Code Task (empfohlen)
Ctrl+Shift+P -> "Tasks: Run Task" -> "MCP Atlassian: Start"

# Oder per PowerShell
.\scripts\mcp-atlassian\start_mcp_atlassian.ps1
```

### 3. Skill im Agent aufrufen

```
# Claude Code
/skill-knowledge-bordnetz-vobes   Was ist der VEC?
$skill-budget-bplus-export        Vorgangsuebersicht fuer EKEK/1 exportieren

# Copilot Chat
@workspace Liste alle Seiten im Confluence Space EKEK1
```

## Transkriptions-Tracking (Protokoll)

Der Skill [`skill-protokoll-confluence`](.agents/skills/skill-protokoll-confluence/SKILL.md) fuehrt ein zentrales Register fuer Transkriptionen.

- CSV-Register: `userdata/transcriptions/transcriptions.csv`
- Master-Transkripte: `userdata/transcriptions/transcripts/*.md`
- Open-Definition: Eintrag ist **offen**, wenn `integrated_targets` leer ist.

### CSV-Felder

```csv
transcription_id;meeting_at;meeting_title;source_type;source_item_id;source_location;transcript_md_path;integrated_targets;suggested_title;last_action_at;notes
```

### Typischer Ablauf

```powershell
# 1) Register aktualisieren (Teams Recordings + lokale Audioaufzeichnungen)
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py sync-register

# Optional: Kalender auch fuer bestehende Eintraege komplett neu abgleichen (langsamer)
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py sync-register --refresh-existing-calendar

# 2) Offene Eintraege anzeigen
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py list-open --limit 20

# 3) Naechsten offenen Eintrag holen
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py next-open

# 4) Transkript als Master-Markdown materialisieren
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py materialize-transcript <transcription_id|source_item_id>

# 5) Nach Integration Ziel hinterlegen (Confluence/lokal/skip/merged/deferred)
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py mark-integrated <transcription_id|source_item_id> --target "confluence|url=...|page_id=...|space=...|title=..."
```

### `integrated_targets`-Konventionen

- `confluence|url=...|page_id=...|space=...|title=...`
- `local|path=...`
- `merged|into=...|reason=...`
- `skip|reason=...`
- `deferred|reason=...`

Mehrere Ziele sind pro Eintrag moeglich (mehrere Zeilen in einer CSV-Zelle).

Hinweis Performance: Standard-`sync-register` fragt Outlook-Kalender nur fuer neue oder unsichere Audio-Titel nach. Das beschleunigt regelmaessige Laeufe deutlich.

## Projektstruktur

```
├── AGENTS.md                          # Steuerung Copilot/Codex
├── CLAUDE.md                          # Steuerung Claude Code (inhaltsgleich)
├── pyproject.toml                     # Python-Paket `vobes-agent`, requires-python >=3.11
├── .agents/skills/                    # 29 Skills (siehe Tabelle unten)
├── .claude/                           # Claude-Code-Konfiguration
│   └── skills/                        # Junction -> .agents/skills (siehe Multi-Agent-Setup)
├── .vscode/
│   ├── mcp.json                       # 4 MCP-Server
│   ├── tasks.json                     # VS Code Tasks
│   └── settings.json
├── scripts/
│   ├── budget/                        # Budget-DB, Beauftragungs-Solver, Report-Utils
│   ├── hooks/                         # Stop-Hook Notifier (notify.ps1, codex-notify.ps1)
│   ├── mcp-atlassian/                 # Docker-Compose und Start/Stop/Logs
│   ├── confluence_md_bridge.py        # Confluence <-> Markdown Bridge
│   ├── m365_copilot_graph_token.py    # Graph-Token-Helfer (M365 Copilot)
│   ├── m365_file_reader.py            # PPTX/XLSX/DOCX/PDF/Bild aus SharePoint/OneDrive
│   ├── outlook_token.py               # Outlook-Token-Helfer
│   └── query_local_rag.py             # CLI-Wrapper um local_rag
├── tests/                             # pytest-Suite (Marker `e2e`)
├── config/
│   └── src_zip_config.toml
├── docs/
│   ├── mcp-atlassian/                 # Quickstart, Setup, Integration
│   ├── bplus/eigenleistung-api.md     # BPLUS EL-API-Beschreibung
│   ├── teams-token-debugging.md       # 6-Stufen-Fallback-Kette M365-Token
│   ├── token-verfahren.md             # Token-Beschaffung generell
│   ├── spec_deep_research.md          # Spec fuer skill-deep-research
│   ├── howto_chat_notify.md           # Chat-Notification-Setup
│   └── Analyse-m365-copilot-*.md      # Research zu M365-Copilot-Skills
└── userdata/                          # Arbeitsdaten (Budget, Outlook, Sessions) - .gitignore
```

## Agenten-Steuerung

Beide Steuerdateien (`AGENTS.md` fuer Copilot/Codex, `CLAUDE.md` fuer Claude Code) enthalten dieselben Regeln:

- **Skill-Pflicht-Matrix**: Vor jeder Antwort pruefen, ob Bordnetz/VOBES-, Confluence/Jira- oder EKEK/1-Kontext vorliegt. In diesem Fall ist das zugehoerige Skill vor der fachlichen Antwort zu laden.
- **Tool-Prioritaet**: `local_rag` ist fuer alle Wissensfragen erste Wahl. `mcp-atlassian` nur fuer Confluence/Jira-Lese-/Schreiboperationen.
- **Git-Skill-Pflicht**: `git commit` nur via `$git-commit`, `git push` nur via `$git-push`, Umbenennen/Verschieben nur mit `git mv`.
- **Plan-Modus**: Wenn MCP-Tools nicht verfuegbar sind, antwortet der Agent mit einer standardisierten Hinweismeldung statt zu raten.
- **Zahlenauswertung**: Summen und Aggregationen immer per Python oder PowerShell, nie manuell.

## MCP-Server

Konfiguriert in `.vscode/mcp.json`:

- **`local-rag`** · HTTP (`localhost:8000`) — Lokales RAG (KBs: `default`, `datenmodelle`, `jira-vkon2`, `ldorado`, `chd`, `prozesse`)
- **`local-rag-bridge`** · stdio (Python) — Bruecke zum remote VOBES-RAG (`test.vobes.vwgroup.com/lightrag`), nutzt Edge-Cookie `MRHSession`
- **`mcp-atlassian`** · stdio (Docker) — Confluence- und Jira-Zugriff via Container
- **`playwright`** · stdio (`npx`) — Browser-Automation via Chrome-Extension (VOBES, M365 Copilot, ChatGPT, Outlook-Termin)


## Skills

### Wissen & Orga
- [skill-knowledge-bordnetz-vobes](.agents/skills/skill-knowledge-bordnetz-vobes/SKILL.md) — RAG-Abfragen zu VOBES, Bordnetz, VEC, KBL, LDorado, Prozessen
- [skill-orga-ekek1](.agents/skills/skill-orga-ekek1/SKILL.md) — Referenz fuer EKEK/1-Orga, Namen, Rollen, Gremien, Regeltermine
- [skill-important-pages-links-and-urls](.agents/skills/skill-important-pages-links-and-urls/SKILL.md) — Zentrale Link-/URL-Sammlung fuer EKEK/1-Dashboard
- [skill-te-regelwerk](.agents/skills/skill-te-regelwerk/SKILL.md) — TE Regelwerk (iProject) durchsuchen, Prozessstandards laden

### Budget & BPLUS
- [skill-budget-bplus-export](.agents/skills/skill-budget-bplus-export/SKILL.md) — Vorgangs-, Abruf-, BM-, Konzeptuebersicht aus BPLUS-NG
- [skill-budget-ea-uebersicht](.agents/skills/skill-budget-ea-uebersicht/SKILL.md) — EA-Stammdaten, Laufzeiten, DevOrders
- [skill-budget-stundensaetze](.agents/skills/skill-budget-stundensaetze/SKILL.md) — OE-Stundensaetze
- [skill-budget-ua-leiter](.agents/skills/skill-budget-ua-leiter/SKILL.md) — UA-Leiter / OE→Mail-Zuordnung
- [skill-budget-eigenleistung-el](.agents/skills/skill-budget-eigenleistung-el/SKILL.md) — EL-Planung lesen/schreiben (inkl. `el_change.py`)
- [skill-budget-plausibilisierung](.agents/skills/skill-budget-plausibilisierung/SKILL.md) — BM-Texte und Aufwandsbegruendungen
- [skill-budget-target-ist-analyse](.agents/skills/skill-budget-target-ist-analyse/SKILL.md) — Massnahmenplan (Aufgabenbereich + Firma)
- [skill-budget-beauftragungsplanung](.agents/skills/skill-budget-beauftragungsplanung/SKILL.md) — Beauftragungsplanung Fremdvergaben (2-Stage-Solver)

### Confluence & Jira
- [skill-protokoll-confluence](.agents/skills/skill-protokoll-confluence/SKILL.md) — Protokollseiten fuer Regeltermine
- [skill-update-confluence-page](.agents/skills/skill-update-confluence-page/SKILL.md) — Bestehende Confluence-Seiten aktualisieren
- [skill-jira-sys-flow](.agents/skills/skill-jira-sys-flow/SKILL.md) — Jira-Board SYS-FLOW (SYS-AEMs, Systemschaltplaene)

### M365 & Outlook
- [skill-m365-copilot-chat](.agents/skills/skill-m365-copilot-chat/SKILL.md) — M365 Copilot Chat via Playwright DOM
- [skill-m365-copilot-file-search](.agents/skills/skill-m365-copilot-file-search/SKILL.md) — SharePoint/OneDrive via Graph Beta API
- [skill-m365-copilot-mail-search](.agents/skills/skill-m365-copilot-mail-search/SKILL.md) — Outlook-Mails via Graph Search API
- [skill-m365-file-reader](.agents/skills/skill-m365-file-reader/SKILL.md) — PPTX/XLSX/DOCX/PDF/Bilder aus SharePoint/OneDrive
- [skill-sharepoint](.agents/skills/skill-sharepoint/SKILL.md) — SharePoint REST API (Listen, Docs, Suche) via Playwright-SSO
- [skill-m365-mail-agent](.agents/skills/skill-m365-mail-agent/SKILL.md) — Agentische Mail-Fall-Analyse (Seed-Mail + Iteration)
- [skill-m365-graph-scope-probe](.agents/skills/skill-m365-graph-scope-probe/SKILL.md) — Diagnose fehlender Graph-Scopes (401/403)
- [skill-outlook](.agents/skills/skill-outlook/SKILL.md) — Lokales Outlook (COM): Suche, Thread-Sicht, verwandte Mails
- [skill-outlook-termin](.agents/skills/skill-outlook-termin/SKILL.md) — Outlook-/Teams-Termine erstellen

### Personen & Recherche
- [skill-personensuche-groupfind](.agents/skills/skill-personensuche-groupfind/SKILL.md) — Personen, Vorgesetzte, OE-Struktur via GroupFind
- [skill-deep-research](.agents/skills/skill-deep-research/SKILL.md) — Mehrstufige Multi-Source-Recherche
- [skill-chatgpt-research](.agents/skills/skill-chatgpt-research/SKILL.md) — Frage an ChatGPT via Playwright
- [skill-browse-intranet](.agents/skills/skill-browse-intranet/SKILL.md) — Intranet-Seiten per Playwright (Navigation, Extraktion, Screenshots)

### Utilities
- [skill-excel-io](.agents/skills/skill-excel-io/SKILL.md) — `.xlsx` lesen/schreiben/bearbeiten per CLI
- [skill-file-converter](.agents/skills/skill-file-converter/SKILL.md) — Lokale Dateien nach PDF (Office COM) oder Markdown (lightrag)
- [skill-hibernate](.agents/skills/skill-hibernate/SKILL.md) — Rechner zeitgesteuert in Ruhezustand versetzen


## VS Code Tasks & Hooks

- **`MCP Atlassian: Start`** — Docker-Container starten
- **`MCP Atlassian: Stop`** — Docker-Container stoppen
- **`MCP Atlassian: Show Logs`** — Container-Logs tail'en
- **`Windows: Hibernate Scheduler`** — GUI fuer einmaligen Hibernate-Zeitpunkt


**Stop-Hook Notifications**: `scripts/hooks/notify.ps1` (Claude Code) und `scripts/hooks/codex-notify.ps1` (Codex) zeigen eine nicht-blockierende Popup-Benachrichtigung via `wscript.exe`, wenn der Agent auf Eingabe wartet.

## Tests

```powershell
pytest -q                     # schnelle Tests
pytest -q -m e2e              # nur e2e (Outlook COM, LLM, M365 - langsam)
pytest -q -m "not e2e"        # e2e ausklammern
```

Test-Daten liegen unter `tests/` (z. B. `TestPPTX.pptx`, `TestXLSX-lang.xlsx`, `budget_test.db`).

## Dokumentation

**MCP Atlassian**

- [Quick Start](docs/mcp-atlassian/MCP-ATLASSIAN-QUICKSTART.md) — Schnelleinstieg fuer den Docker-Container
- [Setup (Detail)](docs/mcp-atlassian/MCP-ATLASSIAN-SETUP.md) — ausfuehrliche Einrichtung inkl. PAT und Env
- [Integration](docs/mcp-atlassian/mcp-atlassian-integration.md) — Einbettung in die Agent-Workflows

**Token & M365**

- [Teams-Token-Debugging](docs/teams-token-debugging.md) — 6-Stufen-Fallback-Kette bei TOKEN_EXPIRED / AADSTS
- [Token-Verfahren](docs/token-verfahren.md) — Ueberblick ueber Token-Beschaffung (Graph, Teams, Outlook)

**BPLUS / Budget**

- [BPLUS Eigenleistung API](docs/bplus/eigenleistung-api.md) — Endpunkte fuer `skill-budget-eigenleistung-el`

**M365 Copilot — Research-Analysen**

- [Analyse M365 Copilot API Research](docs/Analyse-m365-copilot-api-research.md) — Untersuchung Graph-/Copilot-APIs
- [Analyse M365 Copilot Chat Skill](docs/Analyse-m365-copilot-chat-skill.md) — Design-Analyse `skill-m365-copilot-chat`

**Sonstige**

- [Spec Deep Research](docs/spec_deep_research.md) — Spezifikation fuer `skill-deep-research`
- [Chat-Notification-Setup](docs/howto_chat_notify.md) — Setup fuer Stop-Hook-Popups

## Verfuegbare Spaces

- **Confluence**: VOBES, VSUP, EKEK1
- **Jira**: VKON2, SYS-FLOW

## Ressourcen

- VW Devstack Jira: [https://devstack.vwgroup.com/jira](https://devstack.vwgroup.com/jira)
- VW Devstack Confluence: [https://devstack.vwgroup.com/confluence](https://devstack.vwgroup.com/confluence)
- MCP Atlassian GitHub: [https://github.com/sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian)

## Multi-Agent-Setup

Die Skills liegen original unter `.agents/skills/` (fuer Copilot/Codex). Fuer Claude Code werden sie per Junction nach `.claude/skills/` gespiegelt — dadurch gibt es nur **eine** Quelle, aber beide Agenten sehen die Skills.

```powershell
New-Item -ItemType Directory -Force .agents\skills | Out-Null
New-Item -ItemType Directory -Force .claude | Out-Null

if (Test-Path .claude\skills) {
    Remove-Item .claude\skills -Force -Recurse
}

New-Item -ItemType Junction -Path .claude\skills -Target (Resolve-Path .agents\skills).Path
```

## VS Code Tipps

### Markdown standardmaessig als Preview oeffnen

Mit der Extension "Markdown For Humans WYSIWYG" — aber nicht fuer Diffs. In `settings.json`:

```json
"workbench.editorAssociations": {
    "{git}:/**/*.{md}": "vscode.markdown.preview.editor",
    "{git-index}:/**/*.{md}": "vscode.markdown.preview.editor",
    "*.md": "markdownForHumans.editor"
}
```

# VS Code Einstellungen

## Markdown

In VS Code kannst du Markdown-Dateien standardmäßig direkt als gerenderte Vorschau öffnen, statt als reinen Texteditor. Dafür gibt es offiziell die Einstellung `workbench.editorAssociations mit *.md -> vscode.markdown.preview.editor`  
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

### Copilot Auto Suggest auch für Markdown

In settings.json:

```json
"github.copilot.enable": {
  "*": true,
  "markdown": true
},
"editor.inlineSuggest.enabled": true
```

### **Key-Shortcut für nur ein Wort übernehmen:**

In C:\Users\<DEIN_USER>\AppData\Roaming\Code\User\keybindings.json:

```json
[
  {
  "key": "shift+tab",
    "command": "editor.action.inlineSuggest.acceptNextWord",
    "when": "inlineSuggestionVisible && !editorReadonly"
  }
  ]
```

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

# Details

## Skill-Matrix Zugriffe und Berechtigungen

Legende Auth-Typ: **Browser-SSO** = Kerberos/NTLM ueber Playwright, **Graph API** = MS Graph mit Token, **NAA** = Nested App Auth, **COM** = Outlook COM, **lokal** = nur lokale Dateien.

> Skills mit **App-Reg = Ja** benoetigen eine registrierte Azure AD App.


#### Browser-SSO (Playwright)
- **skill-browse-intranet** · Playwright MCP · keine (aktive Browser-Session)
- **skill-chatgpt-research** · Playwright MCP, ChatGPT Web · keine
- **skill-personensuche-groupfind** · GroupFind GraphQL · Keycloak, VW-Netz-Konto
- **skill-sharepoint** · SharePoint REST API · SharePoint-Berechtigungen auf Ziel-Site
- **skill-te-regelwerk** · Playwright, iProject Web · iProject Lesezugriff

#### BPLUS Kerberos
- **skill-budget-beauftragungsplanung** · SQLite, Excel-Config · BPLUS-Benutzerrechte
- **skill-budget-bplus-export** · BPLUS REST API, SQLite · BPLUS Lese-/Exportrechte
- **skill-budget-ea-uebersicht** · BPLUS REST API · `OrgUnit/GetAll`, `DevOrder/GetAll`
- **skill-budget-eigenleistung-el** · BPLUS REST API · `el_planning` (Schreibzugriff)
- **skill-budget-stundensaetze** · BPLUS REST API · `CostCenter/GetCostCenter2HourlyRates`
- **skill-budget-target-ist-analyse** · BPLUS REST API · read-only
- **skill-budget-ua-leiter** · BPLUS REST API · `OrgUnit/GetAll` mit Mail-Feldern

#### Confluence / Jira PAT
- **skill-deep-research** · Playwright + mcp-atlassian · Confluence Lese (VOBES, VSUP)
- **skill-jira-sys-flow** · mcp-atlassian · Jira Lese (SYS-FLOW)
- **skill-protokoll-confluence** · mcp-atlassian · Confluence Lese-/Schreib (VOBES, EKEK1)
- **skill-update-confluence-page** · mcp-atlassian · Confluence Schreib auf Zielseite

#### COM (Outlook lokal)
- **skill-outlook** · Outlook COM (Lesen, Suchen, **Senden**) · bei Graph-Migration: `Mail.Send`, `Mail.ReadWrite`
- **skill-outlook-termin** · Outlook COM (Erstellen, **Senden**, Absagen) · bei Graph-Migration: `Calendars.ReadWrite`

#### Graph API / NAA (App-Reg = **Ja**)
- **skill-m365-copilot-chat** · Playwright DOM · Browser-SSO; bei API-Migration: `Mail.Read`, `Chat.Read`, `ChannelMessage.Read.All`, `People.Read.All`, `OnlineMeetingTranscript.Read.All`, `ExternalItem.Read.All`, `Sites.Read.All`
- **skill-m365-copilot-file-search** · Graph Beta API, NAA (AppID c0ab8ce9) · `Files.Read.All`, `Sites.Read.All`
- **skill-m365-copilot-mail-search** · Graph Search API (Teams AppID 5e3ce6c0) · **`Mail.Read`**, `Calendars.Read`
- **skill-m365-file-reader** · Graph API, NAA · `Files.Read.All`, `Sites.Read.All`
- **skill-m365-graph-scope-probe** · bestehende Tokens · keine eigenen (diagnostisch)
- **skill-m365-mail-agent** · Graph Search API + COM · **`Mail.Read`**, `Calendars.Read`, `Files.Read.All`
- **skill-teams-chat** · Teams Chat Service API · `ic3.teams.office.com/.default`, `Chat.ReadWrite`, `User.Read`
