# VOBES Agent VS Code Workspace

VS Code Workspace für VOBES-bezogene Entwicklung mit dem VOBES-Agent und weiteren Tools/Skills wie z.B. MCP Atlassian Integration für Confluence und Jira

## Quick Start

### VOBES-Agent-MCP

TODO

### 1. MCP Atlassian Container starten

```powershell
# Via VS Code Task (empfohlen)
Ctrl+Shift+P → "Tasks: Run Task" → "MCP Atlassian: Start"

# Oder via PowerShell
.\scripts\mcp-atlassian\start.ps1

# Oder via Docker Compose
docker-compose -f docker-compose.mcp-atlassian.yml up -d
```

### 2. In Copilot Chat nutzen

```
@workspace Liste alle Seiten im Confluence Space EKEK1
@workspace Suche Issues im Projekt VKON2
```

## Dokumentation

- **Quick Start**: `docs/MCP-ATLASSIAN-QUICKSTART.md`
- **Detailliertes Setup**: `docs/MCP-ATLASSIAN-SETUP.md`
- **Skill (Confluence Update, MCP-only)**: `docs/SKILL-UPDATE-CONFLUENCE-PAGE.md`

## Konfiguration

- **MCP Server**: `.vscode/mcp.json`
- **VS Code Tasks**: `.vscode/tasks.json`
- **Docker Compose**: `docker-compose.mcp-atlassian.yml`
- **Scripts**: `scripts/mcp-atlassian/*.ps1`

## Voraussetzungen

- Docker Desktop
- VS Code mit GitHub Copilot Extension
- Umgebungsvariablen: `JIRA_PAT` und `CONFLUENCE_PAT`

## Verfügbare Spaces

- **Confluence**: VOBES, VSUP, EKEK1
- **Jira**: VKON2, VOBES, VSUP, EKEK1

## Ressourcen

- **VW Devstack Jira**: https://devstack.vwgroup.com/jira
- **VW Devstack Confluence**: https://devstack.vwgroup.com/confluence
- **MCP Atlassian GitHub**: https://github.com/sooperset/mcp-atlassian
