---
name: skill-te-regelwerk
description: Prozessstandards, Arbeitsanweisungen und Regelwerke im TE Regelwerk (iProject) suchen, herunterladen und auslesen. Nutze diesen Skill bei Fragen zu Prozessstandards (PS), Arbeitsanweisungen (AA), Gremienregelungen (GreRo) oder Managementsystem-Dokumenten (MS) der Technischen Entwicklung.
---

# Skill: TE Regelwerk durchsuchen, Dokumente laden und lesen

Dieser Skill beschreibt den vollstaendigen Workflow, um Regelwerke im **TE Regelwerk** (iProject) per Playwright zu finden, herunterzuladen und den PDF-Inhalt auszulesen.
Achtung: Suche und Auslesen ist sehr langsam! Die meisten Bordnetz und VOBES-Prozesse sind bereits im VOBES-RAG enthalten. Skill `$skill-knowledge-bordnetz-vobes` immer zuerst laden und RAG-Ergebnis prueren, bevor dieser Skill genutzt wird.

## Wann verwenden?

- Der User fragt nach einem Prozessstandard (PS), einer Arbeitsanweisung (AA), einer Gremienregelung (GreRo) oder einem MS-Dokument
- Der User moechte ein Regelwerk aus dem TE Regelwerk herunterladen oder lesen
- Der User nennt eine Regelungsnummer (z. B. `PS_2.1_011_1462_09`, `AA_2.1_1462_34`)
- Der User fragt nach Prozessen der Technischen Entwicklung bei Volkswagen
- Der User moechte eine Liste aller Regelungen exportieren

## Voraussetzungen

- **MCP Playwright** muss konfiguriert und aktiv sein
- **PyMuPDF** (`fitz`) muss in der Python-Umgebung installiert sein (`pip install pymupdf`)
- Der User muss im VW-Netzwerk authentifiziert sein (SSO/iProject-Login)

## URLs und Architektur

### Hauptseite (Angular-App)

```
https://iproject.wob.vw.vwg/ecm/te2023/P41444D394449463650333249574F593
```

Die Hauptseite laedt ein **iframe** mit der Document-Library-App:

```
https://iproject.wob.vw.vwg/ecm/document-library/70AB3C1AB2FBF67BC8192293CFBF67BC
```

### API-Basis

```
https://iproject.wob.vw.vwg/ecm/document-library/api/
```

Technische Details:
- **Technologie:** Angular-App mit Spring-Boot-Backend (Java/Pageable-API)
- **Library-ID:** `41` (TE Regelwerk)
- **Library-UUID:** `70AB3C1AB2FBF67BC8192293CFBF67BC`
- **Authentifizierung:** Kerberos/NTLM (VW-Netzwerk SSO) — die API-Aufrufe funktionieren nur im authentifizierten Browser-Kontext (Playwright `page.evaluate` mit `fetch()`). Direkter Zugriff per `Invoke-WebRequest`/`curl` mit `-UseDefaultCredentials` liefert `403`.

## Dokumenttypen im TE Regelwerk

| Kuerzel | Typ | Anzahl (Stand 03/2026) |
|---------|-----|----------------------|
| **AA** | Arbeitsanweisung | 1.889 |
| **PS** | Prozessstandard | 653 |
| **GH** | Geschaeftshandbuch / EHB-Anlage | 171 |
| **PA** | Prozessanlage | 138 |
| **RD** | Rollendefinition | 129 |
| **NU** | Nutzerinformation / Unterweisung | 128 |
| **IM** | Interne Mitteilung | 106 |
| **LF** | Leitfaden | 91 |
| **GO** | Geschaeftsordnung | 45 |
| **VL** | Vorlage | 41 |
| **GA** | Geschaeftsanweisung | 38 |
| **RdF** | Regelung des Fachbereichs | 20 |
| **CL** | Checkliste | 16 |
| **RL** | Richtlinie | 14 |

### Status-Werte

