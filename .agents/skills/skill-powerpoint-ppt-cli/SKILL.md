---
name: skill-powerpoint-ppt-cli
description: PowerPoint-Dateien (.pptx) auf Windows mit dem offiziellen `PptMcp.Agent` (Plan/Execute/Verify/Repair) erzeugen und bearbeiten. Corporate-Template-Auswahl bleibt als verpflichtendes Profil-Gate aktiv.
---

# Skill: PowerPoint mit PptMcp.Agent

Primärpfad ist der offizielle Orchestrator `src\PptMcp.Agent` aus `trsdn/mcp-server-ppt`.  
Der Ablauf ist mehrphasig: Plan -> Execute -> Verify -> Repair.  
Keine XML-Manipulation, nur COM-basierte PowerPoint-Automation ueber `mcp-server-ppt`.

Hinweis zur Namensgebung:

- Der Skill heißt historisch `skill-powerpoint-ppt-cli`.
- Fuer **neue Deck-Erstellung** ist der Hauptpfad `PptMcp.Agent` ueber `scripts/run_ppt_mcp_agent.ps1`.
- Fuer **bestehende PPTX-Umbauten** ist der technische Hauptpfad `pptcli session open` oder eine direkte MCP-PowerPoint-Session.
- Der New-Deck-Orchestrator wird fuer Modify nicht erzwungen, wenn gezielte Session-Edits geeigneter sind.
- Der Wrapper nutzt standardmaessig `-Provider codex`; fuer Copilot explizit `-Provider copilot` setzen.

## Wann verwenden

- neue Praesentation per Prompt erzeugen
- bestehende Praesentation agentisch verbessern/reparieren
- aus Mail-/Outlook-Inhalten eine Praesentation erzeugen, nachdem der Inhalt durch den passenden Mail-Skill als Markdown/JSON extrahiert wurde
- reproduzierbare Deck-Erzeugung mit `.plan.json` und `run-summary.json`
- laengere Aufgaben, die Plan/Verify/Repair benoetigen

## Wann NICHT verwenden

- nur PPTX → PDF konvertieren ohne Aenderung → `$skill-file-converter`
- PPTX-Text aus SharePoint/OneDrive nur **lesen** → `$skill-m365-file-reader`
- Outlook/Mail-Inhalte direkt suchen/extrahieren → zuerst `$skill-outlook`, `$skill-m365-copilot-mail-search` oder `$skill-m365-mail-agent`
- Linux/Server-Umgebung (kein lokales PowerPoint) → `python-pptx` direkt

## Voraussetzungen


| Komponente                     | Pfad / Check                                                                                             |
| ------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Microsoft PowerPoint (Desktop) | muss auf dem System installiert sein                                                                     |
| .NET 9 SDK/Runtime             | `dotnet --version` und Build muss laufen                                                                 |
| Node.js + npm                  | `node --version`, `npm --version`                                                                        |
| Externes Repo                  | `C:\Daten\Programme\mcp-server-ppt`                                                                      |
| Agent CLI                      | `C:\Daten\Programme\mcp-server-ppt\src\PptMcp.Agent\src\cli.mjs`                                         |
| MCP Server Binary              | `C:\Daten\Programme\mcp-server-ppt\src\PptMcp.McpServer\bin\Release\net9.0-windows\PptMcp.McpServer.exe` |
| Codex MCP-Server               | `codex mcp get ppt` muss auf das MCP Server Binary zeigen, wenn `-Provider codex` genutzt wird             |
| Vorlagen-Ordner                | `.agents/skills/skill-powerpoint-ppt-cli/Vorlagen/`                                                      |


## Setup (manuell, einmalig)

```powershell
Set-Location C:\Daten\Programme\mcp-server-ppt
dotnet build src\PptMcp.McpServer\PptMcp.McpServer.csproj -c Release /p:NuGetAudit=false

Set-Location src\PptMcp.Agent
npm install
npm run check
npm test

codex mcp add ppt -- "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.McpServer\bin\Release\net9.0-windows\PptMcp.McpServer.exe"
codex mcp get ppt
```

