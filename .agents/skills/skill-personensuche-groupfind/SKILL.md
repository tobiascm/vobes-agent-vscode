---
name: skill-personensuche-groupfind
description: "Personen, Vorgesetzte, Chefs, Organisationsstrukturen und UserIDs ueber die GroupFind GraphQL-API finden. ERSTER Skill fuer alle Personensuchen und Hierarchie-Fragen. Trigger: Person suchen, Chef finden, Vorgesetzter, Kollegen, Peers, Hierarchie, OE-Struktur, Organigramm, userId, wer ist, wer leitet, Telefonnummer, Mail-Adresse, Mitarbeiter einer OE, wer arbeitet in, Kontaktdaten."
---

# Skill: Personensuche & Org-Hierarchie (GroupFind)

Dieser Skill nutzt die **GroupFind GraphQL-API** um Personen, Vorgesetzte, Organisationsstrukturen und UserIDs zu finden. Die API wird per **Playwright MCP** im Browser-Kontext aufgerufen (`fetch()` innerhalb von `evaluate`), da die Authentifizierung ueber Keycloak/CloudIDP laeuft und nur im Browser verfuegbar ist.

**Dieser Skill ist die erste Wahl fuer alle Personen- und Chef-Fragen.**

## Wann verwenden?

- Person suchen (Name, Vorname, Nachname)
- **Chef / Vorgesetzten** einer Person finden
- **Kollegen / Peers** einer Person auflisten
- **Org-Hierarchie / Organigramm** einer OE anzeigen
- **Mitarbeiter einer OE** auflisten (z.B. "Wer arbeitet in EKEK/1?")
- **userId** (VW-Kuerzel) einer Person finden
- **Kontaktdaten** finden: Telefonnummer, E-Mail, Raum, Adresse
- **Abteilung / Kostenstelle** einer Person ermitteln
- Allgemeine Suche im Konzern (Wiki, News, Apps, Personen)

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| OE-Mail fuer Budget-Zuordnung (welche Mail gehoert zu OE?) | `$skill-budget-ua-leiter` |
| Budget, Beauftragungen, Abrufe, Vorgaenge | `$skill-budget-bplus-export` |
| EA-Stammdaten, EA-Nummern, Laufzeiten | `$skill-budget-ea-uebersicht` |
| Confluence / Jira lesen oder schreiben | `mcp-atlassian` |
| Eigenleistung / EL-Planung | `$skill-budget-eigenleistung-el` |

## Abgrenzung zu skill-budget-ua-leiter

| | **skill-personensuche-groupfind** | **skill-budget-ua-leiter** |
|---|---|---|
| **Datenquelle** | GroupFind (Konzern-Personenverzeichnis) | BPLUS-NG OrgUnit-API |
| **Liefert** | Name, OE, Hierarchie, Telefon, Mail, Raum, Adresse, userId, Kollegen | OE → Mail-Adresse (der Leitung) |
| **Chef finden** | Ja (per `contactRelations` → `tree`) | Nur OE-Mail, kein Name/Hierarchie |
| **Einsatz** | **Primaer** fuer Personensuche und Chefs | Nur fuer Budget-spezifische OE→Mail-Zuordnung |

## Voraussetzungen

1. **Playwright MCP Server** muss aktiv sein
2. **Browser Extension** muss verbunden sein (Chrome Extension: Playwright MCP Bridge)
3. User muss im **VW-Netzwerk** authentifiziert sein (Keycloak-Session im Browser)

## API-Referenz

**Endpunkt:** `POST https://groupfind.volkswagenag.com/groupfind-api/graphql/v4`

**Auth:** Browser-Session (Keycloak/CloudIDP). Kein `curl`/PowerShell moeglich (kein Kerberos). Nur per `mcp_playwright_browser_evaluate` mit `fetch()`.

### Query 1: `contacts` — Personensuche (Hauptanwendung)

```graphql
contacts(term: String!, offset: Int, limit: Int, brand: [String], profile: String) → [Contact]
```

