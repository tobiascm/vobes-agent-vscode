---
name: skill-browse-intranet
description: "Webseiten per Playwright MCP und Browser Extension oeffnen, navigieren, lesen und interagieren. Gilt fuer Intranet- UND externe Seiten. Nutze diesen Skill wenn der User eine Webseite oeffnen, durchsuchen, Daten extrahieren, Formulare ausfuellen, Screenshots machen oder mit einer beliebigen Webseite interagieren moechte — per Playwright MCP (nicht dev-browser). Trigger: oeffne Seite, geh auf URL, Intranet durchsuchen, interne Seite, VW-Webseite, Webseite oeffnen, Screenshot von Seite, Daten von Webseite extrahieren, Formular ausfuellen. Nicht für Confleunce oder Jira"
---

# Skill: Browse Intranet & Web

Generischer Skill zum Oeffnen und Interagieren mit **beliebigen Webseiten** (Intranet und extern) ueber den **Playwright MCP Server** und die **Browser Extension**.

## Wann verwenden?

- Der User moechte eine Webseite oeffnen, lesen oder durchsuchen
- Der User moechte Daten von einer Webseite extrahieren
- Der User moechte ein Formular ausfuellen oder auf Buttons klicken
- Der User moechte einen Screenshot einer Webseite machen
- Der User moechte eine authentifizierte Intranet-Seite (SSO/Kerberos) besuchen

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| Confluence / Jira lesen oder schreiben | `mcp-atlassian` (Skills `$skill-important-pages-links-and-urls`, `$skill-update-confluence-page`) |
| iProject / TE Regelwerk durchsuchen | `$skill-te-regelwerk` |
| BPLUS-NG Excel-Export | `$skill-budget-bplus-export` |
| Komplexe Multi-Page-Automation mit eigenem Server | `$skill-dev-browser` |

## Abgrenzung zu skill-dev-browser

| | **skill-browse-intranet** | **skill-dev-browser** |
|---|---|---|
| **Technologie** | Playwright MCP Server (`.vscode/mcp.json`) | Eigener Node-Server + Client-API |
| **Aufruf** | `mcp_playwright_browser_*` Tools direkt | `npx tsx` Scripts mit `connect()`/`page()` |
| **Auth** | Browser Extension uebernimmt Session (Kerberos/NTLM) | Standalone Chromium oder Extension-Relay |
| **Einsatz** | Schnelle Interaktion, Lesen, Screenshots | Komplexe Automationen, Scraping-Pipelines |

**Faustregel:** Fuer einzelne Seiten-Interaktionen → diesen Skill. Fuer mehrstufige Automationen mit Schleifen/Scraping → `skill-dev-browser`.

## Voraussetzungen

1. **Playwright MCP Server** muss aktiv sein (konfiguriert in `.vscode/mcp.json` unter `"playwright"`)
2. **Browser Extension** muss verbunden sein (Chrome Extension: Playwright MCP Bridge)
3. Fuer Intranet-Seiten: User muss im **VW-Netzwerk** authentifiziert sein (SSO-Session im Browser)

### Pruefen ob MCP verfuegbar

Vor dem ersten Tool-Aufruf mit `tool_search_tool_regex` pruefen:

```
tool_search_tool_regex(pattern="mcp_playwright")
```

Falls keine Ergebnisse → Playwright MCP ist nicht verfuegbar (Plan-Modus oder Server nicht gestartet).

## Verfuegbare MCP-Tools

| Tool | Zweck |
|------|-------|
| `mcp_playwright_browser_navigate` | URL oeffnen |
| `mcp_playwright_browser_navigate_back` | Zurueck navigieren |
| `mcp_playwright_browser_snapshot` | Accessibility-Tree / Seitenstruktur lesen |
| `mcp_playwright_browser_click` | Element anklicken |
| `mcp_playwright_browser_type` | Text eingeben (mit optionalem `submit=true`) |
| `mcp_playwright_browser_fill_form` | Formularfelder ausfuellen |
| `mcp_playwright_browser_select_option` | Dropdown-Option waehlen |
| `mcp_playwright_browser_hover` | Element hovern |
| `mcp_playwright_browser_drag` | Drag & Drop |
| `mcp_playwright_browser_press_key` | Taste druecken |
| `mcp_playwright_browser_take_screenshot` | Screenshot erstellen |
| `mcp_playwright_browser_evaluate` | JavaScript im Browser-Kontext ausfuehren |
| `mcp_playwright_browser_wait_for` | Warten (Zeit oder Selektor) |
| `mcp_playwright_browser_tabs` | Tabs auflisten / wechseln |
| `mcp_playwright_browser_console_messages` | Browser-Konsole lesen |
| `mcp_playwright_browser_network_requests` | Netzwerk-Requests inspizieren |
| `mcp_playwright_browser_file_upload` | Datei-Upload |
| `mcp_playwright_browser_handle_dialog` | Dialoge (alert/confirm/prompt) behandeln |
| `mcp_playwright_browser_resize` | Viewport-Groesse aendern |
| `mcp_playwright_browser_close` | Browser/Tab schliessen |

## Standard-Workflow

### 1. Seite oeffnen

```
mcp_playwright_browser_navigate(url="https://example.vw.vwg/seite")
```

### 2. Warten bis geladen

Viele Intranet-Seiten laden langsam (SPAs, SSO-Redirects). Warte initial:

```
mcp_playwright_browser_wait_for(time=3)
```

