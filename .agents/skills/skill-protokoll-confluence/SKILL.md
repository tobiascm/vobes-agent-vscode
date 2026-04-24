---
name: skill-protokoll-confluence
description: Protokollseiten fuer Regeltermine erstellen, ueberarbeiten und in Confluence speichern. Gilt fuer alle Termine mit Sammlerseite im Space VOBES oder EKEK1. Kann Transkripte aus OneDrive Recordings (Teams-Aufzeichnungen) und Audioaufzeichnungen (manuell aufgenommen) automatisch laden, wenn der User sagt "Bitte Protokoll erstellen", "Mache das Protokoll vom letzten Termin", "Protokoll vom Meeting XY erstellen" oder "Protokoll aus Recording bauen".
---

## Zweck

Dieser Skill steuert das Erstellen und Aktualisieren von Protokollseiten in Confluence.
Jede Protokollseite MUSS:
1. Als **Kindseite** unter der zugehoerigen Sammlerseite angelegt werden (`parent_id`).
2. Die **Namenskonvention** des jeweiligen Termins einhalten.
3. Im Space **VOBES** (oder **EKEK1** fuer KC Vibe Coding) liegen.

## Voraussetzungen

- Skill `$skill-orga-ekek1` muss bekannt sein (enthaelt die primaere Zuordnung fuer interne `EKEK/1`-/`VOBES`-Termine, Gremien und Seiten).
- Skill `$skill-important-pages-links-and-urls` muss bekannt sein (enthaelt allgemeine Standardlinks und Zusatzseiten).
- Skill `$skill-update-confluence-page` befolgen bei Updates bestehender Seiten.

## Sammlerseiten und Namenskonventionen

| Regeltermin | Sammlerseite (parent_id) | Namenskonvention | Beispiel |
|---|---|---|---|
| VOBES FB-IT-Abstimmung | `754406190` | `VOBES FB-IT-Abstimmung YYYY-MM-DD` | VOBES FB-IT-Abstimmung 2026-03-12 |
| PO-APO-Prio-Runde | `144309929` | `Protokoll PO-APO-Prio-Runde YYYY-MM-DD` | Protokoll PO-APO-Prio-Runde 2026-03-12 |
| Interne Fachthemen | `282753506` | `Protokoll Fachthemen-Runde YYYY-MM-DD` | Protokoll Fachthemen-Runde 2026-03-12 |
| Workshopreihe Sys-Designer | `212452410` | `WS YYYY-MM-DD` | WS 2026-03-12 |
| Workshopreihe Easy-Migration-Selfservice | `6698589657` | `Workshop Easy-Migration-Selfservice YYYY-MM-DD` | Workshop Easy-Migration-Selfservice 2026-03-12 |
| Planung 2026 | `5127115694` | *(keine datumsbasierten Protokolle — Sonderfall)* | — |
| KC Vibe Coding | `6932124640` | `KC Vibe Coding - YYYY-MM-DD` | KC Vibe Coding - 2026-03-12 |
| Übergreifendes techn. Refinement | `6612851628` | `YYYY-MM-DD Protokoll Übergr. techn. Refinement` | 2026-04-24 Protokoll Übergr. techn. Refinement |

> **Datum-Format:** Immer `YYYY-MM-DD` (ISO 8601). Das Datum im Titel ist das Termindatum, NICHT das Erstellungsdatum.
> **Datum-Position:** Bei den meisten Regelterminen steht das Datum am **Ende** des Titels. Ausnahme: "Übergreifendes techn. Refinement" hat das Datum am **Anfang** (Bestandskonvention).

## Ablauf: Neues Protokoll erstellen

