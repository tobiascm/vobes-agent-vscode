---
name: skill-sharepoint-lists
description: "SharePoint-Listen per REST API ueber Playwright-Browser-Session lesen. Listet verfuegbare Listen, liest Eintraege (einzeln, gefiltert, alle), extrahiert Feld-Metadaten. Auth laeuft ueber die bestehende Browser-Session (Kerberos/SSO). Trigger: SharePoint-Liste lesen, Listen-Eintraege abrufen, SharePoint Items filtern, Listendaten extrahieren, SharePoint REST API, DispForm-Daten lesen."
---

# Skill: SharePoint Lists (REST API via Playwright)

Liest **SharePoint-Listen** ueber die REST API (`_api/Web/Lists`) im Kontext der Playwright-Browser-Session. Authentifizierung erfolgt automatisch ueber die bestehende SSO-Session des Browsers.

## Wann verwenden?

- Daten aus einer **SharePoint-Liste** lesen (Items, Felder, Metadaten)
- **Einzelnes Item** per ID laden (z.B. von einer DispForm.aspx-URL)
- **Gefilterte Abfrage** auf einer SharePoint-Liste (OData `$filter`)
- **Alle Items** einer Liste abrufen (mit Paging)
- **Feld-Definitionen** einer Liste inspizieren (Spaltentypen, interne Namen)

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| **Dateien** aus SharePoint/OneDrive lesen (PPTX, XLSX etc.) | `$skill-m365-file-reader` |
| Dateien in SharePoint **suchen** | `$skill-m365-copilot-file-search` |
| Beliebige Webseite oeffnen / Screenshot | `$skill-browse-intranet` |
| Confluence/Jira | `mcp-atlassian` |

## Voraussetzungen

1. **Playwright MCP Server** aktiv (`.vscode/mcp.json`)
2. **Browser Extension** verbunden (Playwright MCP Bridge)
3. User im **SSO/Kerberos-Netz** authentifiziert (SharePoint-Session im Browser)

## Kernkonzept

SharePoint-Listen haben eine **REST API** unter:
```
https://{tenant}.sharepoint.com/sites/{site}/_api/Web/Lists
```

Alle Aufrufe laufen per `playwright-browser_evaluate` → `fetch()` im Browser-Kontext, damit die SSO-Cookies automatisch mitgeschickt werden. **Kein** PowerShell/curl moeglich (403 bei SSO).

## Schritt-fuer-Schritt

### 1. SharePoint-Seite annavigieren (Session sicherstellen)

Bevor `fetch()` aufgerufen wird, MUSS der Browser auf der richtigen SharePoint-Site sein:

```
playwright-browser_navigate(url="https://{tenant}.sharepoint.com/sites/{site}")
playwright-browser_wait_for(time=3)
```

### 2. Listen einer Site ermitteln

```js
playwright-browser_evaluate({
  function: `async () => {
    const r = await fetch("/_api/Web/Lists?$filter=Hidden eq false&$select=Title,Id,ItemCount", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify(d.d.results.map(l => ({
      title: l.Title, guid: l.Id, count: l.ItemCount
    })));
  }`
})
```

### 3. Feld-Definitionen einer Liste abrufen

Wichtig zum Verstaendnis der internen Feldnamen (SharePoint kodiert Sonderzeichen als `_x00XX_`):

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';  // List-GUID
    const r = await fetch("/_api/Web/Lists(guid'" + GUID + "')/Fields?$filter=Hidden eq false&$select=Title,InternalName,TypeAsString", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify(d.d.results.map(f => ({
      display: f.Title, internal: f.InternalName, type: f.TypeAsString
    })));
  }`
})
```

### 4. Einzelnes Item per ID laden

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
    const ID = 33;
    const r = await fetch("/_api/Web/Lists(guid'" + GUID + "')/items(" + ID + ")", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    // Alle nicht-leeren Felder zurueckgeben
    const fields = {};
    for (const [k, v] of Object.entries(d.d)) {
      if (v !== null && v !== '' && typeof v !== 'object' && !k.startsWith('__') && !k.startsWith('odata'))
        fields[k] = v;
    }
    return JSON.stringify(fields);
  }`
})
```

### 5. Mehrere Items per ID-Liste (Batch)

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
    const IDS = [33, 102, 110];
    const results = {};
    for (const id of IDS) {
      const r = await fetch("/_api/Web/Lists(guid'" + GUID + "')/items(" + id + ")", {
        headers: { 'Accept': 'application/json;odata=verbose' }
      });
      if (r.ok) {
        const d = await r.json();
        const fields = {};
        for (const [k, v] of Object.entries(d.d)) {
          if (v !== null && v !== '' && typeof v !== 'object' && !k.startsWith('__') && !k.startsWith('odata'))
            fields[k] = v;
        }
        results[id] = fields;
      } else {
        results[id] = { error: r.status };
      }
    }
    return JSON.stringify(results);
  }`
})
```