**Wichtige Felder von Contact:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `userId` | String | VW-Kuerzel (z.B. `VWRR6B4`) |
| `givenName` | String | Vorname |
| `familyName` | String | Nachname |
| `departmentName` | String | Abteilung (z.B. `EKEK`) |
| `subDepartmentName` | String | Unterabteilung (z.B. `EKEK/1`) |
| `departmentDescription` | String | Abteilungsbeschreibung |
| `subDepartmentDescription` | String | UA-Beschreibung |
| `emailAddresses` | [String] | E-Mail-Adressen |
| `jobTitle` | String | Stellenbezeichnung |
| `organizationName` | String | Firma (z.B. `Volkswagen AG`) |
| `costCenter` | String | Kostenstelle |
| `roomNumber` | String | Raumnummer / Standort |
| `phoneNumber` | PhoneNumber | `{ office, mobile, bik, fax }` (jeweils Listen) |
| `postalAddress` | PostalAddress | `{ street, city, postalCode, country }` |
| `external` | Boolean | Externer Mitarbeiter? |
| `internal` | Boolean | Interner Mitarbeiter? |

### Query 2: `contact` — Einzelperson per userId

```graphql
contact(userId: String!, profile: String) → Contact
```

Gleiche Felder wie `contacts`. Direkter Zugriff per VW-Kuerzel.

### Query 3: `contactRelations` — Org-Hierarchie / Chef finden

```graphql
contactRelations(userId: String!) → ContactRelations
```

**WICHTIG:** Nur das Feld `tree` verwenden! Das Feld `structure` liefert immer `null`.

**Rueckgabe-Struktur `tree`:** Liste von `ContactNode`:

```
ContactNode {
  focus: Boolean      # true = angefragte Person (oder FK-Ebene)
  contact: Contact    # Personen-Daten
  children: [ContactNode]  # Unterstellte / Peers
}
```

#### Chef-Ermittlungs-Algorithmus

```
contactRelations(userId: "XXX") → tree

Fall 1: tree[0].focus == false
  → tree[0].contact = CHEF der angefragten Person
  → tree[0].children = alle Peers (inkl. angefragte Person mit focus=true)

Fall 2: tree[0].focus == true
  → Die angefragte Person IST SELBST Fuehrungskraft
  → tree[0].contact = die Person selbst
  → tree[0].children = ihre direkten Mitarbeiter
```

**Peers** einer Person: `tree[0].children` (alle Eintraege mit `focus == false`)

### Query 4: `search` — Universalsuche

```graphql
search(term: String!, limit: Int, offset: Int, category: String, filter: [String], sort: String, brand: [String], language: String) → SearchResult
```

Durchsucht alle Quellen: Wiki, News, Apps, Jobs, Bilder, Org.Manager, iProject.

**Kategorien:** `*` (alle), `people`, `wiki`, `news`, `jobs`, `images`, `app`, `rules`

**Rueckgabe:**
```
SearchResult {
  meta { total, categories { name, count } }
  results [{ title, text, sourceName, type, source { internet, vwIntranet } }]
}
```

### Query 5: `autocomplete` — Suchvorschlaege

```graphql
autocomplete(term: String!, limit: Int, language: String) → [Autocomplete]
```

**Rueckgabe:** `{ category, frequency, display }`

### Query 6: `departments` — OE-Suche (eingeschraenkt)

```graphql
departments(term: String!, limit: Int, offset: Int) → [Department]
```

**Hinweis:** Diese Query liefert aktuell oft `null`-Werte fuer die Detail-Felder. Fuer OE-Mitarbeiter besser `contacts(term: "OE-KUERZEL")` verwenden.

## Standard-Workflow

### Schritt 1: GroupFind **Suchergebnis-Seite** im externen Browser oeffnen

**PFLICHT:** Oeffne IMMER zuerst die **Suchergebnis-URL** im **externen Browser** des Users per `run_in_terminal` mit `Start-Process`. So sieht der User sofort Ergebnisse in seinem echten Browser, waehrend der Agent parallel per Playwright die API-Abfragen ausfuehrt.

**URL-Schema:** `https://groupfind.volkswagenag.com/search/general?q={suchbegriff}&cat=Contenttype_vw_groupfind_person`

- `{suchbegriff}` = der Suchbegriff des Users (URL-encoded, z.B. Leerzeichen → `%20`)
- `cat=Contenttype_vw_groupfind_person` fuer Personensuche, `cat=*` fuer allgemeine Suche

```
run_in_terminal(command='Start-Process "https://groupfind.volkswagenag.com/search/general?q=Melanie%20Sohnemann&cat=Contenttype_vw_groupfind_person"')
```

**WICHTIG:** Dieser Schritt oeffnet den Link im Standard-Browser des Users (Chrome, Edge, etc.) — NICHT ueber Playwright. Der User sieht sofort die GroupFind-Suchergebnisse.

### Schritt 2: Playwright-Session herstellen (fuer API-Zugriff)