## Arbeitsregeln (verpflichtend)

1. **Template-Auswahl ist Pflicht-Gate fuer neue Decks.** Vor jedem New-Deck-Run muss eine Vorlage aktiv vom User gewaehlt werden:
  Bei Modify bestehender PPTX gilt stattdessen: Input-PPTX eindeutig bestimmen, nach Output-PPTX kopieren und nur die Output-PPTX bearbeiten.
2. **Paritaet zum offiziellen Agent-Flow**: Plan -> Execute -> Verify -> Repair.
3. **Template-Hinweis**: Die Auswahl wirkt als Corporate-Profil-Guidance fuer den Agent-Prompt.
4. **Keine XML-Hacks** und keine direkte `.potx`-Mutation.
5. **Bei Fehlern** klare Preflight-/Setup-Anweisung geben.

## Template-Fidelity

Aktueller Stand:

- `TemplatePath` wird vom Wrapper `scripts/run_ppt_mcp_agent.ps1` als Corporate-Template-Guidance an `PptMcp.Agent` uebergeben.
- Das garantiert noch nicht technisch, dass die Output-PPTX per PowerPoint-COM aus der `.potx` vorinstanziiert wurde.
- Fuer normale Entwuerfe ist das ausreichend.
- Fuer harte Corporate-Fidelity ist spaeter ein separater Wrapper-Modus sinnvoll:
  1. `.potx` per PowerPoint-COM als neue `.pptx` instanziieren
  2. danach diese `.pptx` mit `pptcli session open` oder MCP gezielt bearbeiten

Bis dieser Modus existiert, darf der Agent keine falsche Garantie geben, dass das Output-Deck technisch aus der Vorlage erzeugt wurde.

## Upstream-Referenzen

Die folgenden Dateien liegen als Referenzmaterial unter  
`.agents/skills/skill-powerpoint-ppt-cli/references/pptmcp-upstream/`:

- `ppt-cli.SKILL.md`
- `ppt-mcp.SKILL.md`
- `behavioral-rules.md`
- `generation-pipeline.md`
- `ppt_agent_mode.md`
- `slide-design-principles.md`
- `slide-design-review.md`
- `PptMcp.Agent.README.md`
- `AGENT-CLIENT.md`
- `LICENSE`

Regeln:

- Die **lokale** `SKILL.md` ist maßgeblich fuer diesen Workspace.
- Die Upstream-Dateien sind Referenzmaterial zur Orientierung und Angleichung.
- Bei Konflikten gewinnt immer der lokale VW-/Corporate-Workflow.

## Modify bestehender PowerPoint-Dateien

Regeln fuer Aenderungen an vorhandenen Decks:

- Originaldatei niemals direkt bearbeiten.
- Input-PPTX zuerst nach einer neuen Output-PPTX kopieren.
- Nur die Output-PPTX oeffnen und bearbeiten.
- Gezielte Aenderungen bevorzugen statt kompletter Delete-Rebuild-Strategie.
- Vor Aenderungen erst Slides/Shapes/Placeholder/Charts/Tables inspizieren.
- Vor jedem Delete immer erst `list/read/verify` ausfuehren.
- Nach jeder Aenderung betroffene Slides erneut lesen/verifizieren.
- Optional zusaetzlich PDF-/PNG-Export zur Sichtpruefung erzeugen.
- Am Ende immer explizit speichern und sauber schliessen.

Technischer Modify-Hauptpfad:

1. Input-Datei nach Output-Datei kopieren.
2. Output-Datei mit `pptcli session open <output.pptx>` oder direkter MCP-Session oeffnen.
3. Bestand inspizieren:
  - `slide list`
  - `shape list`
  - `text find`
  - Chart-/Table-/Placeholder-Inspection, soweit verfuegbar