### 1. Termin identifizieren
- Zuerst `$skill-orga-ekek1` konsultieren, um Terminname, Sammlerseite und internen Kontext fuer `EKEK/1`-/`VOBES`-Termine einzuordnen.
- Danach bei Bedarf `$skill-important-pages-links-and-urls` fuer allgemeine Standardlinks oder Zusatzseiten nachziehen.
- Frage den User, zu welchem Regeltermin das Protokoll gehoert, falls es nach diesem Abgleich noch nicht eindeutig ist.
- Schlage den naechsten passenden Termin vor (basierend auf aktuellem Datum).

### 2. Pruefen ob Protokollseite bereits existiert
- Tool: `mcp_mcp-atlassian_confluence_get_page_children`
- Parameter: `parent_id` der Sammlerseite, `limit=10`
- Pruefen ob eine Seite mit dem erwarteten Titel (Namenskonvention + Datum) bereits existiert.
- Falls ja: **Kein neues Protokoll erstellen**, sondern zum Update-Workflow wechseln (siehe unten).

### 3. Seitentitel zusammensetzen
- Namenskonvention aus der Tabelle oben verwenden.
- Das Termindatum im Format `YYYY-MM-DD` anfuegen.
- Beispiel: Termin "Interne Fachthemen" am 12.03.2026 → `Protokoll Fachthemen-Runde 2026-03-12`

### 4. Inhalt vorbereiten
- Der User liefert den Protokollinhalt (Stichpunkte, Notizen, Agenda, etc.).
- Inhalt im **Confluence Wiki-Markup** strukturieren (NICHT Markdown — Markdown verliert Einrueckungsebenen auf Confluence Server/DC).
- Typische Struktur fuer ein Protokoll:

```
h2. Themen

* Thema 1 (Verantwortlicher)
** Detail / Ergebnis
** Naechste Schritte
** *Maßnahmen*
*** {Confluence Task-Liste hier eingerueckt — siehe Abschnitt "TODOs / Aufgaben in Protokollen"}
* Thema 2 (Verantwortlicher)
** Detail / Ergebnis
```

- **Wiki-Markup Kurzreferenz:**
  - Listen-Ebenen: `*` (L1), `**` (L2), `***` (L3), `****` (L4)
  - Headings: `h1.`, `h2.`, `h3.` etc.
  - Bold: `*text*` (nur inline, NICHT am Zeilenanfang — dort bedeutet `*` Listenpunkt)
  - Links: `[Anzeigetext|https://url]`
  - Tabellen: `||Kopf1||Kopf2||` und `|Zelle1|Zelle2|`

- **TODOs** werden NICHT in einem eigenen Abschnitt gesammelt, sondern als **Unterpunkt "Maßnahmen"** direkt beim jeweiligen Thema eingefuegt — eingerueckt unter dem Thema.
- TODOs muessen als Confluence `<ac:task-list>` angelegt werden (siehe eigener Abschnitt unten), NICHT als Markdown-Tabelle.
- Falls der User nur Stichpunkte liefert, diese sinnvoll in die obige Struktur bringen.
- Falls der User Rohdaten aus einem Chat/Meeting liefert, daraus ein strukturiertes Protokoll formen.
- **Einrueckungen beibehalten:** Wenn die bestehende Seite bereits eine verschachtelte Listenstruktur hat, MUESSEN die vorhandenen Einrueckungsebenen exakt erhalten bleiben. Keine Ebene darf beim Update verloren gehen oder flacher werden.
- **Zusaetzliche Einrueckungen erlaubt:** Ergaenzungen duerfen gerne weitere Einrueckungsebenen nutzen, um die Lesbarkeit zu verbessern (z.B. Details unter einem Unterpunkt nochmals einruecken).
- Bitte immer kompakt in stenoartigem Stil schreiben. Nur Fakten, praezise formuliert. Keine Verallgemeinerungen oder vage oder unpraezise Formulierungen.