Parallel zum externen Browser wird Playwright nur fuer die GraphQL-API-Aufrufe genutzt. Dafuer muss einmalig zu GroupFind navigiert werden:

```
tool_search_tool_regex(pattern="mcp_playwright")
mcp_playwright_browser_navigate(url="https://groupfind.volkswagenag.com/")
mcp_playwright_browser_wait_for(time=5)
```

### Schritt 3: GraphQL-Query per evaluate ausfuehren

Ab hier arbeitet der Agent per API weiter — die Playwright-Session ist hergestellt. Der User sieht parallel die Ergebnisse in seinem externen Browser.

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('/groupfind-api/graphql/v4', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: \`{ ... GraphQL-Query hier ... }\`
      })
    });
    return JSON.stringify(await resp.json());
  }`
})
```

**WICHTIG:** Nach dem initialen `navigate` + `wait_for` koennen beliebig viele `evaluate`-Aufrufe gemacht werden, ohne erneut zu navigieren. Die Browser-Session bleibt aktiv.

### Schritt 4: Ergebnis verarbeiten

Das Ergebnis ist ein JSON-String. Direkt parsen und dem User als Tabelle oder strukturiert praesentieren.

**PFLICHT — Direktlinks immer mit ausgeben:**

Bei jeder Personensuche MUESSEN folgende Links mit ausgegeben werden:

| Link | URL-Schema | Beschreibung |
|------|-----------|--------------|
| **GroupFind-Profil** | `https://groupfind.volkswagenag.com/search/person/{userId}` | Oeffnet das Personenprofil in GroupFind |
| **GroupFind-Suche** | `https://groupfind.volkswagenag.com/search/general?q={suchbegriff}&cat=*` | Oeffnet die Suchergebnisseite |
| **Teams-Chat** | `https://teams.microsoft.com/l/chat/0/0?users={email}` | Oeffnet eine Teams-Konversation mit der Person |

**Beispiel-Ausgabe fuer eine Person:**

```
| Name | OE | Mail | Telefon |
|------|-----|------|---------|
| Dr. Max Mustermann | EKEK/1 | max.mustermann@volkswagen.de | +49-5361-9-12345 |

→ [GroupFind-Profil](https://groupfind.volkswagenag.com/search/person/VWAB123)
→ [Teams-Chat](https://teams.microsoft.com/l/chat/0/0?users=max.mustermann@volkswagen.de)
```

**Hinweis:** Der `{userId}` fuer die GroupFind-URL kommt direkt aus dem `userId`-Feld der API-Antwort. Die `{email}` fuer den Teams-Link kommt aus `emailAddresses[0]`. Den Suchbegriff fuer die Suche-URL mit `encodeURIComponent()` kodieren.

## Beispiele