4. Zielobjekte anhand stabiler Slide-Indizes, Shape-Namen oder Placeholder identifizieren.
5. Nur gezielte Aenderungen ausfuehren:
  - Text setzen/ersetzen
  - Shapes verschieben/skalieren/formatieren
  - Charts/Tables aktualisieren
  - Bilder gezielt ersetzen
6. Betroffene Slides erneut lesen/verifizieren.
7. Optional PDF/PNG exportieren.
8. Session mit Save sauber schliessen.

Wichtig:

- `PptMcp.Agent` bleibt primaer fuer neue Deck-Erstellung und groessere Plan/Verify/Repair-Runs.
- Fuer kleine oder konkrete Umbauten bestehender PPTX ist `pptcli session open` meist robuster und besser nachvollziehbar.

## Mail-/Outlook-Inhalte zu PowerPoint

Dieser Skill sucht oder liest keine Outlook-/M365-Mails selbst.

Standardkette:

1. Mail-Inhalt mit passendem Mail-Skill extrahieren:
   - `$skill-outlook` fuer lokales Outlook/COM
   - `$skill-m365-copilot-mail-search` fuer Graph/Copilot-Mail-Suche
   - `$skill-m365-mail-agent` fuer agentische Fallanalyse
2. Extrahierten Inhalt als Markdown/JSON an diesen PowerPoint-Skill uebergeben.
3. Neue Praesentation ueber `scripts/run_ppt_mcp_agent.ps1` erzeugen oder bestehende PPTX ueber Modify-Workflow bearbeiten.

Es gibt keinen separaten Legacy-Mail-PPT-Builder mehr.
Die geloeschte Datei `test_email_prompt_content.json` ist bewusst nicht erforderlich.

## Create neuer PowerPoint-Dateien

Regeln fuer Neuanlagen:

- Template-Gate bleibt verpflichtend (Vorlage aktiv waehlen).
- Wrapper-Default ist `-Provider codex`; fuer GitHub Copilot explizit `-Provider copilot` verwenden.
- Vorlage nur als Corporate-Template-Profil/Quelle verwenden, niemals mutieren.
- Output standardmaessig nach `userdata/powerpoint/drafts/` schreiben.
- Nach jedem Lauf Artefakte pruefen:
  - `*.plan.json`
  - `*-artifacts/run-summary.json` (primär `status`, `verification`, `slideCount*`; freie Agent-Texte nur in `raw.*`)

## Design Review

Lokale, gekuerzte Review-Regeln (an Upstream angelehnt):

- Action Titles verwenden (aussagekraeftige, handlungsorientierte Titel).
- Pro Slide genau eine Kernbotschaft.
- Lesbarkeit sicherstellen (Schriftgroessen, Kontrast, Hierarchie).
- Keine Ueberlappungen von Shapes/Charts/Texten.
- Konsistente Abstaende und sauberes Grid.
- Bei Datenfolien Source Bar pflegen.
- Title Story Test: Titel ueber alle Slides muessen eine klare Story bilden.
- Deck-Level Flow pruefen (roter Faden ueber alle Slides).
- Keine festen Upstream-Farben/Fallback-Fonts erzwingen.
- VW-/Unternehmensvorlage hat immer Vorrang.

## Agent-Verhalten

Arbeitsregeln fuer den Agent:

- Nicht nach Informationen fragen, die per Tool/CLI direkt ermittelbar sind.
- Rueckfragen sind verpflichtend bei:
  - destruktiven Aenderungen
  - Ueberschreiben bestehender Outputs
  - unklarer Input-Datei
  - mehreren moeglichen Vorlagen
- Bei Fehlern nicht identisch wiederholen:
  - Fehlerursache lesen
  - Parameter gezielt korrigieren
  - genau einen gezielten Retry ausfuehren

## Standard-Pfade


