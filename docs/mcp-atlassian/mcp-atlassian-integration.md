# MCP Atlassian Integration

Integration des [MCP Atlassian Servers](https://github.com/sooperset/mcp-atlassian) für Zugriff auf VW Devstack Jira und Confluence.

## Übersicht

- **Docker Container**: `mcp-atlassian` (Port 8100)
- **MCP Server**: stdio-basiert über `docker exec`
- **Jira**: https://devstack.vwgroup.com/jira
- **Confluence**: https://devstack.vwgroup.com/confluence
- **VS Code Integration**: `.vscode/mcp.json` in `C:\Daten\Python\vobes_agent_vscode`

## Setup

### 1. Voraussetzungen

- Docker Desktop installiert und gestartet
- Umgebungsvariablen gesetzt:
  ```bash
  JIRA_PAT=<your_token>
  CONFLUENCE_PAT=<your_token>
  ```
- VS Code mit GitHub Copilot Extension

### 2. Container starten

**PowerShell:**
```powershell
C:\Daten\Python\lightrag_test\scripts\mcp-atlassian\start_mcp_atlassian.ps1
```

**Docker Compose:**
```bash
cd C:\Daten\Python\lightrag_test
docker-compose -f docker-compose.mcp-atlassian.yml up -d
```

**VS Code Tasks:**
1. `Ctrl+Shift+P` → "Tasks: Run Task"
2. Wähle "MCP Atlassian: Start"

### 3. Container stoppen

```powershell
C:\Daten\Python\lightrag_test\scripts\mcp-atlassian\stop_mcp_atlassian.ps1
```

### 4. Logs anzeigen

```powershell
C:\Daten\Python\lightrag_test\scripts\mcp-atlassian\logs_mcp_atlassian.ps1
```

## Konfiguration

### Docker Compose (`docker-compose.mcp-atlassian.yml`)

```yaml
services:
  mcp-atlassian:
    image: ghcr.io/sooperset/mcp-atlassian:0.21
    container_name: mcp-atlassian
    restart: "no"
    stdin_open: true
    tty: true
    entrypoint: ["/bin/sh"]
    command: ["-c", "tail -f /dev/null"]

    environment:
      JIRA_URL: https://devstack.vwgroup.com/jira
      JIRA_USERNAME: tobias.carsten.mueller@volkswagen.de
      JIRA_API_TOKEN: ${JIRA_PAT}
      CONFLUENCE_URL: https://devstack.vwgroup.com/confluence
      CONFLUENCE_USERNAME: tobias.carsten.mueller@volkswagen.de
      CONFLUENCE_API_TOKEN: ${CONFLUENCE_PAT}

    ports:
      - "8100:8000"
```

### VS Code MCP Konfiguration (`.vscode/mcp.json`)

```json
{
  "servers": {
    "mcp-atlassian": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "mcp-atlassian",
        "/app/.venv/bin/mcp-atlassian"
      ],
      "env": {
        "JIRA_URL": "https://devstack.vwgroup.com/jira",
        "JIRA_USERNAME": "tobias.carsten.mueller@volkswagen.de",
        "CONFLUENCE_URL": "https://devstack.vwgroup.com/confluence",
        "CONFLUENCE_USERNAME": "tobias.carsten.mueller@volkswagen.de"
      }
    }
  }
}
```

### Environment Variables (`.env`)

```bash
# MCP Atlassian (Docker Container)
MCP_ATLASSIAN_ENABLED=true
MCP_ATLASSIAN_HOST=127.0.0.1
MCP_ATLASSIAN_PORT=8100
```

## Verwendung in GitHub Copilot Chat

Nach dem Start des Containers kannst du MCP Atlassian Funktionen in Copilot Chat nutzen.

### Jira Beispiele

```
@workspace Suche alle offenen Issues im Projekt VKON2
@workspace Erstelle ein neues Issue im Projekt VKON2 mit Titel "Test Issue"
@workspace Zeige Details zu VKON2-1234
@workspace Liste alle Issues mit Label "bug" im Sprint "Sprint 1"
@workspace Füge einen Kommentar zu VKON2-1234 hinzu: "Review abgeschlossen"
@workspace Setze den Status von VKON2-1234 auf "In Progress"
```

### Confluence Beispiele

```
@workspace Suche nach "Stammdatenservice" in Confluence Space VOBES
@workspace Zeige mir die Confluence-Seite mit ID 123456789
@workspace Liste alle Seiten im Space VSUP
@workspace Erstelle eine neue Seite im Space VOBES mit Titel "Test Seite"
@workspace Füge einen Kommentar zur Seite 123456789 hinzu
@workspace Liste alle Attachments der Seite 123456789
```

### JQL Queries (Jira Query Language)

```
@workspace Suche Issues mit JQL: project = VKON2 AND status = "In Progress"
@workspace Suche Issues mit JQL: assignee = currentUser() AND resolution = Unresolved
@workspace Suche Issues mit JQL: created >= -7d ORDER BY created DESC
```

### CQL Queries (Confluence Query Language)

```
@workspace Suche Confluence-Seiten mit CQL: space = VOBES AND type = page
@workspace Suche Confluence-Seiten mit CQL: text ~ "Stammdatenservice" AND space = VSUP
@workspace Suche Confluence-Seiten mit CQL: created >= now("-30d")
```

## Verfügbare Funktionen

Das MCP Atlassian Tool bietet ~72 Funktionen:

### Jira Core Functions
- `jira_search_issues` - JQL-basierte Issue-Suche
- `jira_get_issue` - Issue-Details abrufen
- `jira_create_issue` - Neues Issue erstellen
- `jira_update_issue` - Issue aktualisieren
- `jira_transition_issue` - Status-Übergang durchführen
- `jira_add_comment` - Kommentar hinzufügen
- `jira_get_transitions` - Verfügbare Übergänge abrufen
- `jira_add_attachment` - Attachment hochladen
- `jira_delete_issue` - Issue löschen

### Confluence Core Functions
- `confluence_search_content` - CQL-basierte Content-Suche
- `confluence_get_page` - Seiten-Details abrufen
- `confluence_get_page_content` - Seiten-Inhalt abrufen
- `confluence_create_page` - Neue Seite erstellen
- `confluence_update_page` - Seite aktualisieren
- `confluence_delete_page` - Seite löschen
- `confluence_add_comment` - Kommentar hinzufügen
- `confluence_list_attachments` - Attachments auflisten
- `confluence_download_attachment` - Attachment herunterladen

### Advanced Functions
- Watcher-Management (Jira)
- Label-Management (Jira)
- Link-Management (Jira/Confluence)
- Space-Management (Confluence)
- User-Search (Jira/Confluence)
- Permissions-Management

## Architektur

### stdio-basierte MCP-Kommunikation

Der MCP Server läuft nicht als HTTP-Server, sondern kommuniziert über stdio (Standard Input/Output):

1. **VS Code** sendet MCP-Request über stdin
2. **Docker exec** leitet stdin an Container weiter
3. **mcp-atlassian** verarbeitet Request
4. **Antwort** wird über stdout zurückgesendet
5. **VS Code** empfängt und verarbeitet Response

### Container Lifecycle

- **Start**: Container läuft mit `tail -f /dev/null` (Keep-Alive)
- **Kommunikation**: Bei Bedarf via `docker exec -i mcp-atlassian /app/.venv/bin/mcp-atlassian`
- **Stop**: `docker-compose down` beendet Container

### Authentifizierung

- **Jira/Confluence PATs** werden als ENV-Variablen in Container übergeben
- **Keine PATs** in VS Code mcp.json (nur URLs und Username)
- **Tokens** bleiben in Container-Environment isoliert

## Troubleshooting

### Container läuft nicht

```powershell
# Status prüfen
docker ps -a | grep mcp-atlassian

# Logs prüfen
docker logs mcp-atlassian

# Neu starten
docker-compose -f C:\Daten\Python\lightrag_test\docker-compose.mcp-atlassian.yml restart
```

### Authentifizierung fehlschlägt

```powershell
# Prüfe, ob PATs gesetzt sind
echo $env:JIRA_PAT
echo $env:CONFLUENCE_PAT

# PATs neu setzen
$env:JIRA_PAT = "neues_token"
$env:CONFLUENCE_PAT = "neues_token"

# Container neu starten
docker-compose -f C:\Daten\Python\lightrag_test\docker-compose.mcp-atlassian.yml restart
```

### MCP Server antwortet nicht

```powershell
# Test: MCP Server im Container ausführen
docker exec -i mcp-atlassian /app/.venv/bin/mcp-atlassian --help

# Prüfe VS Code mcp.json Konfiguration
code C:\Daten\Python\vobes_agent_vscode\.vscode\mcp.json

# VS Code neu laden
# Ctrl+Shift+P -> "Developer: Reload Window"
```

### Rate Limits / Quota Exceeded

VW Devstack Jira/Confluence haben möglicherweise Rate Limits:

- **Jira**: ~100-200 Requests/Minute
- **Confluence**: ~100 Requests/Minute

Bei Quota-Errors:
- Requests reduzieren
- Batch-Size verkleinern
- Retry-Delay erhöhen

### Connection Timeout

```powershell
# Prüfe VPN-Verbindung zu VW Devstack
ping devstack.vwgroup.com

# Prüfe Netzwerk im Container
docker exec mcp-atlassian ping devstack.vwgroup.com
```

## Sicherheit

### PAT-Management

- **Niemals** PATs in Git commiten
- **Niemals** PATs in mcp.json speichern
- **Immer** ENV-Variablen oder Docker Secrets verwenden

### PAT erneuern

1. Besuche: https://id.atlassian.com/manage-profile/security/api-tokens
2. Erstelle neuen API Token
3. Setze neue ENV-Variablen
4. Starte Container neu

### Best Practices

- PATs regelmäßig rotieren (alle 90 Tage)
- Minimale Permissions für PATs
- Separate PATs für Dev/Test/Prod
- Logging von API-Zugriffen

## Performance

### Optimierungen

- **Caching**: MCP Server cached API-Responses (Memory)
- **Batch Requests**: Nutze Batch-APIs für Multiple Operations
- **Pagination**: Limitiere Ergebnisse mit `maxResults`
- **Field Selection**: Nutze `fields` Parameter um nur benötigte Daten zu laden

### Monitoring

```powershell
# Container Resource Usage
docker stats mcp-atlassian

# Container Logs (Live)
docker logs mcp-atlassian -f --tail 100

# Network Traffic
docker exec mcp-atlassian netstat -an
```

## Weiterführende Ressourcen

- **MCP Atlassian GitHub**: https://github.com/sooperset/mcp-atlassian
- **MCP Protocol Spec**: https://modelcontextprotocol.io
- **Jira REST API**: https://docs.atlassian.com/jira-software/REST/latest/
- **Confluence REST API**: https://developer.atlassian.com/cloud/confluence/rest/v2/intro/
- **VW Devstack Jira**: https://devstack.vwgroup.com/jira
- **VW Devstack Confluence**: https://devstack.vwgroup.com/confluence

## Support

Bei Problemen:
1. Prüfe Logs: `docker logs mcp-atlassian`
2. Prüfe GitHub Issues: https://github.com/sooperset/mcp-atlassian/issues
3. Erstelle Issue mit:
   - Fehlermeldung
   - Docker-Logs
   - VS Code MCP Konfiguration (ohne PATs!)
   - Steps to Reproduce