### 5. Seite anlegen
- Tool: `mcp_mcp-atlassian_confluence_create_page`
- Parameter:
  - `space_key`: `"VOBES"` (bzw. `"EKEK1"` fuer KC Vibe Coding)
  - `title`: Zusammengesetzter Titel (siehe Schritt 3)
  - `content`: Vorbereiteter Wiki-Markup-Inhalt (siehe Schritt 4)
  - `parent_id`: ID der Sammlerseite aus der Tabelle
  - `content_format`: `"wiki"`

### 6. Ergebnis bestaetigen
- Erfolgsmeldung pruefen.
- URL der neuen Seite an den User ausgeben.
- `page_id` merken fuer eventuelle Nachbearbeitungen.

## Ablauf: Bestehendes Protokoll ueberarbeiten

### 1. Protokollseite finden
- Entweder der User liefert die `page_id` direkt.
- Oder: Ueber `mcp_mcp-atlassian_confluence_get_page_children` die Kindseiten der Sammlerseite durchsuchen und die Seite anhand des Datums im Titel identifizieren.

### 2. Aktuellen Inhalt laden
- Tool: `mcp_mcp-atlassian_confluence_get_page`
- Parameter: `page_id`, `include_metadata=true`, `convert_to_markdown=false`
- **Wichtig:** `convert_to_markdown=false` verwenden, damit `<ac:>`-Makros (Tasks, Jira-Links, Status etc.) im Original-Storage-Format erhalten bleiben. Bei `convert_to_markdown=true` gehen diese Makros verloren oder werden in nicht-rueckkonvertierbares Markdown umgewandelt.

### 3. Inhalt anpassen
- Aenderungen des Users direkt im **Storage-Format** (XHTML) einarbeiten.
- Bestehende `<ac:>`-Makros (Tasks, Jira-Verweise, Status-Makros etc.) NICHT veraendern oder entfernen.
- Neue Textabschnitte als XHTML einfuegen (z.B. `<h2>Themen</h2>`, `<ul><li>...</li></ul>`).
- Struktur beibehalten, keine unnoetige Umformatierung.

### 4. Seite updaten
- Ablauf gemaess Skill `$skill-update-confluence-page`:
  - Tool: `mcp_mcp-atlassian_confluence_update_page`
  - Parameter:
    - `page_id`
    - `title` (unveraendert!)
    - `content` (vollstaendiger aktualisierter Inhalt im Storage-Format)
    - `content_format`: `"storage"`
    - `version_comment`: Kurzer Kommentar zur Aenderung

### 5. Ergebnis bestaetigen
- Erfolgsmeldung pruefen.
- URL und Versionsnummer an den User ausgeben.

## Fehlervermeidung

- **NIEMALS** eine Protokollseite auf oberster Ebene im Space anlegen — immer `parent_id` setzen!
- **NIEMALS** die Namenskonvention aendern — bestehende Seiten folgen einem einheitlichen Muster.
- Bei unbekanntem Termin nach Abgleich mit `$skill-orga-ekek1` und `$skill-important-pages-links-and-urls` den User fragen, nicht raten.
- Bei Zweifeln am Datum: Aktuelles Datum vorschlagen und User bestaetigen lassen.
- Titel bestehender Seiten beim Update niemals aendern.
- Kein Mischbetrieb aus MCP und manuellen REST-Calls.

## TODOs / Aufgaben in Protokollen

TODOs in Protokollseiten MUESSEN als Confluence Task-List im **Storage-Format** (HTML) angelegt werden — NICHT als Markdown-Tabelle. Nur so erscheinen sie als echte Confluence-Aufgaben mit Checkbox, Zuweisung und Faelligkeitsdatum.

### Storage-Format einer Task-Liste

```html
<ac:task-list>
<ac:task>
<ac:task-id>{fortlaufende_nummer}</ac:task-id>
<ac:task-status>incomplete</ac:task-status>
<ac:task-body><ac:link><ri:user ri:userkey="{userkey}"></ri:user></ac:link> {Aufgabentext} <time datetime="{YYYY-MM-DD}"></time> </ac:task-body>
</ac:task>
</ac:task-list>
```

