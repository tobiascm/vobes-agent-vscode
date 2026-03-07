# MCP Atlassian Setup für VS Code

Diese Konfiguration ermöglicht die Nutzung des MCP Atlassian Servers in VS Code über Docker.

## Voraussetzungen

- Docker Desktop muss installiert und gestartet sein
- Umgebungsvariablen `JIRA_PAT` und `CONFLUENCE_PAT` müssen gesetzt sein
- VS Code mit GitHub Copilot Extension

## Container starten

### Option 1: VS Code Tasks (empfohlen)
1. Drücke `Ctrl+Shift+P`
2. Wähle "Tasks: Run Task"
3. Wähle "MCP Atlassian: Start"

### Option 2: PowerShell Skript
```powershell
.\scripts\mcp-atlassian\start.ps1
```

### Option 3: Docker Compose
```bash
cd C:\Daten\Python\vobes_agent_vscode
docker-compose -f docker-compose.mcp-atlassian.yml up -d
```

## Container stoppen

### VS Code Task
`Ctrl+Shift+P` → "Tasks: Run Task" → "MCP Atlassian: Stop"

### PowerShell
```powershell
.\scripts\mcp-atlassian\stop.ps1
```

## Logs anzeigen

### VS Code Task
`Ctrl+Shift+P` → "Tasks: Run Task" → "MCP Atlassian: Show Logs"

### PowerShell
```powershell
.\scripts\mcp-atlassian\logs.ps1
```

## MCP Server Konfiguration

Die MCP-Konfiguration befindet sich in `.vscode/mcp.json` und enthält:

- **Server**: `mcp-atlassian`
- **Typ**: stdio (über docker exec)
- **Container**: `mcp-atlassian`
- **Jira URL**: https://devstack.vwgroup.com/jira
- **Confluence URL**: https://devstack.vwgroup.com/confluence

## Verwendung in GitHub Copilot Chat

Nach dem Start des Containers kannst du MCP Atlassian Funktionen in Copilot Chat nutzen:

### Beispiele

**Jira:**
```
@workspace Suche alle offenen Issues im Projekt VOBES
@workspace Erstelle ein neues Issue in VKON2
@workspace Zeige Details zu VKON2-1234
```

**Confluence:**
```
@workspace Suche nach "Stammdatenservice" in Confluence Space VOBES
@workspace Zeige mir die Seite mit ID 123456789
@workspace Liste alle Seiten im Space VSUP
```

## Verfügbare Funktionen

Das MCP Atlassian Tool bietet ~72 Funktionen, darunter:

### Jira
- Issue Suche (JQL)
- Issue erstellen/aktualisieren
- Status-Übergänge
- Kommentare hinzufügen
- Attachments verwalten

### Confluence
- Seiten suchen (CQL)
- Seiten-Inhalt abrufen
- Seiten erstellen/aktualisieren
- Kommentare verwalten
- Attachments verwalten

## Troubleshooting

### Container startet nicht
```powershell
# Prüfe, ob JIRA_PAT und CONFLUENCE_PAT gesetzt sind
echo $env:JIRA_PAT
echo $env:CONFLUENCE_PAT

# Prüfe Docker Logs
docker logs mcp-atlassian

# Container neu starten
docker-compose -f docker-compose.mcp-atlassian.yml restart
```

### MCP Server nicht erreichbar
```powershell
# Prüfe, ob Container läuft
docker ps | grep mcp-atlassian

# Prüfe Container Health
docker inspect mcp-atlassian --format='{{.State.Health.Status}}'

# Test Container-Ausführung
docker exec -i mcp-atlassian mcp-atlassian --help
```

### Authentifizierung fehlgeschlagen
1. Überprüfe, ob PATs noch gültig sind: https://id.atlassian.com/manage-profile/security/api-tokens
2. Erneuere PATs falls nötig
3. Setze Umgebungsvariablen neu:
   ```powershell
   $env:JIRA_PAT = "neues_token"
   $env:CONFLUENCE_PAT = "neues_token"
   ```
4. Container neu starten

## Konfigurationsdateien

- **Docker Compose**: `docker-compose.mcp-atlassian.yml` (im Projektroot)
- **MCP Config**: `.vscode/mcp.json`
- **VS Code Tasks**: `.vscode/tasks.json`
- **Scripts**: `scripts/mcp-atlassian/*.ps1`

## Ressourcen

- GitHub Repo: https://github.com/sooperset/mcp-atlassian
- Docker Image: ghcr.io/sooperset/mcp-atlassian:0.21
- VW Devstack Jira: https://devstack.vwgroup.com/jira
- VW Devstack Confluence: https://devstack.vwgroup.com/confluence