### 6. Items mit OData-Filter

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
    const FILTER = "Bereich eq 'EK'";
    const TOP = 100;
    const r = await fetch("/_api/Web/Lists(guid'" + GUID + "')/items?$filter=" + encodeURIComponent(FILTER) + "&$top=" + TOP, {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify({ count: d.d.results.length, items: d.d.results });
  }`
})
```

### 7. Alle Items mit Paging (grosse Listen)

SharePoint liefert max. 100 Items pro Request. Fuer groessere Listen:

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
    let url = "/_api/Web/Lists(guid'" + GUID + "')/items?$top=100";
    const all = [];
    while (url) {
      const r = await fetch(url, {
        headers: { 'Accept': 'application/json;odata=verbose' }
      });
      const d = await r.json();
      all.push(...d.d.results);
      url = d.d.__next || null;
    }
    return JSON.stringify({ total: all.length, items: all });
  }`
})
```

### 8. List-GUID aus Listennamen ermitteln

```js
playwright-browser_evaluate({
  function: `async () => {
    const NAME = 'KI-Portfolio';
    const r = await fetch("/_api/Web/Lists?$filter=Title eq '" + NAME + "'&$select=Title,Id,ItemCount", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    if (d.d.results.length === 0) return JSON.stringify({ error: 'List not found' });
    const l = d.d.results[0];
    return JSON.stringify({ title: l.Title, guid: l.Id, count: l.ItemCount });
  }`
})
```

### 9. DispForm-URL → Item-ID extrahieren

Aus einer URL wie `DispForm.aspx?ID=344` die ID extrahieren:

```js
const id = new URL(url).searchParams.get('ID');
```

## Bekannte Pitfalls

### Feldnamen-Encoding

SharePoint kodiert Sonderzeichen in internen Feldnamen:

| Zeichen | Encoding |
|---------|----------|
| Leerzeichen | `_x0020_` |
| Klammer `(` | `_x0028_` |
| Klammer `)` | `_x0029_` |
| Bindestrich `-` | `_x002d_` |
| Punkt `.` | `_x002e_` |
| Umlaut `ä` | `_x00e4_` |
| Umlaut `ö` | `_x00f6_` |
| Umlaut `ü` | `_x00fc_` |
| Euro `€` | `_x20ac_` |
| Slash `/` | `_x002f_` |

Beispiel: `Wirkung € EK` → interner Name enthaelt `_x20ac_` und `_x0020_`.

**Empfehlung:** Bei `$select` lieber KEINE Feldnamen angeben (alle Felder laden), statt an der Encoding zu scheitern. Filtern dann client-seitig in JS.

### Ergebnis-Groesse

Bei grossen Ergebnissen kann die Playwright-`evaluate`-Rueckgabe abgeschnitten werden. Strategien:
- `$select` verwenden (nur benoetigte Felder)
- Ergebnis in `.playwright-mcp/`-Datei schreiben lassen (via `filename`-Parameter)
- Items in Batches laden

### $select mit Sonderzeichen-Feldern

`$select=Wirkung_x0020__x20ac__x0020_EK` → liefert oft **400 Bad Request**. Besser: Alle Felder laden und client-seitig filtern.

### Relative URLs

`fetch()` im Browser-Kontext unterstuetzt relative URLs. Wenn der Browser bereits auf der richtigen SharePoint-Site ist, reicht:
```js
fetch("/_api/Web/Lists(...)")
```
Ansonsten die volle URL verwenden.

## Bekannte Listen (Referenz)

| Site | Liste | GUID | Beschreibung |
|------|-------|------|--------------|
| KI-KreisTechnischeEntwicklungVW | KI-Portfolio | `45243118-abdd-4036-84b9-128b8ba4525e` | KI-Projekte der TE mit Wirkungsschaetzung |

## Troubleshooting

| Problem | Loesung |
|---------|---------|
| `fetch()` liefert 403 | Browser nicht auf der richtigen Site → erst `navigate` ausfuehren |
| `fetch()` liefert 404 | List-GUID falsch → per Listennamen neu ermitteln (Schritt 8) |
| `fetch()` liefert 400 bei `$select` | Feldnamen-Encoding falsch → `$select` weglassen, client-seitig filtern |
| Ergebnis `undefined` | JSON zu gross → in Datei speichern oder Batch-Abruf verwenden |
| `playwright-browser_evaluate` nicht verfuegbar | Playwright MCP nicht aktiv → VS Code MCP-Panel pruefen |
| Nur 100 Items zurueck | SharePoint-Paging → Schritt 7 verwenden |