### Beispiel 1: Person suchen (Name)

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('/groupfind-api/graphql/v4', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: \`{
          contacts(term: "Andreas Krause", limit: 5) {
            userId givenName familyName
            departmentName subDepartmentName
            emailAddresses
            phoneNumber { office mobile }
          }
        }\`
      })
    });
    return JSON.stringify(await resp.json());
  }`
})
```

### Beispiel 2: Einzelperson per userId

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('/groupfind-api/graphql/v4', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: \`{
          contact(userId: "VWRR6B4") {
            givenName familyName
            departmentName subDepartmentName subDepartmentDescription
            emailAddresses jobTitle organizationName
            phoneNumber { office mobile }
            roomNumber costCenter
          }
        }\`
      })
    });
    return JSON.stringify(await resp.json());
  }`
})
```

### Beispiel 3: Chef / Vorgesetzten finden

**Schritt A:** Zuerst die userId der Person ermitteln (falls nicht bekannt):

```
contacts(term: "Armin Bachmann", limit: 1) { userId givenName familyName }
```

**Schritt B:** Dann die Hierarchie abrufen:

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('/groupfind-api/graphql/v4', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: \`{
          contactRelations(userId: "EBACHAR") {
            tree {
              focus
              contact { userId givenName familyName departmentName subDepartmentName }
              children {
                focus
                contact { userId givenName familyName departmentName subDepartmentName }
              }
            }
          }
        }\`
      })
    });
    return JSON.stringify(await resp.json());
  }`
})
```

**Auswertung:**
- `tree[0].focus == false` → `tree[0].contact` = Chef
- Angefragte Person hat `focus: true` in `tree[0].children`

### Beispiel 4: Alle Mitarbeiter einer OE

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('/groupfind-api/graphql/v4', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: \`{
          contacts(term: "EKEK/1", limit: 50) {
            userId givenName familyName
            subDepartmentName jobTitle
            emailAddresses
          }
        }\`
      })
    });
    return JSON.stringify(await resp.json());
  }`
})
```

**Hinweis:** Bei grossen OEs `limit` erhoehen und ggf. `offset` fuer Paginierung nutzen.

### Beispiel 5: Universalsuche (Wiki, News, etc.)

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('/groupfind-api/graphql/v4', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: \`{
          search(term: "VOBES 2025", limit: 10, category: "wiki") {
            meta { total categories { name count } }
            results {
              title text sourceName
              source { internet vwIntranet }
            }
          }
        }\`
      })
    });
    return JSON.stringify(await resp.json());
  }`
})
```

### Beispiel 6: Zwei Schritte kombiniert — Person suchen + Chef ermitteln

Wenn der User fragt "Wer ist der Chef von Donato Sciaraffia?":

**Schritt A:** Externen Browser oeffnen damit der User sofort das Ergebnis sieht:

```
run_in_terminal(command='Start-Process "https://groupfind.volkswagenag.com/search/general?q=Donato%20Sciaraffia&cat=Contenttype_vw_groupfind_person"')
```

**Schritt B:** Playwright-Session fuer API herstellen + `contacts` + `contactRelations` kombiniert:

```
mcp_playwright_browser_navigate(url="https://groupfind.volkswagenag.com/")
mcp_playwright_browser_wait_for(time=5)
```

1. `contacts(term: "Donato Sciaraffia", limit: 1)` → `userId: "ESCIARA"`
2. `contactRelations(userId: "ESCIARA")` → `tree[0].contact` (Chef, da `focus == false`)

Beide Queries koennen in einem einzigen `evaluate`-Aufruf kombiniert werden:

```
mcp_playwright_browser_evaluate({
  function: `async () => {
    const gql = async (query) => {
      const r = await fetch('/groupfind-api/graphql/v4', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });
      return r.json();
    };

    // Schritt 1: userId finden
    const search = await gql(\`{
      contacts(term: "Donato Sciaraffia", limit: 1) { userId givenName familyName }
    }\`);
    const userId = search.data.contacts[0]?.userId;
    if (!userId) return JSON.stringify({ error: "Person nicht gefunden" });

    // Schritt 2: Hierarchie abrufen
    const rel = await gql(\`{
      contactRelations(userId: "\${userId}") {
        tree {
          focus
          contact { userId givenName familyName departmentName subDepartmentName emailAddresses }
          children {
            focus
            contact { userId givenName familyName }
          }
        }
      }
    }\`);

    return JSON.stringify({ search: search.data, relations: rel.data });
  }`
})
```

## Paginierung

Fuer grosse Ergebnismengen `offset` und `limit` kombinieren:

```graphql
contacts(term: "EKEK", limit: 20, offset: 0)   # Seite 1: Ergebnis 0-19
contacts(term: "EKEK", limit: 20, offset: 20)  # Seite 2: Ergebnis 20-39
```

## Troubleshooting

| Problem | Loesung |
|---------|---------|
| `mcp_playwright_*` Tools nicht verfuegbar | Playwright MCP Server nicht aktiv → VS Code MCP-Panel pruefen |
| Seite zeigt Keycloak-Login statt GroupFind | Browser-Session abgelaufen → User bitten, sich manuell im Browser bei GroupFind einzuloggen |
| `fetch()` liefert 401/403 | Session abgelaufen → erneut `navigate` + `wait_for` ausfuehren |
| `contacts` liefert leere Liste | Suchbegriff pruefen — Vor- und Nachname getrennt oder OE-Kuerzel exakt |
| `contactRelations` → `structure` ist `null` | Normal — immer `tree`-Feld verwenden, `structure` ist serverseitig deaktiviert |
| `departments` liefert `null`-Felder | Bekannte Einschraenkung — fuer OE-Mitarbeiter stattdessen `contacts(term: "OE-KUERZEL")` verwenden |
| Zu viele Ergebnisse | `limit` reduzieren oder Suchbegriff praezisieren |
| Ergebnis abgeschnitten | `limit` erhoehen und/oder `offset` fuer Paginierung nutzen |
| Falsche Person gefunden (gleicher Name) | `departmentName` / `subDepartmentName` zur Disambiguierung pruefen |
