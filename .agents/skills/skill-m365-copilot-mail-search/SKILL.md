---
name: skill-m365-copilot-mail-search
description: "M365 Mail Search ueber Graph Search API ausfuehren. Durchsucht Outlook-Mails im Postfach des Users. Benoetigt den separaten Teams-/Mail-Resolver. Mail suchen, Outlook durchsuchen, finde Mail zu, habe ich eine Mail von, Mail-Suche, E-Mail finden, nach Mail suchen, Postfach durchsuchen."
---

# Skill: M365 Mail Search (Graph Search API)

Durchsucht **Outlook-Mails** ueber den Graph Search API Endpoint `/v1.0/search/query` mit `entityTypes: ["message"]`.
Das Script unterstuetzt zusaetzlich einen exklusiven Kalender-Modus per `--events`, der nur `entityTypes: ["event"]` abfragt und die Ausgabe auf das Mail-Schema mappt (`receivedDateTime`, `from`, `replyTo`, `subject`, `attachments`, `bodyPreview`, `webLink`).

> **Wichtig:** Der Endpoint benoetigt fuer Mail-Suche **Mail.Read**, fuer Kalender-Suche **Calendars.Read**. Der Copilot-Token (NAA) hat diese Scopes typischerweise **nicht**. Es wird zwingend ein **Teams-Web-Token** benoetigt.

## Wann verwenden?

- Der User moechte **Mails im Outlook-Postfach** finden
- Der User fragt: "Habe ich eine Mail von X?", "Finde Mails zum Thema Y", "Durchsuche mein Postfach nach Z"
- Der User moechte **Mails ueber die Graph API** suchen (nicht ueber Outlook COM)

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| Dokumente in SharePoint/OneDrive suchen | `$skill-m365-copilot-file-search` |
| Mail-Thread per Entry-ID nachladen | `$skill-outlook` |
| Verwandte Mails per Outlook COM suchen | `$skill-outlook` |
| Confluence/Jira durchsuchen | `local_rag` oder `mcp-atlassian` |

### Abgrenzung zu Outlook COM Skills

| Kriterium | Mail Search (dieser Skill) | Outlook COM Skills |
|-----------|---------------------------|-------------------|
| **Zugang** | Graph API + separater Mail-Resolver | Outlook COM (lokal) |
| **Voraussetzung** | Playwright MCP + Teams-Session | Outlook muss laufen |
| **Suchbereich** | Serverseitig, alle Ordner | Lokaler Outlook-Cache |
| **Geschwindigkeit** | Schnell (API-Call) | Abhaengig von Cache-Groesse |
| **Ergebnis** | Subject, Sender, Datum, Preview | Vollstaendiger Body, alle Empfaenger |
| **Typischer Einsatz** | Schnelle Suche, Ueberblick | Detaillierte Analyse, Thread-Sicht |

**Empfehlung:** Fuer schnelle Suchen und Ueberblick diesen Skill verwenden. Fuer detaillierte Mail-Analyse (vollstaendiger Body, alle To/Cc) anschliessend `$skill-outlook` nutzen.

## Voraussetzungen

1. **Playwright MCP Server** muss aktiv sein (fuer Token-Beschaffung)
2. **Teams-Web-Session** muss im Browser aktiv sein (SSO ueber Browser Extension)
3. Token muss **Mail.Read** Scope haben (bereitgestellt ueber `m365_mail_search_token.py`)

### Pruefen ob MCP verfuegbar

```
tool_search_tool_regex(pattern="mcp_playwright")
```

Falls keine Ergebnisse → Skill nicht nutzbar (Plan-Modus oder MCP nicht gestartet).

---

## Workflow

> **Script:** `scripts/m365_mail_search.py` im Skill-Ordner — Token-Pruefung, Mail-Suche und Formatierung.

### Schritt 1: Mail-Suche ausfuehren

```bash
# via run_in_terminal
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "SUCHBEGRIFF"

# Optional: Outlook-Kalender statt Mails durchsuchen
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "SUCHBEGRIFF" --events

# Optional: mehr Ergebnisse (max 25)
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "SUCHBEGRIFF" --size 25

# Optional: reine Datums-Sortierung statt Default-Hybridranking
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "SUCHBEGRIFF" --date-order

# Optional: nur Search-Snippets ausgeben, ohne Mail-Bodies nachzuladen
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "SUCHBEGRIFF" --only-summary
```

- **Default-Verhalten:** Die Search API liefert fuer `message` mit `enableTopResults=true` eine hybride Ergebnisliste:
  die ersten **3 Nachrichten nach Relevanz**, der Rest nach **Date/Time**.