| statusId | Status | Anzahl (Stand 03/2026) |
|----------|--------|----------------------|
| 7 | Veroeffentlicht | 2.158 |
| 8 | ausser Kraft | 1.153 |
| 2 | in Erstellung | 86 |
| 1 | in Planung | 68 |
| 3 | in Abstimmung | 9 |
| 6 | zur Freigabe QMR | 1 |
| 4 | zur Freigabe QMB | 1 |
| 5 | Ungueltig | 3 |

---

## REST-API-Referenz

**Wichtig:** Alle API-Aufrufe muessen im authentifizierten Browser-Kontext ausgefuehrt werden. Verwende `mcp_playwright_browser_evaluate` mit `fetch()` innerhalb der iProject-Seite.

### 1. Alle Regelungen auflisten

```
GET /ecm/document-library/api/rule/library/{libraryId}
```

**Parameter:**
- `libraryId`: `41` (TE Regelwerk)

**Antwort:** JSON-Array mit allen Regelungen (Stand 03/2026: 3.479 Eintraege).

**Beispiel:**
```javascript
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('https://iproject.wob.vw.vwg/ecm/document-library/api/rule/library/41');
    const data = await resp.json();
    return JSON.stringify({ total: data.length });
  }`
})
```

**Antwortstruktur pro Eintrag:**
```json
{
  "content": {
    "ruleId": 7801,
    "ruleVersionId": 11949,
    "ruleNumber": "AA_2.1_1796_05",
    "title": "Entsorgung von Prototypen Spezialbetriebsmitteln im VSC durchführen",
    "ruleType": {
      "typeShortcut": "AA",
      "i18nValue": "Arbeitsanweisung",
      "ruleTypeId": 22
    },
    "status": {
      "statusId": 7,
      "i18nValue": "Veröffentlicht",
      "publicised": true
    },
    "validFrom": 1710284400000,
    "majorVersion": 1,
    "minorVersion": 0,
    "releaseDepartment": {
      "orgId": 480009,
      "name": "EV1",
      "title": "Product Unit I"
    },
    "contactDepartment": {
      "orgId": 480014,
      "name": "EV2/G"
    },
    "description": "<p>HTML-Beschreibung...</p>"
  },
  "identifier": "AA_2.1_1796_05",
  "contentType": 1,
  "validFrom": 1710284400000
}
```

**Wichtige Felder fuer Filterung:**
- `content.ruleId` — Eindeutige Regel-ID (fuer Detail-API und Download-URL)
- `content.ruleNumber` / `identifier` — Regelungsnummer (z.B. `PS_2.1_011_1462_09`)
- `content.ruleType.typeShortcut` — Dokumenttyp-Kuerzel (AA, PS, GH, ...)
- `content.status.statusId` — Status (`7` = Veroeffentlicht)
- `content.status.publicised` — `true` wenn oeffentlich

### 2. Regel-Details mit Dokumenten abrufen

```
GET /ecm/document-library/api/rule-version/getEditRule?ruleId={ruleId}&isSpecialDialogTransition=false
```

**Parameter:**
- `ruleId`: Die `content.ruleId` aus der Auflistung

**Beispiel:**
```javascript
mcp_playwright_browser_evaluate({
  function: `async () => {
    const resp = await fetch('https://iproject.wob.vw.vwg/ecm/document-library/api/rule-version/getEditRule?ruleId=7801&isSpecialDialogTransition=false');
    const data = await resp.json();
    return JSON.stringify({
      ruleNumber: data.ruleNumber,
      title: data.title,
      documents: data.attachment?.documents?.length,
      internalDocs: data.attachment?.internalDocuments?.length
    });
  }`
})
```

**Antwortstruktur (relevante Felder):**
```json
{
  "ruleId": 7801,
  "ruleNumber": "AA_2.1_1796_05",
  "title": "Entsorgung von Prototypen...",
  "ruleVersionId": 17579,
  "status": { "statusId": 7, "i18nValue": "Veröffentlicht" },
  "attachment": {
    "documents": [
      {
        "ruleVersionAttachmentId": 59680,
        "documentId": 21865,
        "documentVersionId": 42166,
        "fileName": "AA_2.1_1796_05 Entsorgung... (Vers.01.01).pdf",
        "title": "AA_2.1_1796_05 Entsorgung...",
        "displayOrder": 0,
        "attachmentGroup": {
          "attachmentGroupId": 1,
          "i18nValue": "Dokument"
        },
        "attachmentType": {
          "attachmentTypeId": 1,
          "i18nValue": "Dateianhang"
        }
      }
    ],
    "trainings": [],
    "references": [],
    "internalDocuments": []
  },
  "scope": {
    "vwAgFactoryKeys": [...],
    "vwFactoryKeys": [],
    "brandsFactoryKeys": []
  },
  "roles": [...]
}
```

**Wichtige Attachment-Felder:**
- `attachment.documents` — Oeffentliche Dokumente (PDFs, Anlagen)
- `attachment.internalDocuments` — Interne Dokumente (nur mit erweiterten Rechten)
- `attachment.trainings` — Schulungsmaterialien
- `attachment.references` — Verweise auf andere Regelungen
- Pro Dokument: `documentId`, `documentVersionId`, `fileName`, `title`

### 3. PDF-Dokument herunterladen

**Fuer veroeffentlichte Regelungen:**
```
GET /ecm/document-library/api/document/published/download/{ruleId}/{documentId}/{sanitizedTitle}
```

**Fuer nicht-veroeffentlichte Regelungen (Entwurf, in Planung etc.):**
```
GET /ecm/document-library/api/document/download/{ruleId}/{documentVersionId}/{sanitizedTitle}
```

**Parameter:**
- `ruleId`: Die `content.ruleId` der Regelung
- `documentId`: Die `documentId` aus dem Attachment
- `documentVersionId`: Die `documentVersionId` aus dem Attachment (fuer nicht-veroeffentlichte)
- `sanitizedTitle`: Beliebiger String (wird fuer den Dateinamen im Download-Header verwendet, aber der Server ignoriert ihn fuer die Dateisuche)

**Antwort:** Binaerer PDF-Stream mit `Content-Type: application/pdf`

**URL-Konstruktion im JavaScript der Angular-App:**
```javascript
// Originale URL-Konstruktionslogik aus dem Angular-Source:
function buildDownloadUrl(ruleId, isPublished, attachment) {
  const apiBase = 'https://iproject.wob.vw.vwg/ecm/document-library/api/document/';
  const isInternal = attachment.attachmentGroup.i18nKey.toLowerCase().includes('internal');
  const publishedPrefix = isPublished ? 'published/' : '';
  const internalPrefix = isInternal ? 'internal/' : '';
  const docId = isPublished ? attachment.documentId : attachment.documentVersionId;
  const safeName = attachment.title.replace(/\s|[^a-zA-Z 0-9]/g, '');
  return apiBase + publishedPrefix + internalPrefix + 'download/' + ruleId + '/' + docId + '/' + safeName;
}
```

**Download per Playwright (einzelne Datei):**
```javascript
mcp_playwright_browser_evaluate({
  function: `async () => {
    const url = 'https://iproject.wob.vw.vwg/ecm/document-library/api/document/published/download/7801/21865/test';
    const resp = await fetch(url);
    return JSON.stringify({
      status: resp.status,
      contentType: resp.headers.get('content-type'),
      size: resp.headers.get('content-length')
    });
  }`
})
```

### 4. Weitere API-Endpunkte

| Endpunkt | Methode | Beschreibung |
|----------|---------|-------------|
| `/api/library/toLibrary?libraryUUID={uuid}` | GET | Library-ID aus UUID ermitteln (gibt Int zurueck, z.B. `41`) |
| `/api/library/getLibrary?libraryId={id}` | GET | Library-Metadaten abrufen |
| `/api/rule/getLibraryRuleByRuleId?libraryId={libId}&ruleId={ruleId}` | GET | Regel-Kurzinfo (ohne Attachments!) |
| `/api/rule/references?ruleId={ruleId}` | GET | Verweise/Referenzen einer Regelung |
| `/api/role/library/{libraryId}` | GET | Alle Rollen der Library |
| `/api/role/{roleId}` | GET | Einzelne Rolle |
| `/api/workflow/getStatusTransitions` | GET | Moegl. Status-Uebergaenge |
| `/api/defaults` | GET | Standard-Konfiguration |
| `/api/options` | GET | Dropdown-Optionen |
| `/api/orgUnits` | GET | Organisationseinheiten |

---

## Workflow: Einzelne Regelung suchen (UI-basiert via Playwright)

### Schritt 1: TE Regelwerk oeffnen

```
mcp_playwright_browser_navigate(url="https://iproject.wob.vw.vwg/ecm/te2023/P41444D394449463650333249574F593")
```

Warte bis die Seite geladen ist (Titel: "TE Regelwerk"). Falls nur Ladebalken sichtbar:

```
mcp_playwright_browser_wait_for(time=5)
```

### Schritt 2: Nach Regelwerk suchen

1. Snapshot machen, um das Suchfeld im **iframe** zu finden
2. Auf das Suchfeld klicken (`textbox "Zu welchem Thema suchen Sie eine Regelung?"`)
3. Suchbegriff eingeben mit `submit=true`:

```
mcp_playwright_browser_type(ref=<suchfeld-ref>, text="<Suchbegriff>", submit=true)
```

**Wichtig:** Das Suchfeld befindet sich innerhalb eines `iframe`. Playwright adressiert es ueber `page.locator('iframe').contentFrame()`.

### Schritt 3: Suchergebnisse auswerten

Nach der Suche einen **Snapshot** machen. Die Ergebnisse zeigen:
- **Typ** (PS, AA, GreRo, MS, R)
- **Titel** des Regelwerks
- **Regelungsnummer**
- **Version**
- **Status** (Veroeffentlicht, Entwurf, etc.)
- **Gueltig-ab-Datum**
- **Anzahl Ergebnisse** (z. B. "2 Ergebnisse")

Die Ergebnisliste ist paginiert (Standard: 10 pro Seite). Bei Bedarf mit "Next page"-Button blaettern.

### Schritt 4: Regelwerk oeffnen

Auf den gewuenschten Eintrag klicken. Die Detail-Ansicht zeigt:
- Stammdaten (Version, Gueltig ab, KSU, Klassifikation)
- **Tab "Allgemein"**: Dokumente (Download-Links), Verweise, Freigebende Instanz
- **Tab "Geltungsbereich"**: Betroffene Werke und Organisationseinheiten
- **Tab "Rollen"**: Beteiligte Rollen
- **Tab "Training"**: Schulungsinformationen

### Schritt 5: Dokument herunterladen

Die Download-Links befinden sich unter **Dokumente** im Tab "Allgemein". Klick auf den Link loest einen Browser-Download aus:

```
mcp_playwright_browser_click(ref=<download-link-ref>, element="<Dokumenttitel>")
```

Die Datei landet im Windows-Downloads-Ordner (`%USERPROFILE%\Downloads`). Dateinamen-Muster pruefen:

```powershell
Get-ChildItem "$env:USERPROFILE\Downloads" -Filter "*<Regelungsnummer-Fragment>*" | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name, Length, LastWriteTime
```

### Schritt 6: Datei ins Workspace kopieren (optional)

```powershell
Copy-Item "$env:USERPROFILE\Downloads\<Dateiname>.pdf" "C:\Daten\Python\vobes_agent_vscode\<Zielname>.pdf"
```

### Schritt 7: PDF-Inhalt auslesen

```python
python -c "
import fitz
doc = fitz.open(r'<Pfad-zur-PDF>')
for i, page in enumerate(doc):
    text = page.get_text()
    if text.strip():
        print(f'=== Seite {i+1} ===')
        print(text)