### Pflichtfelder pro TODO

| Element | Beschreibung | Pflicht |
|---|---|---|
| `<ac:task-id>` | Fortlaufende Nummer, seitenweit eindeutig | Ja |
| `<ac:task-status>` | `incomplete` (neu) oder `complete` | Ja |
| `<ri:user ri:userkey="...">` | Zugewiesene Person (Confluence-Userkey) | Ja, wenn Person bekannt |
| Freitext in `<ac:task-body>` | Aufgabenbeschreibung | Ja |
| `<time datetime="YYYY-MM-DD">` | **Faelligkeitsdatum** im ISO-Format | **Ja — IMMER angeben!** |

### Regeln

- **Faelligkeitsdatum ist Pflicht** — jedes TODO MUSS ein `<time datetime="...">` enthalten.
- Falls der User kein Datum nennt, nachfragen oder einen sinnvollen Vorschlag machen (z.B. naechster Regeltermin).
- `task-id` fortlaufend vergeben: Bei bestehenden Seiten die hoechste vorhandene ID ermitteln und ab dort weiterzaehlen.
- `task-uuid` kann weggelassen werden — Confluence generiert sie automatisch.
- Mehrere TODOs werden als separate `<ac:task>`-Bloecke innerhalb derselben `<ac:task-list>` angelegt.
- Beim Update einer Seite bestehende Tasks NICHT loeschen oder ueberschreiben, sondern neue Tasks anhaengen.

### Einbettung in den Seiteninhalt

Da Tasks Storage-Format (HTML) benoetigen, muss beim Erstellen/Updaten der Seite darauf geachtet werden:

1. **Bei `content_format="storage"` (EMPFOHLEN)**: Task-Liste direkt im Storage-Format schreiben. Alle `<ac:>`-Makros (Tasks, Jira-Links, Status etc.) werden nativ verarbeitet.
2. **Bei `content_format="wiki"`**: **NICHT verwenden wenn `<ac:>`-Makros vorhanden sind!** Der Wiki-zu-Storage-Converter erkennt `<ac:>`-Namespace-Elemente NICHT und rendert sie als sichtbare HTML-Tags auf der Seite.
3. **Bei `content_format="markdown"`**: Markdown unterstuetzt KEINE Confluence-Makros. Falls die Seite TODOs, Jira-Links oder andere Makros enthaelt, MUSS `"storage"` verwendet werden.

### Beispiel: Zwei TODOs mit Zuweisung und Datum

```html
<ac:task-list>
<ac:task>
<ac:task-id>1</ac:task-id>
<ac:task-status>incomplete</ac:task-status>
<ac:task-body><ac:link><ri:user ri:userkey="4028949e6b21d06c016b2ca19cd30041"></ri:user></ac:link> Erstellt zentrale Story; andere Teams klonen/verlinken <time datetime="2026-04-16"></time> </ac:task-body>
</ac:task>
<ac:task>
<ac:task-id>2</ac:task-id>
<ac:task-status>incomplete</ac:task-status>
<ac:task-body><ac:link><ri:user ri:userkey="402894975ee80eb60160e0bd895501a3"></ri:user></ac:link> Klont relevante Findings fuer VMDS <time datetime="2026-04-16"></time> </ac:task-body>
</ac:task>
</ac:task-list>
```

## Diff-Review-Workflow (Standard)

Vor jedem Confluence-Write MUSS der Diff-Review-Workflow durchlaufen werden. Das Script `scripts/confluence_md_bridge.py` uebernimmt Konvertierung, Diff-Oeffnung und Benachrichtigung.

### Ablauf