- `--date-order` deaktiviert dieses Hybridranking und nutzt fuer alle Treffer die normale Datumssortierung des Endpoints.
- Standardmaessig laedt das Script fuer jeden Treffer die Mail nach und zeigt `bodyPreview` als erste **10** nichtleere Body-Zeilen.
- `--only-summary` zeigt statt `bodyPreview` nur `summary` aus dem Search-Response und spart die zusaetzlichen Mail-Nachlade-Calls.
- `--events` schaltet in einen **exklusiven** Kalender-Modus. In diesem Lauf werden keine Mails gesucht; der Agent muss fuer Mail + Kalender zwei getrennte Script-Aufrufe machen.
- Im Event-Modus werden Organizer und Teilnehmer per Event-Detail-GET nachgeladen; `replyTo` zeigt die Teilnehmerliste und kuerzt ab mehr als 10 Personen mit `[...] (N)` ab.
- Im Event-Modus entfallen `end` und `summary`; stattdessen werden `bodyPreview` und `attachments` analog zur Mail-Suche ausgegeben.
- Das Script versucht den Mail-Token jetzt **selbststaendig** zu beschaffen:
  - vorhandenen Cache nutzen
  - Teams-LocalStorage scannen
  - falls moeglich per Refresh-Token neuen Access-Token holen
  - falls noetig Teams in Edge oeffnen und auf aktualisierte MSAL-Eintraege warten
- **Exit 0** → Die Suchtreffer werden auf STDOUT ausgegeben; zusaetzlich wird eine Markdown-Datei unter `tmp/` erzeugt.
- **Exit 2** → `TOKEN_EXPIRED` oder `NO_MAIL_SCOPE` auf stderr. Dann ist auch der Python-Resolver gescheitert. Nur dann manuell weiter zu Schritt 2.
- **Exit 1** → sonstiger Fehler (Meldung auf stderr).

### Schritt 2: Mail-Token holen (nur bei Exit 2)

Der separate Resolver `m365_mail_search_token.py` ist die **einzige** Token-Quelle fuer Mail-Suche. Dieser Schritt ist jetzt nur noch der **Fallback**, wenn `m365_mail_search.py` im Skill-Ordner ihn nicht selbst aufloesen konnte.

**2a.** Teams Web oeffnen:

```
mcp_playwright_browser_navigate(url="https://teams.microsoft.com/v2/")
```

**2b.** Token aus Teams `localStorage` extrahieren und in Cache-Datei speichern:

> Normalfall: nicht noetig. Das Python-Script verwendet dafuer jetzt `.agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py`.
> Nur wenn der Resolver mit `TOKEN_EXPIRED` endet, kann der Agent diesen manuellen Fallback noch nutzen.

```
mcp_playwright_browser_evaluate(
  function: <JS-FUNKTION UNTEN>,
  filename: "userdata/tmp/.graph_token_cache_teams.json"
)
```

JS-Funktion (als `function`-Parameter uebergeben):

```javascript
async () => {
  const msalTokenKeysRaw = localStorage.getItem('msal.token.keys.5e3ce6c0-2b1f-4285-8d4b-75ee78787346');
  if (!msalTokenKeysRaw) return JSON.stringify({ error: 'No MSAL token keys' });
  const keys = JSON.parse(msalTokenKeysRaw);
  for (const atKey of (keys.accessToken || [])) {
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

**2c.** Mail-Suche erneut ausfuehren:

```bash
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "SUCHBEGRIFF"
```

**Fehlerbehandlung:**
- `No MSAL token keys` → Teams-Session nicht aktiv, User muss sich in Teams anmelden
- `No Graph token found` → Seite neu laden und erneut versuchen
- `NO_MAIL_SCOPE` → Token hat keinen Mail.Read Scope. Mail-Suche funktioniert nur ueber den separaten Mail-Resolver, nicht ueber den Copilot-Token (NAA).

### Schritt 3: Einzelne Mail vollstaendig lesen

Die Search API liefert im Suchmodus mehrere Metadaten und Such-Snippets. Standardmaessig laedt das Script fuer
jeden Treffer zusaetzlich die eigentliche Mail per `hitId` nach und schreibt die ersten **10** nichtleeren
Body-Zeilen als `bodyPreview` in STDOUT und in die Ergebnisdatei unter `tmp/`.
Mit `--only-summary` wird stattdessen nur `summary` aus dem Search-Response ausgegeben. Fuer den kompletten Body:

```bash
# MESSAGE_ID ist die hitId aus dem Suchergebnis
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID"

