# MCP Atlassian Quick Start

Schnelleinstieg für die Nutzung des MCP Atlassian Servers mit Docker + VS Code.

## 1-Minuten-Setup

**Wichtig**: VW Devstack ist ein Server/Data Center Deployment und verwendet **Bearer Token Authentication**.

### Schritt 1: Container starten
```powershell
cd C:\Daten\Python\vobes_agent_vscode
docker-compose -f docker-compose.mcp-atlassian.yml up -d
```

### Schritt 2: Status prüfen
```powershell
docker ps | grep mcp-atlassian
# Sollte "healthy" zeigen
```

### Schritt 3: VS Code öffnen
```powershell
code C:\Daten\Python\vobes_agent_vscode
```

### Schritt 4: In Copilot Chat nutzen
```
@workspace Suche alle offenen Issues im Projekt VKON2
```

## Wichtige Befehle

### Container Management
```powershell
# Starten
.\scripts\mcp-atlassian\start.ps1

# Stoppen
.\scripts\mcp-atlassian\stop.ps1

# Logs
.\scripts\mcp-atlassian\logs.ps1

# Status
docker ps | grep mcp-atlassian
```

### Häufige Aufgaben

**Jira Issues suchen:**
```
@workspace Suche Issues mit JQL: project = VKON2 AND status = "In Progress"
```

**Confluence Seiten suchen:**
```
@workspace Suche Confluence-Seiten mit CQL: space = VOBES AND type = page
```

**Issue Details abrufen:**
```
@workspace Zeige Details zu VKON2-1234
```

**Seiten-Inhalt abrufen:**
```
@workspace Zeige mir den Inhalt der Confluence-Seite 123456789
```

## Troubleshooting

**Container läuft nicht:**
```powershell
docker logs mcp-atlassian
docker-compose -f docker-compose.mcp-atlassian.yml restart
```

**Authentifizierung fehlschlägt:**
```powershell
# Prüfe PATs
echo $env:JIRA_PAT
echo $env:CONFLUENCE_PAT

# Container neu starten
docker-compose -f docker-compose.mcp-atlassian.yml restart
```

**MCP Server antwortet nicht:**
- VS Code neu laden: `Ctrl+Shift+P` → "Developer: Reload Window"
- Container neu starten

## Weitere Informationen

- **Detaillierte Doku**: `docs/MCP-ATLASSIAN-SETUP.md`
- **VS Code Setup**: Gleiche Dokumentation (Projekt ist VS Code-spezifisch)
- **GitHub Repo**: https://github.com/sooperset/mcp-atlassian

## Konfigurationsdateien

- **Docker Compose**: `docker-compose.mcp-atlassian.yml` (im Projektroot)
- **VS Code MCP Config**: `.vscode/mcp.json`
- **VS Code Tasks**: `.vscode/tasks.json`
- **Scripts**: `scripts/mcp-atlassian/*.ps1`