Bei bekannt langsamen Seiten (Confluence, iProject, SharePoint) bis zu 8 Sekunden warten.

### 3. Seitenstruktur lesen

```
mcp_playwright_browser_snapshot()
```

Der Snapshot liefert den Accessibility-Tree mit `[ref=eN]`-Referenzen fuer interagierbare Elemente.

### 4. Interagieren

```
mcp_playwright_browser_click(ref="e5", element="Beschreibung des Elements")
mcp_playwright_browser_type(ref="e10", text="Suchbegriff", submit=true)
```

### 5. Daten extrahieren

**Option A — Aus Snapshot:** Fuer sichtbaren Text reicht oft der Snapshot.

**Option B — Per JavaScript:** Fuer strukturierte Daten oder APIs:

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('/api/endpoint');
    const data = await resp.json();
    return JSON.stringify(data);
  }`
})
```

### 6. Screenshot

```
mcp_playwright_browser_take_screenshot()
```

## Authentifizierung (Intranet)

Die **Browser Extension** nutzt die bestehende Browser-Session. Wenn der User im Browser bereits angemeldet ist (Kerberos/NTLM/SSO), funktioniert die Authentifizierung automatisch.

**Wichtig:**
- `fetch()`-Aufrufe innerhalb von `mcp_playwright_browser_evaluate` uebernehmen die Session-Cookies des Browsers
- Direkte API-Aufrufe per PowerShell/curl funktionieren bei SSO-geschuetzten Seiten oft NICHT (403)
- Falls eine Seite eine Login-Seite zeigt → User bitten, sich manuell im Browser einzuloggen

## Typische Patterns

### SSO-Redirect

Viele Intranet-Seiten leiten zunaechst auf eine SSO-Login-Seite um. Nach dem Redirect:

1. `mcp_playwright_browser_wait_for(time=5)` — SSO-Redirect abwarten
2. `mcp_playwright_browser_snapshot()` — Pruefen ob Zielseite oder Login-Seite

### iframes

Einige Intranet-Apps (iProject, SharePoint) nutzen iframes. Der Snapshot zeigt iframe-Inhalte mit an. Falls ein Element im iframe liegt:

1. Snapshot machen — Refs sind auch fuer iframe-Elemente gueltig
2. Normal mit `ref=eN` interagieren

### SPAs (Single Page Applications)

Nach Navigation innerhalb einer SPA aendert sich die URL, aber die Seite macht keinen Fullpage-Load:

1. Nach Klick: `mcp_playwright_browser_wait_for(time=2)`
2. Erneut `mcp_playwright_browser_snapshot()` fuer aktualisierten Inhalt

### Datei-Downloads

Downloads landen im Standard-Download-Ordner des Browsers:

```powershell
Get-ChildItem "$env:USERPROFILE\Downloads" -Filter "*<Dateiname-Fragment>*" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name, Length, LastWriteTime
```

## Beispiele

### Beispiel 1: Intranet-Seite oeffnen und Inhalt lesen

```
mcp_playwright_browser_navigate(url="https://devstack.vwgroup.com/confluence/display/VOBES")
mcp_playwright_browser_wait_for(time=5)
mcp_playwright_browser_snapshot()
```

### Beispiel 2: Suche auf einer Webseite

```
mcp_playwright_browser_navigate(url="https://example.com")
mcp_playwright_browser_wait_for(time=3)
mcp_playwright_browser_snapshot()
# → Suchfeld identifizieren (z.B. ref=e5)
mcp_playwright_browser_click(ref="e5", element="Suchfeld")
mcp_playwright_browser_type(ref="e5", text="Suchbegriff", submit=true)
mcp_playwright_browser_wait_for(time=3)
mcp_playwright_browser_snapshot()
# → Ergebnisse aus Snapshot lesen
```

### Beispiel 3: API-Daten aus authentifiziertem Kontext laden

```
mcp_playwright_browser_navigate(url="https://intranet.vw.vwg/app")
mcp_playwright_browser_wait_for(time=5)
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('https://intranet.vw.vwg/api/data');
    if (!resp.ok) return JSON.stringify({ error: resp.status });
    const data = await resp.json();
    return JSON.stringify(data);
  }`
})
```

### Beispiel 4: Screenshot fuer Dokumentation

```
mcp_playwright_browser_navigate(url="https://example.com/dashboard")
mcp_playwright_browser_wait_for(time=5)
mcp_playwright_browser_take_screenshot()
```

## Troubleshooting

| Problem | Loesung |
|---------|---------|
| `mcp_playwright_*` Tools nicht verfuegbar | Playwright MCP Server nicht aktiv → in VS Code MCP-Panel pruefen |
| Seite zeigt Login-Formular statt Inhalt | Browser-Session abgelaufen → User bitten, sich manuell einzuloggen |
| Snapshot zeigt Extension-Seite statt Zielseite | `mcp_playwright_browser_tabs(action="list")` → richtigen Tab waehlen |
| Seite laedt nicht fertig | `mcp_playwright_browser_wait_for(time=8)` und erneut Snapshot |
| `fetch()` liefert 403 | Nur im Browser-Kontext (`evaluate`) moeglich, nicht per PowerShell/curl |
| Element nicht im Snapshot | Seite noch nicht geladen, oder Element in lazy-loaded Bereich → scrollen oder warten |
| Falscher Tab aktiv | `mcp_playwright_browser_tabs(action="list")` → Tab-ID ermitteln und wechseln |
