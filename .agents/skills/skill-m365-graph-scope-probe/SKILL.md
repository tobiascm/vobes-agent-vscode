---
name: skill-m365-graph-scope-probe
description: "Graph API Token-Scopes pruefen und Endpunkt-Faehigkeiten testen. Diagnose-Tool fuer Mail-Suche, Teams-Chat-Suche und Kanalnachrichten. Trigger: Graph Scopes pruefen, welche Scopes hat mein Token, Mail-Suche testen, Chat-Suche testen, Graph Probe, Token-Diagnose, fehlende Scopes, 403 Forbidden Ursache."
---

# Skill: M365 Graph API — Scope & Capability Probe

Diagnose-Skill: Prueft welche Scopes im aktuellen Graph-Token vorhanden sind und testet systematisch, welche Graph-Endpunkte damit funktionieren.

## Wann verwenden?

- Token-Scopes pruefen: "Welche Scopes hat mein Graph-Token?"
- Endpunkt-Diagnose: "Warum bekomme ich 403 bei der Mail-Suche?"
- Faehigkeiten testen: "Kann ich mit dem Token Chat-Nachrichten lesen?"
- Vor Skill-Entwicklung: "Funktioniert Mail-/Chat-Suche ueberhaupt mit dem aktuellen Token?"
- Admin-Rueckfrage vorbereiten: "Welche Scopes fehlen fuer Feature X?"

## Wann NICHT verwenden?

| Aufgabe | Stattdessen |
|---------|----|
| Dateien in SharePoint suchen | `$skill-m365-copilot-file-search` |
| Copilot-Frage stellen | `$skill-m365-copilot-chat` |
| Datei aus SharePoint lesen | `$skill-m365-file-reader` |
| Outlook-Mails durchsuchen (Produktiv) | `$skill-outlook` |

## Voraussetzungen

1. **Gueltiger Graph-Token** im Cache
   - Copilot-Token: `userdata/tmp/.graph_token_cache.json` (20 Scopes, KEIN Mail.Read)
   - Teams-Token: `userdata/tmp/.graph_token_cache_teams.json` (30 Scopes, MIT Mail.Read)
2. Token-Beschaffung: Playwright NAA (Copilot) oder Teams-Web localStorage
3. Python 3 mit `requests` installiert

## Token-Quellen

### Copilot-Token (Standard)
- App: M365ChatClient (`c0ab8ce9-...`)
- Quelle: `m365.cloud.microsoft/chat` via NAA
- **20 Scopes**, KEIN `Mail.Read`, KEIN `Chat.Read`
- Nutzen: File Search, Copilot Search

### Teams-Token (empfohlen fuer Mail-Suche)
- App: Microsoft Teams Web Client (`5e3ce6c0-...`)
- Quelle: `teams.microsoft.com/v2/` via localStorage MSAL-Cache
- **30 Scopes**, MIT `Mail.Read` + `Mail.ReadWrite`
- Nutzen: Mail-Suche via Graph Search API

### Teams-Token holen (Workflow)

1. Playwright auf Teams navigieren:
   ```
   mcp_playwright_browser_navigate(url="https://teams.microsoft.com/v2/")
   ```

2. Token aus localStorage extrahieren und in Datei speichern:
   ```javascript
   // via mcp_playwright_browser_evaluate mit filename Parameter:
   // filename: "userdata/tmp/.graph_token_cache_teams.json"
   async () => {
     const msalTokenKeysRaw = localStorage.getItem('msal.token.keys.5e3ce6c0-2b1f-4285-8d4b-75ee78787346');
     if (!msalTokenKeysRaw) return JSON.stringify({ error: 'No MSAL token keys' });
     const keys = JSON.parse(msalTokenKeysRaw);
     const accessTokenKeys = keys.accessToken || [];
     for (const atKey of accessTokenKeys) {
       const atRaw = localStorage.getItem(atKey);
       if (atRaw) {
         const atData = JSON.parse(atRaw);
         if (atData.target && atData.target.includes('graph.microsoft.com')) {
           const token = atData.secret;
           const parts = token.split('.');
           const payload = JSON.parse(atob(parts[1].replace(/-/g,'+').replace(/_/g,'/')));
           return JSON.stringify({ token: token, exp: payload.exp, source: 'teams-web' });
         }
       }
     }
     return JSON.stringify({ error: 'No Graph token found' });
   }
   ```

3. Token normalisieren und validieren:
   ```bash
   python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py cache-teams-token
   ```

4. Danach alle Befehle mit `--source teams`:
   ```bash
   python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py --source teams check-token
   python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py --source teams probe
   python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py --source teams search-mail "Suchbegriff"
   ```

## Workflow

### Schnell-Check: Token-Scopes anzeigen

```bash
python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py check-token
```

Zeigt: aud, appid, tid, upn, Ablaufzeit, alle Scopes, Present/Missing fuer relevante Scopes.

### Systematischer Test: Alle Endpunkte proben

```bash
python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py probe
```

Testet 10 Graph-Endpunkte und zeigt pro Test: Name, HTTP-Status, PASS/FAIL, benoetigter Scope.

### Gezielt: Mail-Suche testen

```bash
python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py search-mail "Abfrage Mehrarbeit Mai"
```

Testet `POST /v1.0/search/query` mit `entityTypes=["message"]`. Zeigt Treffer oder diagnostiziert fehlenden `Mail.Read` Scope.
Ausgabe: bis zu 10 Treffer mit `Subject`, `Von`, `Datum` und optional `webLink`.

### Gezielt: Chat-Suche testen

```bash
python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py search-chat "Abfrage Mehrarbeit Mai"
```

Testet `POST /v1.0/search/query` mit `entityTypes=["chatMessage"]`. Zeigt Treffer oder diagnostiziert fehlenden `Chat.Read` Scope.