print(f'\nGesamt: {len(doc)} Seiten')
"
```

---

## Haeufige Probleme und Loesungen

| Problem | Loesung |
|---------|---------|
| Snapshot zeigt Extension-Seite statt iProject | `mcp_playwright_browser_tabs(action="list")` → richtigen Tab auswaehlen oder neu navigieren |
| Seite zeigt nur Ladebalken | `mcp_playwright_browser_wait_for(time=8)` und erneut Snapshot machen |
| Download-Link oeffnet Login-Seite | User ist nicht authentifiziert → manuell im Browser einloggen |
| PDF-Text ist leer oder unleserlich | Dokument ist gescannt/Bild-PDF → OCR noetig (nicht im Skill abgedeckt) |
| Mehrere gleichnamige Downloads | Neueste Datei per `Sort-Object LastWriteTime -Descending` waehlen |
| API liefert 403 per PowerShell/curl | Nur im Browser-Kontext moeglich — `mcp_playwright_browser_evaluate` mit `fetch()` verwenden |
| `fetch()` liefert leere Antwort | iProject-Session abgelaufen → Seite neu laden (`mcp_playwright_browser_navigate`) |
| API-Aufruf liefert `0 Ergebnisse` | Seite ist noch nicht vollstaendig geladen → `wait_for(time=8)` vor dem API-Aufruf |

---

## Beispiel 1: Einzelne Regelung suchen (UI-Workflow)

**User fragt:** "Was steht im Prozessstandard fuer Systemschaltplaene?"

1. `mcp_playwright_browser_navigate` → TE Regelwerk oeffnen
2. `mcp_playwright_browser_snapshot` → Suchfeld-Ref ermitteln
3. `mcp_playwright_browser_click` → Suchfeld fokussieren
4. `mcp_playwright_browser_type(text="Systemschaltpläne", submit=true)` → Suche ausfuehren
5. `mcp_playwright_browser_snapshot` → Ergebnisse lesen ("2 Ergebnisse")
6. `mcp_playwright_browser_click` → Regelwerk "Systemschaltpläne erstellen und freigeben" oeffnen
7. `mcp_playwright_browser_snapshot` → Detail-Ansicht mit Download-Links
8. `mcp_playwright_browser_click` → PDF-Download ausloesen
9. Terminal: Download-Datei finden und ins Workspace kopieren
10. Terminal: `python` + `fitz` → PDF-Text extrahieren und zusammenfassen

## Beispiel 2: PDF einer bekannten Regelung direkt herunterladen (API)

```javascript
mcp_playwright_browser_evaluate({
  function: `async () => {
    // 1. Regelung per Nummer finden
    const resp = await fetch('https://iproject.wob.vw.vwg/ecm/document-library/api/rule/library/41');
    const all = await resp.json();
    const rule = all.find(r => r.content.ruleNumber === 'PS_2.1_011_1462_09');
    if (!rule) return 'Regelung nicht gefunden';
    
    // 2. Dokumente abrufen
    const detailResp = await fetch('https://iproject.wob.vw.vwg/ecm/document-library/api/rule-version/getEditRule?ruleId=' + rule.content.ruleId + '&isSpecialDialogTransition=false');
    const detail = await detailResp.json();
    const pdfs = (detail.attachment?.documents || []).filter(d => d.fileName?.endsWith('.pdf'));
    
    // 3. Download-URLs konstruieren
    const isPublished = detail.status?.statusId === 7;
    const urls = pdfs.map(doc => ({
      fileName: doc.fileName,
      url: 'https://iproject.wob.vw.vwg/ecm/document-library/api/document/' + (isPublished ? 'published/' : '') + 'download/' + rule.content.ruleId + '/' + (isPublished ? doc.documentId : doc.documentVersionId) + '/file'
    }));
    return JSON.stringify(urls, null, 2);
  }`
})
```