```
1. MCP: get_page(page_id, convert_to_markdown=false)
   → Agent speichert content als userdata/tmp/page_raw.html

2. Agent: Protokoll aus Transkript aufbereiten
   → Schreibt Ergaenzungen als MD in userdata/tmp/page_after.md
   (page_before.md wird vom Script erzeugt)

3. Terminal:
   python scripts/confluence_md_bridge.py prepare \
     --before userdata/tmp/page_raw.html \
     --after  userdata/tmp/page_after.md \
     --notify "Protokoll XYZ — Diff bitte reviewen"
   → VS Code Diff oeffnet sich
   → Windows-Popup erscheint

4. ── User reviewt, editiert page_after.md, sagt "go" ──

5. Terminal:
   python scripts/confluence_md_bridge.py finalize \
     --input  userdata/tmp/page_after.md \
     --output userdata/tmp/page_updated.html \
     --base   userdata/tmp/page_raw.html

6. Agent: Liest page_updated.html
   MCP: update_page(page_id, title=UNCHANGED, content=..., content_format="storage")

7. Bestaetigung: URL + Version an User
```

### Markdown-Annotationen (Referenz)

| Confluence-Element | Markdown-Darstellung |
|---|---|
| `<ac:task>` (incomplete) | `- [ ] Text <!-- task id=N uuid=xxx status=incomplete -->` |
| `<ac:task>` (complete) | `- [x] Text <!-- task id=N uuid=xxx status=complete -->` |
| `<ri:user>` | `@[userkey:xxx]` |
| `<time>` | `(bis YYYY-MM-DD)` |
| `<ac:emoticon name="tick">` | ✅ |
| `<ac:emoticon name="warning">` | ⚠️ |
| `<ac:emoticon name="cross">` | ❌ |
| `<ri:page>` | `[[Seitentitel]]` |
| Unbekannte `<ac:>`-Bloecke | `<!-- confluence:raw -->` Passthrough |

### Utility-Commands

- `python scripts/confluence_md_bridge.py storage2md <in.html> <out.md>` — nur Konvertierung
- `python scripts/confluence_md_bridge.py md2storage <in.md> <out.html>` — nur Konvertierung

## Sonderfaelle

- **Planung 2026**: Keine datumsbasierten Protokollseiten. Hier wird direkt auf bestehenden Seiten gearbeitet (Update-Workflow).
- **Neuer Regeltermin ohne Eintrag**: Falls der User einen Termin nennt, der nicht in der Tabelle steht, nachfragen und ggf. die Sammlerseite und Namenskonvention klaeren bevor eine Seite erstellt wird.
- **Mehrere Protokolle am selben Tag**: Falls bereits ein Protokoll mit identischem Datum existiert, ist das ein Hinweis, dass der Update-Workflow genutzt werden soll. Kein Duplikat erzeugen!

## Workflow B: Protokoll aus Teams-Recording oder Audioaufzeichnung

Trigger: User sagt z.B. *"Bitte Protokoll erstellen"*, *"Mache das Protokoll vom letzten Termin"*, *"Protokoll vom Meeting XY"* oder *"Protokoll aus Recording bauen"*.

Quellen (Kaskade, beide werden gelesen und chronologisch zusammengefuehrt):
1. OneDrive `Recordings/` — Teams-Aufzeichnungen, Dateiname `{Title}-YYYYMMDD_HHMMSS-Besprechungstranskript.mp4`. **Graph-Token** fuer Listing, **SharePoint-Token** fuer VTT via `/media/transcripts/{id}/streamContent?is=1&applymediaedits=false`. Der `applymediaedits=false`-Parameter ist Pflicht — ohne ihn liefert SharePoint ein "edited" VTT ohne `<v Speaker>`-Tags. (VTT wird nicht mit OneDrive synchronisiert.) Fallback fuer fremd-organisierte Meetings: `iCalUid` aus Calendar → Outlook-Collab-API `https://outlook.office.com/Collab/v1/smtp:{mail}/collabs?collab_id=2SMTP:{mail}externalentitykey:{iCalUid}` mit `outlook.office.com/.default`-Token, dann `TranscriptV2.location` parsen.
2. OneDrive `Dokumente/Audioaufzeichnungen/` — manuell aufgenommene Audios, Dateiname `meeting_YYYYMMDD_HHMM-HHMM.md` (Start- und Endzeit). **Wird lokal gelesen** (OneDrive-Sync), kein Token fuer Listing und Fetch. `.mp3` und Altformate werden ignoriert. Titel kommt aus Outlook-Kalender (Graph `calendarView`, exaktes Zeitfenster — Token-pflichtig).
3. **Screenshots** (automatisch): `fetch` sammelt Bilder aus `~/OneDrive - Volkswagen AG/Desktop/Screenshots/` (lokal) deren Aufnahmezeit im Meeting-Fenster liegt (Recording: Start bis Ende des letzten VTT-Cues; Audio: Start bis Ende+1 Min). Dateien werden nach `userdata/sessions/{slug}/screenshots/` kopiert und in `meta.json["screenshots"]` mit `filename`, `takenAt`, `offsetSeconds`, `title` erfasst.