### Komplett: Gesamtauswertung

```bash
python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py summary
```

Kombiniert Token-Analyse + Probe + Ergebnis-Matrix. Ausgabe direkt fuer Admin-/IT-Rueckfragen verwendbar.
Die Matrix umfasst: Token-Gueltigkeit, Restlaufzeit, Mail-Basiszugriff, Mail-Suche, Chats listen, Chat-Nachrichten lesen, Chat-Suche, Teams listen und Kanalnachrichten lesen.

### Mit explizitem Token

```bash
python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py --token BEARER_TOKEN check-token
python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py --token BEARER_TOKEN probe
```

## Befehle (Referenz)

| Befehl | Zweck |
|--------|-------|
| `check-token` | JWT dekodieren, Scopes auflisten, Present/Missing pruefen |
| `probe` | 10 Graph-Endpunkte systematisch testen |
| `search-mail "query"` | Mail-Suche via Search API testen |
| `search-chat "query"` | Chat-Suche via Search API testen |
| `summary` | Alles kombiniert + Ergebnis-Matrix |
| `cache-teams-token` | Teams-Token normalisieren und validieren |

### Globale Flags

| Flag | Wirkung |
|------|---------|
| `--source copilot` | Token aus M365 Copilot Cache (Standard) |
| `--source teams` | Token aus Teams Web Cache (hat Mail.Read) |
| `--token TOKEN` | Expliziter Bearer-Token |

## Exit-Codes

| Code | Bedeutung |
|------|-----------|
| 0 | Erfolgreich |
| 1 | Fehler (API-Fehler, fehlender Scope) |
| 2 | Token abgelaufen oder nicht vorhanden |

## Getestete Endpunkte (Probe)

| # | Endpunkt | Benoetigter Scope |
|---|----------|-------------------|
| 1 | `GET /v1.0/me` | User.Read |
| 2 | `GET /v1.0/me/messages?$top=3` | Mail.ReadBasic / Mail.Read |
| 3 | `GET /beta/me/chats?$top=5` | Chat.ReadBasic |
| 4 | `GET /v1.0/chats/{id}/messages?$top=3` | Chat.Read |
| 5 | `GET /v1.0/me/joinedTeams` | Team.ReadBasic.All |
| 6 | `GET /v1.0/teams/{id}/channels` | Channel.ReadBasic.All |
| 7 | `GET /v1.0/teams/{id}/channels/{id}/messages?$top=3` | ChannelMessage.Read.All |
| 8 | `POST /v1.0/search/query` (message) | Mail.Read |
| 9 | `POST /v1.0/search/query` (chatMessage) | Chat.Read |
| 10 | `POST /v1.0/search/query` (message+chatMessage) | Mail.Read + Chat.Read |

## Haeufige Fehlerbilder

| Fehler | Ursache | Naechster Schritt |
|--------|---------|-------------------|
| Exit 2: TOKEN_EXPIRED | Kein Token im Cache | Token via Playwright NAA holen (wie bei File Search Skill) |
| 401 Unauthorized | Token serverseitig abgelaufen | Neuen Token holen |
| 403 bei `me/messages` | `Mail.Read` oder `Mail.ReadBasic` fehlt | Scope bei Admin-Consent anfragen |
| 403 bei `chats/{id}/messages` | `Chat.ReadBasic` vorhanden, `Chat.Read` fehlt | `Chat.Read` benoetigt Admin-Consent |
| 403 bei `search/query` (message) | `Mail.Read` fehlt | Mail.Read Scope anfragen |
| 403 bei `search/query` (chatMessage) | `Chat.Read` fehlt | Chat.Read Scope anfragen |
| 403 bei Channel messages | `ChannelMessage.Read.All` fehlt | Scope bei Admin anfragen |
| SKIP bei Probe-Tests 4/6/7 | Keine Chats/Teams/Channels gefunden | Kein Fehler — Vorbedingung nicht erfuellt |

## Bekannte Scope-Situation (Stand April 2026)

### Copilot-Token (M365ChatClient `c0ab8ce9-...`)
- **Vorhanden:** Chat.ReadBasic, Channel.ReadBasic.All, Team.ReadBasic.All, Sites.ReadWrite.All, People.Read
- **Fehlend:** Mail.Read, Mail.ReadBasic, Chat.Read, ChannelMessage.Read.All, People.Read.All
- Mail-Suche: **403**
- Chat-Suche: **403**

### Teams-Token (Teams Web `5e3ce6c0-...`) — empfohlen
- **Vorhanden:** Mail.Read, Mail.ReadWrite, Channel.ReadBasic.All, Team.ReadBasic.All, Sites.ReadWrite.All, People.Read, ChatMember.Read
- **Fehlend:** Chat.ReadBasic, Chat.Read, ChannelMessage.Read.All, People.Read.All
- **Mail-Suche: 200 (funktioniert!)**
- Chat-Suche: **403**
- Chats listen: **403** (Chat.ReadBasic fehlt auch hier)

### Token-Vergleich

| Faehigkeit | Copilot-Token | Teams-Token |
|---|---|---|
| Mail lesen (messages) | 403 | **200** |
| Mail-Suche (Search API) | 403 | **200** |
| Chats listen | 200 | 403 |
| Chat-Nachrichten lesen | 403 | 403 |
| Chat-Suche | 403 | 403 |
| Teams listen | 200 | 200 |
| Channels listen | 200 | 200 |
| Kanalnachrichten lesen | 403 | 403 |

Fuer **Mail-Suche** den Teams-Token verwenden (`--source teams`).
Fuer **Chat-Suche und Kanalnachrichten** wird weiterhin `Chat.Read` / `ChannelMessage.Read.All` per Admin-Consent benoetigt.
