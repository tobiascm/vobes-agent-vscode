---
name: skill-protokoll-confluence
description: Protokollseiten fuer Regeltermine erstellen, ueberarbeiten und in Confluence speichern. Gilt fuer alle Termine mit Sammlerseite im Space VOBES oder EKEK1.
---

## Zweck

Dieser Skill steuert das Erstellen und Aktualisieren von Protokollseiten in Confluence.
Jede Protokollseite MUSS:
1. Als **Kindseite** unter der zugehoerigen Sammlerseite angelegt werden (`parent_id`).
2. Die **Namenskonvention** des jeweiligen Termins einhalten.
3. Im Space **VOBES** (oder **EKEK1** fuer KC Vibe Coding) liegen.

## Voraussetzungen

- Skill `$skill-important-pages-links-and-urls` muss bekannt sein (enthaelt die Sammlerseiten).
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

> **Datum-Format:** Immer `YYYY-MM-DD` (ISO 8601). Das Datum im Titel ist das Termindatum, NICHT das Erstellungsdatum.

## Ablauf: Neues Protokoll erstellen

### 1. Termin identifizieren
- Frage den User, zu welchem Regeltermin das Protokoll gehoert, falls nicht eindeutig.
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
- Inhalt als Markdown strukturieren.
- Typische Struktur fuer ein Protokoll:

```markdown
## Themen

* Thema 1 (Verantwortlicher)
  + Detail / Ergebnis
  + Naechste Schritte
* Thema 2 (Verantwortlicher)
  + Detail / Ergebnis

## Offene Punkte / TODOs

| # | Aufgabe | Verantwortlich | Termin |
|---|---------|----------------|--------|
| 1 | ... | ... | ... |
```

- Falls der User nur Stichpunkte liefert, diese sinnvoll in die obige Struktur bringen.
- Falls der User Rohdaten aus einem Chat/Meeting liefert, daraus ein strukturiertes Protokoll formen.
- Bitte immer kopakt in stenoartigem Stil schreiben. Nur Fakten, präziese formuliert. Keine Verallgemeinerungen, oder vagfe oder unrpäszise Formulierungen.

### 5. Seite anlegen
- Tool: `mcp_mcp-atlassian_confluence_create_page`
- Parameter:
  - `space_key`: `"VOBES"` (bzw. `"EKEK1"` fuer KC Vibe Coding)
  - `title`: Zusammengesetzter Titel (siehe Schritt 3)
  - `content`: Vorbereiteter Markdown-Inhalt (siehe Schritt 4)
  - `parent_id`: ID der Sammlerseite aus der Tabelle
  - `content_format`: `"markdown"`

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
- Parameter: `page_id`, `include_metadata=true`, `convert_to_markdown=true`

### 3. Inhalt anpassen
- Aenderungen des Users in den bestehenden Markdown-Inhalt einarbeiten.
- Struktur beibehalten, keine unnoetige Umformatierung.

### 4. Seite updaten
- Ablauf gemaess Skill `$skill-update-confluence-page`:
  - Tool: `mcp_mcp-atlassian_confluence_update_page`
  - Parameter:
    - `page_id`
    - `title` (unveraendert!)
    - `content` (vollstaendiger aktualisierter Markdown-Inhalt)
    - `content_format`: `"markdown"`
    - `version_comment`: Kurzer Kommentar zur Aenderung

### 5. Ergebnis bestaetigen
- Erfolgsmeldung pruefen.
- URL und Versionsnummer an den User ausgeben.

## Fehlervermeidung

- **NIEMALS** eine Protokollseite auf oberster Ebene im Space anlegen — immer `parent_id` setzen!
- **NIEMALS** die Namenskonvention aendern — bestehende Seiten folgen einem einheitlichen Muster.
- Bei unbekanntem Termin den User fragen, nicht raten.
- Bei Zweifeln am Datum: Aktuelles Datum vorschlagen und User bestaetigen lassen.
- Titel bestehender Seiten beim Update niemals aendern.
- Kein Mischbetrieb aus MCP und manuellen REST-Calls.

## Sonderfaelle

- **Planung 2026**: Keine datumsbasierten Protokollseiten. Hier wird direkt auf bestehenden Seiten gearbeitet (Update-Workflow).
- **Neuer Regeltermin ohne Eintrag**: Falls der User einen Termin nennt, der nicht in der Tabelle steht, nachfragen und ggf. die Sammlerseite und Namenskonvention klaeren bevor eine Seite erstellt wird.
- **Mehrere Protokolle am selben Tag**: Falls bereits ein Protokoll mit identischem Datum existiert, ist das ein Hinweis, dass der Update-Workflow genutzt werden soll. Kein Duplikat erzeugen!
