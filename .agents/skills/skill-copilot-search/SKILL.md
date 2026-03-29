---
name: skill-copilot-search
description: "M365 Copilot Search ueber Graph Beta API ausfuehren. Durchsucht SharePoint, OneDrive und weitere M365-Quellen mit Copilot-Ranking. Nutze diesen Skill wenn der User nach Dokumenten, Praesentationen, PDFs oder Dateien im SharePoint / OneDrive suchen moechte, die ueber die normale Suche hinausgehen. Trigger: SharePoint durchsuchen, Dokument finden, M365 Suche, Copilot Suche, finde Datei in SharePoint, OneDrive durchsuchen, suche in M365."
---

# Skill: M365 Copilot Search (Graph Beta API)

Durchsucht **SharePoint, OneDrive und weitere M365-Quellen** ueber den Graph Beta Copilot Search Endpoint mit Copilot-optimiertem Ranking.

> **Dokumentation:** [docs/m365-copilot-api-research.md](../../docs/m365-copilot-api-research.md)

## Wann verwenden?

- Der User moechte **Dokumente in SharePoint oder OneDrive** finden
- Der User sucht nach **Praesentationen, PDFs, Excel-Dateien** im M365-Oekosystem
- Der User fragt: "Finde die Datei zu X", "Gibt es ein Dokument ueber Y im SharePoint?"
- Der User moechte die **M365 Copilot Search** nutzen (gleiche Suchergebnisse wie im BizChat)

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

> **Script:** `scripts/copilot_search.py` — Token-Caching, Search-Aufruf und Formatierung in einem Script.

### Schritt 1: Search ausfuehren

```bash
# via run_in_terminal
python scripts/copilot_search.py search "SUCHBEGRIFF"
```

- **Exit 0** → Ergebnisse werden als Markdown-Tabelle ausgegeben. Fertig.
- **Exit 2** → `TOKEN_EXPIRED` auf stderr. Weiter zu Schritt 2.
- **Exit 1** → sonstiger Fehler (Meldung auf stderr).

### Schritt 2: Token via Playwright NAA holen (nur bei Exit 2)

**2a.** M365 Copilot oeffnen:

```
mcp_playwright_browser_navigate(url="https://m365.cloud.microsoft/chat")
```

**3 Sekunden warten** (damit `nestedAppAuthService` verfuegbar wird).

**2b.** Token extrahieren:

```javascript
// via mcp_playwright_browser_evaluate
async () => {
  const nas = window.nestedAppAuthService;
  if (!nas) return { error: 'NAA not ready — page not fully loaded' };

  const result = await nas.handleRequest({
    method: 'GetToken',
    requestId: 'copilot-search-' + Date.now(),
    tokenParams: {
      clientId: 'c0ab8ce9-e9a0-42e7-b064-33d422df41f1',
      resource: 'https://graph.microsoft.com',
      scope: 'https://graph.microsoft.com/.default'
    }
  }, new URL(window.location.href));

  if (!result.success || !result.token?.access_token) {
    return { error: 'Token request failed', details: result.error };
  }
  return { success: true, token: result.token.access_token };
}
```

**2c.** Token cachen (mit automatischer Validierung) und Search erneut ausfuehren:

```bash
# Token cachen — prueft automatisch gegen /v1.0/me
python scripts/copilot_search.py cache-token TOKEN_AUS_2B

# Search erneut
python scripts/copilot_search.py search "SUCHBEGRIFF"
```

**Fehlerbehandlung:**
- `NAA not ready` → `mcp_playwright_browser_wait_for` mit 3s, dann Retry (max. 2x)
- `Token request failed` → M365-Session abgelaufen, User muss sich neu anmelden
- `cache-token` liefert **Exit 2** (Token serverseitig ungueltig trotz gueltigem JWT-Claim):
  1. M365-Seite neu laden (`mcp_playwright_browser_navigate` erneut)
  2. 5 Sekunden warten
  3. Token erneut via NAA holen (Schritt 2b)
  4. `cache-token` erneut ausfuehren
  5. Maximal **2 Versuche** — danach Fehler an User melden

### Schritt 3: Ergebnisse praesentieren

Das Script gibt die Treffer bereits als Markdown-Tabelle aus. Ausgabe direkt an den User weitergeben.

### Script-Befehle (Referenz)

| Befehl | Zweck |
|--------|-------|
| `python scripts/copilot_search.py search "query"` | Suche ausfuehren (Cache → API → Markdown) |
| `python scripts/copilot_search.py search "query" --token TOKEN` | Suche mit explizitem Token (wird auch gecacht) |
| `python scripts/copilot_search.py cache-token TOKEN [EXP]` | Token in Cache speichern |
| `python scripts/copilot_search.py check-token` | Cache-Status pruefen |

---

## API-Details

| Parameter | Wert |
|-----------|------|
| **Endpoint** | `POST https://graph.microsoft.com/beta/copilot/microsoft.graph.search` |
| **Auth** | Bearer Token (Graph API, `aud: https://graph.microsoft.com`) |
| **App-ID** | `c0ab8ce9-e9a0-42e7-b064-33d422df41f1` (M365ChatClient) |
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
| `401 Unauthorized` | Token abgelaufen | Schritt 2 erneut ausfuehren |
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
