---
name: skill-m365-copilot-file-search
description: "M365 Copilot File Search ueber Graph Beta API ausfuehren. Durchsucht SharePoint und OneDrive mit Copilot-optimiertem Ranking. Nutze diesen Skill wenn der User nach Dokumenten, Praesentationen, PDFs oder Dateien im SharePoint / OneDrive suchen moechte, die ueber die normale Suche hinausgehen. Trigger: SharePoint durchsuchen, Dokument finden, M365 Suche, Copilot Suche, finde Datei in SharePoint, OneDrive durchsuchen, suche in M365."
---

# Skill: M365 Copilot File Search (Graph Beta API)

Durchsucht **SharePoint und OneDrive** ueber den Graph Beta Copilot Search Endpoint mit Copilot-optimiertem Ranking.

> **Dokumentation:** [docs/Analyse-m365-copilot-api-research.md](../../docs/Analyse-m365-copilot-api-research.md)

## Wann verwenden?

- Der User moechte **Dokumente in SharePoint oder OneDrive** finden
- Der User sucht nach **Praesentationen, PDFs, Excel-Dateien** im M365-Oekosystem
- Der User fragt: "Finde die Datei zu X", "Gibt es ein Dokument ueber Y im SharePoint?"
- Der User moechte die **M365 Copilot File Search** nutzen (gleiche Suchergebnisse wie im BizChat)

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| Confluence-Seiten durchsuchen | `local_rag` oder `mcp-atlassian` |
| Jira-Tickets durchsuchen | `local_rag` (KB `jira-vkon2`) oder `mcp-atlassian` |
| Copilot-Frage stellen und Antwort bekommen | `$skill-browse-intranet` (Playwright UI) |
| Intranet-Webseiten oeffnen | `$skill-browse-intranet` |

## Voraussetzungen

1. **Playwright MCP Server** muss aktiv sein (fuer Token-Beschaffung)
2. **M365-Sitzung** muss im Browser aktiv sein (SSO ueber Browser Extension)
3. User muss **M365 Copilot Lizenz** haben

### Pruefen ob MCP verfuegbar

```
tool_search_tool_regex(pattern="mcp_playwright")
```

Falls keine Ergebnisse → Skill nicht nutzbar (Plan-Modus oder MCP nicht gestartet).

---

## Workflow

> **Scripts:** `.agents/skills/skill-m365-copilot-file-search/copilot_file_search.py` + `scripts/m365_copilot_graph_token.py` — Search, automatische Token-Beschaffung via Playwright MCP/NAA, Caching und Formatierung.

### Schritt 1: Search ausfuehren

```bash
python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "SUCHBEGRIFF"
```

- **Exit 0** → Ergebnisse werden als Markdown-Tabelle ausgegeben. Fertig.
- Das Script ruft intern automatisch `python scripts/m365_copilot_graph_token.py ensure` auf.
- Der Token wird ueber Playwright MCP + `nestedAppAuthService.GetToken(...)` geholt, lokal gegen `/v1.0/me` validiert und in `userdata/tmp/.graph_token_cache.json` gespeichert.
- Fuer einen garantiert frischen Token:

```bash
python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "SUCHBEGRIFF" --force
```

### Schritt 2: Ergebnisse praesentieren

Das Script gibt die Treffer bereits als Markdown-Tabelle aus. Ausgabe direkt an den User weitergeben.

### Script-Befehle (Referenz)

| Befehl | Zweck |
|--------|-------|
| `python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "query"` | Suche ausfuehren (auto Resolver → API → Markdown) |
| `python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "query" --force` | Suche mit frischem NAA-Token, Cache ignorieren |
| `python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "query" --token TOKEN` | Debug-only: Suche mit explizitem Token |
| `python scripts/m365_copilot_graph_token.py ensure` | Gueltigen Token sicherstellen (Cache zuerst) |
| `python scripts/m365_copilot_graph_token.py ensure --force` | Frischen Token via MCP/NAA erzwingen |
| `python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py check-token` | Cache-Status pruefen |
| `python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py cache-token TOKEN [EXP]` | Debug-only: Token manuell in Cache speichern |

---

## API-Details

| Parameter | Wert |
|-----------|------|
| **Endpoint** | `POST https://graph.microsoft.com/beta/copilot/search` |
| **Auth** | Bearer Token (Graph API, `aud: https://graph.microsoft.com`) |
| **App-ID** | `c0ab8ce9-e9a0-42e7-b064-33d422df41f1` (M365ChatClient, NAA via Copilot) |
| **Request-Body** | `{"query": "<Suchanfrage>"}` |
| **Response** | `{"searchHits": [{webUrl, resourceType, preview}]}` |
| **Typische Treffer** | 25 pro Anfrage |
| **Quellen** | SharePoint, OneDrive, weitere M365-Inhalte |
| **Token-Laufzeit** | ca. 1 Stunde |


## Haeufige Fehler

| Fehler | Ursache | Loesung |
|--------|---------|---------|
| `NAA not ready` | Seite nicht geladen | `mcp_playwright_browser_wait_for` mit 3s, dann Retry |
| `Token request failed` | Session abgelaufen | User muss sich in M365 neu anmelden |
| `401 Unauthorized` | Token abgelaufen | Search erneut starten oder `--force` verwenden |
| `403 Forbidden` | Keine Copilot-Lizenz | User braucht M365 Copilot Lizenz |
| `CORS Error` (bei Python) | Sydney-NanoProxy | Nur im Browser ausfuehrbar, NICHT per Python/requests |

## Beispiel-Suchanfragen

```
"Meilensteine PEP"
"Bordnetz Spezifikation ID.1"
"Systemschaltplan Freigabe"
"KBL VEC Datenmodell"
"Projektplanung 2026"
```

### Warum dieser Endpoint statt `/v1.0/search/query`?

Der Copilot-Endpoint liefert **semantisch erweiterte Ergebnisse**. Beispiel fuer Query `AMOB@EK-corona.pdf`:
- **Copilot Search**: 6 Treffer — exakte Datei + 5 thematisch verwandte Dokumente
- **Graph Search** (`/v1.0/search/query`, `driveItem`): 1 Treffer — nur exakter Dateiname-Match

Fuer Dateisuche ist der Copilot-Endpoint deutlich besser, weil er semantischen Kontext mitbringt und verwandte Dokumente findet, nicht nur exakte Keyword-Matches.