### Ablauf

1. `python .agents/skills/skill-protokoll-confluence/scripts/recordings.py list-recent --limit 5`
   → Markdown-Tabelle mit Source, Name, Start/Ende, Item-ID, Regel-Match und Ziel-Confluence-Seite.
2. Neuesten Eintrag dem User als Vorschlag formulieren:
   > *"Meinst Du das Protokoll **{Name|Kalendertermin}** vom **{Datum} {Uhrzeit}**? Soll ich es in die Confluence-Seite **{Titel}** (parent `{parent_id}`, Space `{space}`) integrieren?"*
   - Bei Audio-Fallback: Name kommt aus `calendarSubject` (Outlook), nicht aus dem Dateinamen.
3. Bei **Bestaetigung**:
   - a. `recordings.py fetch <item-id>` → Recording: `transcript.vtt`; Audio: `transcript.md`/`.txt`. Ablage in `userdata/sessions/{YYYYMMDD_HHMM}_{slug}/` + `meta.json`.
   - b. `recordings.py suggest-page <item-id>` → JSON `{matched, title, parent_id, space, calendarSubject}`.
   - c. Transkript lesen, Protokoll-Markdown bauen (Themen / Diskussion / Beschluesse / Massnahmen — identisch zu Workflow A, Wiki-Markup oder Storage-Format).
     - Screenshots aus `meta.json["screenshots"]` thematisch einsortieren: pro Eintrag anhand `offsetSeconds` (Recording) bzw. `takenAt` (Audio) den passenden Agendapunkt finden und als `![{title}](screenshots/{filename})` einfuegen. `confluence_md_bridge.py` konvertiert diese Markdown-Images automatisch in `<ac:image ac:width="800"><ri:attachment ri:filename="..." /></ac:image>`.
   - d. **Update** (bestehende Kindseite mit gleichem Titel vorhanden) → Skill `$skill-update-confluence-page` mit `confluence_md_bridge.py prepare/finalize`. **Vor** dem `update_page` die Screenshots mit `mcp_mcp-atlassian_confluence_upload_attachments` (`content_id=page_id`, `file_paths`=Komma-Liste der Absolutpfade aus `screenshots/`) hochladen — sonst rendern die `<ac:image>`-Tags als "broken attachment".
   - d. **Create** (kein Treffer) → `mcp_mcp-atlassian_confluence_create_page` mit `parent_id` + `space_key` aus `suggest-page`. Direkt nach Create: `mcp_mcp-atlassian_confluence_upload_attachments` mit `content_id={page_id}` und allen Screenshot-Pfaden.
4. Bei **kein Match** (weder Recording-Prefix noch Kalender-Subject trifft eine Regel):
   - Protokoll-Markdown lokal in `userdata/sessions/{YYYYMMDD_HHMM}_{slug}/protokoll.md` speichern.
   - Hinweis an User: *"Nicht in Confluence integriert, da kein bekannter Regeltermin. Lokal unter `userdata/sessions/…` archiviert."*