| Zweck           | Pfad                                                                    |
| --------------- | ----------------------------------------------------------------------- |
| Vorlagen        | `.agents/skills/skill-powerpoint-ppt-cli/Vorlagen/*.potx`               |
| Entwuerfe       | `userdata/powerpoint/drafts/`                                           |
| Agent-Artefakte | neben Output-Datei: `*.plan.json`, `*-artifacts\run-summary.json`       |
| Runner-Script   | `.agents/skills/skill-powerpoint-ppt-cli/scripts/run_ppt_mcp_agent.ps1` |


## Workflow

```powershell
# 1) Vorlage interaktiv oder eindeutig per -Name/-Index waehlen (Pflicht)
powershell -ExecutionPolicy Bypass -File .agents/skills/skill-powerpoint-ppt-cli/scripts/select_template.ps1

# Agentenfaehig ohne Interaktion, wenn Name eindeutig ist:
powershell -ExecutionPolicy Bypass -File .agents/skills/skill-powerpoint-ppt-cli/scripts/select_template.ps1 `
  -Name "Volkswagen Brand" `
  -NonInteractive

# 2) Agent-Run starten (empfohlener Hauptpfad)
powershell -ExecutionPolicy Bypass -File .agents/skills/skill-powerpoint-ppt-cli/scripts/run_ppt_mcp_agent.ps1 `
  -Task "Build a 5-slide executive deck on Q4 revenue performance and next actions." `
  -TemplatePath ".agents/skills/skill-powerpoint-ppt-cli/Vorlagen/Volkswagen Brand.potx" `
  -OutputPath "userdata/powerpoint/drafts/q4-agent-smoke.pptx" `
  -Provider codex `
  -Overwrite

# 3) Ergebnis pruefen:
#    - userdata/powerpoint/drafts/q4-agent-smoke.pptx
#    - userdata/powerpoint/drafts/q4-agent-smoke.plan.json
#    - userdata/powerpoint/drafts/q4-agent-smoke-artifacts/run-summary.json
#      Wichtig: Fuer Betriebsentscheidungen nur status/verification/slideCount* nutzen.
#      raw.executionSummary/raw.repairSummary/raw.verificationSummary sind Debug-Freitext.
```

Direkter Agent-CLI-Aufruf (ohne Wrapper) bleibt moeglich:

```powershell
Set-Location C:\Daten\Programme\mcp-server-ppt\src\PptMcp.Agent
node .\src\cli.mjs run `
  --provider codex `
  --task "Build a 5-slide executive deck on Q4 revenue performance and next actions." `
  --output "C:\Daten\Python\vobes_agent_vscode\userdata\powerpoint\drafts\q4-agent-smoke.pptx" `
  --overwrite
```

Wichtige Flags:

- `--provider`, `--plan-file`, `--model`, `--show`, `--skip-verify`, `--mcp-server`
- `--plan-timeout-ms`, `--execute-timeout-ms`, `--verify-timeout-ms`

## Fehlerbehandlung


| Fehler                                 | Ursache                      | Fix                                                                             |
| -------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------- |
| `Missing npm dependencies`             | `node_modules` fehlt         | `cd C:\Daten\Programme\mcp-server-ppt\src\PptMcp.Agent && npm install`          |
| `Default MCP server binary not found`  | MCP Server nicht gebaut      | `dotnet build ... -c Release /p:NuGetAudit=false`                               |
| `NU190x warnings as errors`            | NuGet-Audit blockiert Build  | Build mit `/p:NuGetAudit=false` ausfuehren                                      |
| Agent bricht mit Copilot-SDK Fehler ab | Copilot Runtime/Auth Problem | in `src\PptMcp.Agent` erneut `npm install`, dann `npm run check` und `npm test` |
| Datei gesperrt                         | Deck in PowerPoint offen     | Deck in PowerPoint schliessen, Run wiederholen                                  |
