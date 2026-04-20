---
name: skill-sharepoint
description: "SharePoint-Daten per REST API ueber Playwright-Browser-Session lesen. Listen (Items, Felder, Filter, Paging), Dokumentbibliotheken (Ordner, Dateien), Site-Metadaten, Suche, Site Pages und Berechtigungen. Auth laeuft ueber die bestehende Browser-Session (Kerberos/SSO). Trigger: SharePoint-Liste lesen, Listen-Eintraege abrufen, SharePoint Items filtern, Listendaten extrahieren, SharePoint REST API, DispForm-Daten lesen, SharePoint-Ordner auflisten, SharePoint-Suche, Site-Metadaten, SharePoint Dokumentbibliothek, SharePoint Pages."
---

# Skill: SharePoint (REST API via Playwright)

Liest **SharePoint-Daten** ueber die REST API im Kontext der Playwright-Browser-Session. Authentifizierung erfolgt automatisch ueber die bestehende SSO-Session des Browsers.

## Wann verwenden?

- Daten aus einer **SharePoint-Liste** lesen (Items, Felder, Filter, Paging)
- **Einzelnes Item** per ID laden (z.B. von einer DispForm.aspx-URL)
- **Dokumentbibliothek** durchsuchen (Ordner, Dateien, Metadaten)
- **SharePoint-Suche** ausfuehren (Volltextsuche ueber Sites)
- **Site-Metadaten** abrufen (Titel, Subsites, Navigation)
- **Site Pages** lesen (Modern Pages)
- **Benutzer/Gruppen** einer Site abfragen

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| **Datei-Inhalt** lesen (PPTX, XLSX, DOCX, PDF) | `$skill-m365-file-reader` |
| Dateien in SharePoint **suchen** (Copilot-Ranking) | `$skill-m365-copilot-file-search` |
| Beliebige Webseite oeffnen / Screenshot | `$skill-browse-intranet` |
| Confluence/Jira | `mcp-atlassian` |

## Voraussetzungen

1. **Playwright MCP Server** aktiv (`.vscode/mcp.json`)
2. **Browser Extension** verbunden (Playwright MCP Bridge)
3. User im **SSO/Kerberos-Netz** authentifiziert (SharePoint-Session im Browser)

## Kernkonzept

Alle Aufrufe laufen per `playwright-browser_evaluate` → `fetch()` im Browser-Kontext, damit die SSO-Cookies automatisch mitgeschickt werden. **Kein** PowerShell/curl moeglich (403 bei SSO).

**Basis-URL:**
```
https://{tenant}.sharepoint.com/sites/{site}/_api/...
```

**WICHTIG:** Vor dem ersten `fetch()` MUSS der Browser auf der richtigen SharePoint-Site navigiert sein.

```
playwright-browser_navigate(url="https://{tenant}.sharepoint.com/sites/{site}")
playwright-browser_wait_for(time=3)
```

---

## A. Listen (Items, Felder, Filter)

### A1. Listen einer Site ermitteln

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

### A2. List-GUID aus Listennamen ermitteln

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

### A3. Feld-Definitionen einer Liste

Zeigt interne Feldnamen (SharePoint kodiert Sonderzeichen als `_x00XX_`):

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
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

### A4. Einzelnes Item per ID

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
    const ID = 33;
    const r = await fetch("/_api/Web/Lists(guid'" + GUID + "')/items(" + ID + ")", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    const fields = {};
    for (const [k, v] of Object.entries(d.d)) {
      if (v !== null && v !== '' && typeof v !== 'object' && !k.startsWith('__') && !k.startsWith('odata'))
        fields[k] = v;
    }
    return JSON.stringify(fields);
  }`
})
```

### A5. Mehrere Items per ID-Liste (Batch)

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

### A6. Items mit OData-Filter

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
    const FILTER = "Bereich eq 'EK'";
    const r = await fetch("/_api/Web/Lists(guid'" + GUID + "')/items?$filter=" + encodeURIComponent(FILTER) + "&$top=100", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify({ count: d.d.results.length, items: d.d.results });
  }`
})
```

### A7. Alle Items mit Paging (grosse Listen)

SharePoint liefert max. 100 Items pro Request:

```js
playwright-browser_evaluate({
  function: `async () => {
    const GUID = '...';
    let url = "/_api/Web/Lists(guid'" + GUID + "')/items?$top=100";
    const all = [];
    while (url) {
      const r = await fetch(url, { headers: { 'Accept': 'application/json;odata=verbose' } });
      const d = await r.json();
      all.push(...d.d.results);
      url = d.d.__next || null;
    }
    return JSON.stringify({ total: all.length, items: all });
  }`
})
```

### A8. DispForm-URL → Item-ID

```js
const id = new URL("https://...DispForm.aspx?ID=344").searchParams.get('ID');
```

---

## B. Dokumentbibliotheken (Ordner & Dateien)

### B1. Ordner-Inhalt auflisten

```js
playwright-browser_evaluate({
  function: `async () => {
    const PATH = '/sites/MySite/Shared Documents/Subfolder';
    const r = await fetch("/_api/Web/GetFolderByServerRelativeUrl('" + PATH + "')?$expand=Folders,Files", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    const folders = d.d.Folders.results.map(f => ({ name: f.Name, itemCount: f.ItemCount }));
    const files = d.d.Files.results.map(f => ({ name: f.Name, size: f.Length, modified: f.TimeLastModified, url: f.ServerRelativeUrl }));
    return JSON.stringify({ folders, files });
  }`
})
```

### B2. Datei-Metadaten

```js
playwright-browser_evaluate({
  function: `async () => {
    const PATH = '/sites/MySite/Shared Documents/report.xlsx';
    const r = await fetch("/_api/Web/GetFileByServerRelativeUrl('" + PATH + "')", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify({
      name: d.d.Name, size: d.d.Length, modified: d.d.TimeLastModified,
      version: d.d.UIVersionLabel, checkedOut: d.d.CheckOutType !== 2
    });
  }`
})
```

### B3. Datei-Download-URL erzeugen

```js
// Direkter Download-Link (Browser-Session noetig):
const url = "/_api/Web/GetFileByServerRelativeUrl('" + PATH + "')/$value";
```

> **Hinweis:** Zum Lesen des Datei-INHALTS (PPTX, XLSX etc.) besser `$skill-m365-file-reader` verwenden.

---

## C. Suche

### C1. Volltextsuche ueber SharePoint

```js
playwright-browser_evaluate({
  function: `async () => {
    const QUERY = 'KI Bordnetz';
    const r = await fetch("/_api/search/query?querytext='" + encodeURIComponent(QUERY) + "'&rowlimit=10&selectproperties='Title,Path,Author,LastModifiedTime'", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    const rows = d.d.query.PrimaryQueryResult.RelevantResults.Table.Rows.results;
    return JSON.stringify(rows.map(r => {
      const cells = {};
      r.Cells.results.forEach(c => { if (c.Value) cells[c.Key] = c.Value; });
      return { title: cells.Title, path: cells.Path, author: cells.Author, modified: cells.LastModifiedTime };
    }));
  }`
})
```

### C2. Suche einschraenken auf eine Site

```js
const QUERY = "KI Bordnetz site:https://volkswagengroup.sharepoint.com/sites/MySite";
```

### C3. Suche nach Dateityp

```js
const QUERY = "KI filetype:pptx";
```

---

## D. Site-Metadaten

### D1. Site-Informationen

```js
playwright-browser_evaluate({
  function: `async () => {
    const r = await fetch("/_api/Web?$select=Title,Url,Description,Created,LastItemModifiedDate", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify({ title: d.d.Title, url: d.d.Url, description: d.d.Description, created: d.d.Created, lastModified: d.d.LastItemModifiedDate });
  }`
})
```

### D2. Subsites auflisten

```js
playwright-browser_evaluate({
  function: `async () => {
    const r = await fetch("/_api/Web/Webs?$select=Title,Url,Created", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify(d.d.results.map(w => ({ title: w.Title, url: w.Url })));
  }`
})
```

### D3. Navigation (Quick Launch)

```js
playwright-browser_evaluate({
  function: `async () => {
    const r = await fetch("/_api/Web/Navigation/QuickLaunch", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify(d.d.results.map(n => ({ title: n.Title, url: n.Url })));
  }`
})
```

---

## E. Site Pages

### E1. Alle Pages einer Site

```js
playwright-browser_evaluate({
  function: `async () => {
    const r = await fetch("/_api/SitePages/Pages?$select=Id,Title,Url,Modified,AuthorByline&$top=50", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify(d.d.results.map(p => ({
      id: p.Id, title: p.Title, url: p.Url, modified: p.Modified
    })));
  }`
})
```

### E2. Einzelne Page lesen (Canvas-Content)

```js
playwright-browser_evaluate({
  function: `async () => {
    const PAGE_ID = 5;
    const r = await fetch("/_api/SitePages/Pages(" + PAGE_ID + ")?$select=Title,CanvasContent1,Modified", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify({ title: d.d.Title, modified: d.d.Modified, content: d.d.CanvasContent1 });
  }`
})
```

---

## F. Benutzer & Gruppen

### F1. Site-Benutzer

```js
playwright-browser_evaluate({
  function: `async () => {
    const r = await fetch("/_api/Web/SiteUsers?$select=Title,Email,LoginName&$filter=Email ne ''&$top=200", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify(d.d.results.map(u => ({ name: u.Title, email: u.Email })));
  }`
})
```

### F2. Site-Gruppen

```js
playwright-browser_evaluate({
  function: `async () => {
    const r = await fetch("/_api/Web/SiteGroups?$select=Title,Id,OwnerTitle", {
      headers: { 'Accept': 'application/json;odata=verbose' }
    });
    const d = await r.json();
    return JSON.stringify(d.d.results.map(g => ({ title: g.Title, id: g.Id, owner: g.OwnerTitle })));
  }`
})
```

---

## Bekannte Pitfalls

### Feldnamen-Encoding (Listen)

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

**Empfehlung:** Bei `$select` lieber KEINE Feldnamen angeben (alle Felder laden), statt an der Encoding zu scheitern. Filtern dann client-seitig in JS.

### $select mit Sonderzeichen-Feldern

`$select=Wirkung_x0020__x20ac__x0020_EK` → liefert oft **400 Bad Request**. Besser: Alle Felder laden und client-seitig filtern.

### Ergebnis-Groesse

Bei grossen Ergebnissen kann die Playwright-`evaluate`-Rueckgabe abgeschnitten werden. Strategien:
- `$select` verwenden (nur benoetigte Felder)
- Ergebnis in `.playwright-mcp/`-Datei schreiben lassen (via `filename`-Parameter)
- Items in Batches laden

### Relative URLs

`fetch()` im Browser-Kontext unterstuetzt relative URLs. Wenn der Browser bereits auf der richtigen SharePoint-Site ist, reicht `/_api/...`. Ansonsten die volle URL verwenden.

### ServerRelativeUrl fuer Dateien/Ordner

Dokumentbibliothek-Pfade muessen als **ServerRelativeUrl** angegeben werden, z.B. `/sites/MySite/Shared Documents/Subfolder`. Den genauen Pfad kann man ueber die Ordner-API (B1) oder die Site-Navigation (D3) herausfinden.

## Bekannte Listen (Referenz)

| Site | Liste | GUID | Beschreibung |
|------|-------|------|--------------|
| KI-KreisTechnischeEntwicklungVW | KI-Portfolio | `45243118-abdd-4036-84b9-128b8ba4525e` | KI-Projekte der TE mit Wirkungsschaetzung |

## Troubleshooting

| Problem | Loesung |
|---------|---------|
| `fetch()` liefert 403 | Browser nicht auf der richtigen Site → erst `navigate` ausfuehren |
| `fetch()` liefert 404 | List-GUID oder Pfad falsch → per Listennamen (A2) oder Ordner-API (B1) pruefen |
| `fetch()` liefert 400 bei `$select` | Feldnamen-Encoding falsch → `$select` weglassen, client-seitig filtern |
| Ergebnis `undefined` | JSON zu gross → in Datei speichern oder Batch-Abruf verwenden |
| `playwright-browser_evaluate` nicht verfuegbar | Playwright MCP nicht aktiv → VS Code MCP-Panel pruefen |
| Nur 100 Items zurueck | SharePoint-Paging → A7 verwenden |
| Suche liefert 0 Treffer | Query-Syntax pruefen, ggf. `site:`-Einschraenkung entfernen |
| SitePages-API liefert 404 | Nur auf Modern Sites verfuegbar, nicht auf Classic Sites |