5. Bei **mehreren Kandidaten** oder wenn User "letzter Termin" nicht = #1: Top-5 listen und auswaehlen lassen.

### Voraussetzungen fuer Workflow B

- **Audio + Screenshots**: OneDrive-Sync der Ordner `Dokumente/Audioaufzeichnungen/` und `Desktop/Screenshots/`. Kein Token noetig.
- **Recordings**: Teams-Token im Cache (`userdata/tmp/.graph_token_cache_teams.json`) mit Scope `Calendars.Read` + `Files.ReadWrite.All`. Refresh-Token im Teams-LocalStorage (Script refresht SharePoint-Token automatisch ueber `m365_mail_search_token`).
- **Kalender-Subject-Lookup fuer Audio**: Graph-Token (Scope `Calendars.Read`). Faellt ohne Token auf Filename-Stem zurueck.
- Confluence-MCP `mcp-atlassian` verfuegbar (nur wenn Push gewuenscht).

## Workflow C: Register + Queue fuer unverarbeitete Transkriptionen

Zweck: zentraler Ueberblick in `userdata/transcriptions/transcriptions.csv` und systematische Abarbeitung offener Transkriptionen.

### Register-Regeln

- Master-Ordner: `userdata/transcriptions/`
- CSV: `userdata/transcriptions/transcriptions.csv` (Delimiter `;`, UTF-8 BOM)
- Transkript-Markdown: `userdata/transcriptions/transcripts/YYYY-MM-DD_HHMM__{source}__{meeting-title}.md`
- Mehrere Integrationsziele pro Eintrag: Feld `integrated_targets` mit **Zeilenumbruechen** innerhalb einer Zelle.

### CSV-Felder (11)

`transcription_id;meeting_at;meeting_title;source_type;source_item_id;source_location;transcript_md_path;integrated_targets;suggested_title;last_action_at;notes`

### Titel-Logik (Pflicht)

- `recording`: Titel aus Teams-Dateinamen (`{Title}-YYYYMMDD_HHMMSS-Besprechungstranskript.mp4`).
- `audio`: Titel aus Outlook-Kalender.
- Kalender-Matching priorisiert Meetings **mit Kategorie** vor Meetings ohne Kategorie; bei Gleichstand entscheidet Zeitnaehe.

### Kommandos

1. Register aktualisieren:
   `python .agents/skills/skill-protokoll-confluence/scripts/recordings.py sync-register`
2. Naechste offene Transkription:
   `python .agents/skills/skill-protokoll-confluence/scripts/recordings.py next-open`
3. Offene Liste:
   `python .agents/skills/skill-protokoll-confluence/scripts/recordings.py list-open --limit 20`
4. Master-Transkript materialisieren:
   `python .agents/skills/skill-protokoll-confluence/scripts/recordings.py materialize-transcript <transcription_id|source_item_id>`
5. Integration markieren (mehrfach moeglich):
   `python .agents/skills/skill-protokoll-confluence/scripts/recordings.py mark-integrated <transcription_id|source_item_id> --target "confluence|url=...|page_id=...|space=...|title=..."`

### Agentischer Queue-Ablauf

1. `sync-register` ausfuehren.
2. `next-open` aufrufen und Eintrag vorschlagen.
3. Bei Bestaetigung:
   - `materialize-transcript ...`
   - Protokoll erstellen/integrieren (Workflow A/B).
   - `mark-integrated ... --target "..."`
4. Wieder zu Schritt 2 bis `next-open` => `{"open": false}`.

## Hinweis

Alternativ kann das Protokoll auch über den skill skill-m365-copilot-chat mit dem prompt in
m365_copilot_protokoll_prompt.md
erzeugt werden.
Bitte im Prompt in <Termin> den Titel und Datum + Startzeit einsetzen und in <content> den aktuellen Inhalt der Seite als Markdown.