# Mit Anhang-Download nach userdata/tmp/
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID" --save-attachments

# Anhaenge direkt als Text extrahieren (PDF, DOCX, XLSX, PPTX)
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID" --convert

# Ganzen Mail-Thread anzeigen (alle Mails der Unterhaltung)
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID" --include-thread

# Kombinierbar: Mail lesen + Anhaenge konvertieren + Thread anzeigen
python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID" --convert --include-thread
```

Ausgabe: Subject, Von, Datum, An, Cc, Prioritaet, Anhang-Liste und vollstaendiger Body (HTML wird automatisch in Text konvertiert).
- `--save-attachments` speichert Anhaenge als Dateien nach `userdata/tmp/`.
- `--convert` extrahiert den Textinhalt unterstuetzter Anhaenge (PDF, DOCX, XLSX, PPTX) und haengt ihn seitenweise als Markdown an die Ausgabe an. Nutzt intern `scripts/file_parsers.py`.
- `--include-thread` liest die `conversationId` aus der Mail und laedt alle Nachrichten der Unterhaltung per `GET /v1.0/me/messages?$filter=conversationId eq '...'`. Gibt eine chronologische Tabelle aller Thread-Nachrichten aus, die aktuelle Mail mit **◀** markiert.

### Schritt 3b: Anhaenge manuell konvertieren (falls --convert nicht genuegt)

Falls die automatische `--convert`-Extraktion nicht ausreicht (z.B. fuer Bilder oder Sonderformate),
koennen gespeicherte Anhaenge manuell konvertiert werden:

```python
# PDF → Text
import pdfplumber
with pdfplumber.open("userdata/tmp/datei.pdf") as pdf:
    text = "\n".join(p.extract_text() or "" for p in pdf.pages)

# DOCX → Text
from docx import Document
doc = Document("userdata/tmp/datei.docx")
text = "\n".join(p.text for p in doc.paragraphs)

# XLSX → CSV
from openpyxl import load_workbook
wb = load_workbook("userdata/tmp/datei.xlsx")
for ws in wb.worksheets:
    for row in ws.iter_rows(values_only=True):
        print(";".join(str(c or "") for c in row))

# PPTX → Text
from pptx import Presentation
prs = Presentation("userdata/tmp/datei.pptx")
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            print(shape.text)
```

> **Tipp:** Fuer SharePoint-/OneDrive-Dateien direkt `scripts/m365_file_reader.py read URL` verwenden — das macht Download + Konvertierung in einem Schritt.

### Schritt 4: Ergebnisse praesentieren

Das Script gibt die Suchtreffer auf STDOUT als kompakte Markdown-Bloecke aus mit:
`subject`, `receivedDateTime`, `replyTo`, `from` und bei Vorhandensein `cc` sowie genau einem Vorschaufeld:
- standardmaessig `bodyPreview` (erste 10 Mail-Zeilen)
- mit `--only-summary` nur `summary`
- wenn verlinkbare Anhaenge vorhanden sind, zusaetzlich `attachments:` mit den reinen Namen
- `importance` nur dann, wenn der Wert ungleich `normal` ist

Mailadressen im `bodyPreview` werden dabei entfernt, sodass z. B. `Max Mustermann <max@firma.de>` nur als `Max Mustermann` erscheint.
Sobald eine Vorschauzeile mit `Von:` oder `-----Ursprünglicher Termin` beginnt, endet das `bodyPreview` vor dieser Zeile, damit keine weitergeleitete oder vorherige Mail in die Treffer-Vorschau hineinlaeuft.

Zusaetzlich legt das Script eine Markdown-Datei in `tmp/` ab. Diese Datei enthaelt dieselben Treffer inklusive
`webLink` sowie einer `attachments:`-Linkliste fuer verlinkbare Datei-, Inline- und Referenz-Anhaenge
(inkl. OneDrive-/SharePoint-Referenzen), damit spaeter bei Bedarf gezielt geladen werden kann.

Falls Outlook Cloud-Dateien nur im HTML-Body verlinkt und nicht sauber als `referenceAttachment` geliefert werden, versucht das Script zusaetzlich SharePoint-/OneDrive-Links aus den HTML-Links der Mail als Attachment-Eintraege zu erkennen.

Personenfelder wie `from` und `replyTo` werden nur als Anzeigename gespeichert, ohne Mailadresse.
Rauschworte wie `INTERNAL` werden aus `summary` und `bodyPreview` entfernt.

### Script-Befehle (Referenz)

| Befehl | Zweck |
|--------|-------|
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "query"` | Mail-Suche (10 Treffer, Default: erste 3 nach Relevanz, Rest nach Date/Time) |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "query" --size 25` | Mail-Suche (max 25 Treffer) |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "query" --date-order` | Mail-Suche nur nach Datum statt Hybridranking |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "query" --only-summary` | Nur `summary` ausgeben, keine Mail-Bodies pro Treffer nachladen |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "query" --token TOKEN` | Suche mit explizitem Token |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py fetch` | Mail-Token mit Mail.Read aktiv beschaffen |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py check-token` | Cache-Status des dedizierten Mail-Token-Resolvers pruefen |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID"` | Vollstaendige Mail laden (Body, To, Cc) |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID" --save-attachments` | Mail laden + Anhaenge nach userdata/tmp/ speichern |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID" --convert` | Mail laden + Anhaenge als Text extrahieren (PDF, DOCX, XLSX, PPTX) |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read "MESSAGE_ID" --include-thread` | Mail laden + alle Thread-Nachrichten chronologisch auflisten |
| `python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py check-token` | Prueft ob Token mit Mail.Read vorhanden |

---

## API-Details

| Parameter | Wert |
|-----------|------|
| **Endpoint** | `POST https://graph.microsoft.com/v1.0/search/query` |
| **Auth** | Bearer Token mit **Mail.Read** fuer `message`, **Calendars.Read** fuer `event` |
| **App-ID** | `5e3ce6c0-2b1f-4285-8d4b-75ee78787346` (Teams Web Client) |
| **Request-Body** | `{"requests": [{"entityTypes": ["message"], "query": {"queryString": "..."}, "from": 0, "size": 10}]}` |
| **Response** | `{"value": [{"hitsContainers": [{"total": N, "hits": [...]}]}]}` |
| **Max Treffer** | 25 pro Anfrage |
| **Token-Laufzeit** | ca. 1 Stunde |

Bei `entityTypes=["message"]` und `enableTopResults=true` liefert der Endpoint keine vollstaendige Relevanzsortierung ueber alle Treffer, sondern eine hybride Liste:
die ersten **3 Nachrichten nach Relevanz**, die restlichen Treffer nach **Date/Time**.

### Warum `/v1.0/search/query` statt `/beta/copilot/microsoft.graph.search`?

Der Copilot-Endpoint kann **keine Mails suchen**. Er akzeptiert `entityTypes: ["message"]` zwar ohne Fehler, ignoriert den Parameter aber komplett und liefert nur SharePoint/OneDrive-Dateien (`resourceType: "listItem"`).

Fuer Mail-Suche ist zwingend `/v1.0/search/query` mit `entityTypes: ["message"]` noetig, was wiederum den `Mail.Read` Scope erfordert.

### KQL-Suchsyntax

Der `queryString` unterstuetzt **KQL (Keyword Query Language)**:

| Beispiel | Beschreibung |
|----------|-------------|
| `"Mehrarbeit"` | Einfache Keyword-Suche |
| `from:max.mustermann` | Mails von bestimmtem Absender |
| `subject:"Projektbericht"` | Suche im Betreff |
| `received>=2026-01-01` | Mails ab Datum |
| `hasAttachment:true` | Nur Mails mit Anhaengen |
| `from:mueller AND subject:budget` | Kombinierte Suche |
| `"Bordnetz Spezifikation" AND received>=2026-03-01` | Thema + Zeitraum |

## Haeufige Fehler

| Fehler | Ursache | Loesung |
|--------|---------|---------|
| `NO_MAIL_SCOPE` | Token hat keinen Mail.Read Scope | Mail-Token holen (Schritt 2) |
| `TOKEN_EXPIRED` | Kein gueltiger Token im Cache | Mail-Token holen (Schritt 2) |
| `401 Unauthorized` | Token serverseitig abgelaufen | Mail-Token neu holen |
| `403 Forbidden` | Token ohne Mail.Read oder Endpoint blockiert | Erst `$skill-m365-graph-scope-probe` zur Scope-Diagnose verwenden, danach Mail-Token neu holen |
| `No MSAL token keys` | Teams-Session nicht aktiv | User muss sich in Teams Web anmelden |

## Beispiel-Suchanfragen

```
"Mehrarbeit Mai"
"Projektbericht Bordnetz"
from:britta.ulrich subject:abwesenheit
hasAttachment:true received>=2026-03-01
"Budget EKEK" AND from:controller
subject:"Freigabe" AND received>=2026-01-01
```
