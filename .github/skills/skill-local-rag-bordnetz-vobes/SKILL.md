---
name: skill-local-rag-bordnetz-vobes
description: Nutze local_rag systematisch fuer Fragen zur Wissensbasis in Bordnetz- und VOBES-Themen. Verwende den Skill bei fachlichen Fragen zu Spezifikationen, Prozessen, Datenmodellen, Jira/Confluence-Inhalten und Artefakten rund um VOBES 2025, wenn Evidenz aus der lokalen Knowledge Base benoetigt wird.
---
## Ziel

- Liefere belastbare Antworten aus der lokalen Wissensbasis.
- Waehle die passende Knowledgebase gezielt aus.
- Belege Kernaussagen mit Chunks und bei Bedarf mit Readback.
- Nutze `mcp-atlassian` nur fuer Aufgaben, die `local_rag` nicht leisten kann (z. B. Seiten/Tickets erstellen oder aendern).

## Knowledgebase-Auswahl

- Nutze immer lower-case fuer `knowledgebase`.
- Verwende:
  - `default` fuer allgemeine VOBES-/VOBES-2025-Spezifikationen (Confluence VOBES + VSUP).
  - `datenmodelle` fuer VEC/KBL-Inhalte; filtere auf Spaces, damit VEC und KBL nicht vermischt werden.
  - `jira-vkon2` fuer umgesetzte User Stories und aktuelle Epics.
  - `ldorado` nur fuer Bedienung/Spezifikation zu LDorado (Capital Harness LD).
  - `chd` nur fuer Capital Harness ohne LD.
  - `prozesse` fuer Prozessdokumente, Normen und Lastenhefte.

## Pflicht-Workflow

1. Klaere bei unklarer Anfrage zuerst den Scope (z. B. VEC-1.2 vs. VEC-2.2), bevor du Retrieval startest.
2. Starte mit `rag_retrieve`:
   - setze `question` fachlich praezise.
   - setze `knowledgebase` passend.
   - nutze optional `metadata_filter_json` bei hoher Mehrdeutigkeit.
3. Parse das Tool-Ergebnis als JSON.
4. Befolge `instruction` und nutze primaer `chunks`, `references`, `entities`, `relationships`.
5. Pruefe `is_enough_for_answer`, `coverage_gaps`, `recommended_next_actions`.
6. Wenn Evidenz nicht reicht (`is_enough_for_answer=false` oder Luecken sichtbar), fuehre mindestens einen weiteren Tool-Schritt aus:
   - zweites `rag_retrieve` mit schaerferer Frage/Filter/`max_chunks`, oder
   - Readback via `get_document_content`/`get_attachment_content`.
7. Nutze bei relevanten Jira/Confluence-Dokumenten `list_attachments` und lade wichtige Anhaenge nach.
8. Finalisiere erst, wenn alle zentralen Aussagen belegbar sind.

## Readback-Regeln

- Verwende Referenzen aus `rag_retrieve.references` als Input fuer:
  - `get_document_content`
  - `list_attachments`
- Verwende `attachment_url` aus `list_attachments.attachments[]` als `reference` fuer:
  - `get_attachment_content`
- Behalte dieselbe `knowledgebase` ueber den gesamten Folge-Workflow bei.
- Nutze `from_line`/`to_line` nur 1-basiert und mit `to_line >= from_line`.

## Antwortformat

- Antworte in der Sprache des Users.
- Antworte konkret und ohne unbelegte Verallgemeinerungen.
- Benenne unbelegte Teilaspekte explizit als "im Kontext nicht vorhanden".
- Fuege bei laengeren Antworten ein `TL;DR` hinzu.
- Schliesse immer mit einer Referenzuebersicht.
- Bei PDF-Referenzen haenge die Seite als `#page=X` an.

## Beispiele

Retrieval:

```json
{"tool":"rag_retrieve","arguments":{"question":"Welche Aenderungen gibt es am Stammdatenservice in VOBES 2025?","knowledgebase":"default","mode":"mix","max_chunks":20}}
```

Datenmodell-Fokus (VEC-2.2):

```json
{"tool":"rag_retrieve","arguments":{"question":"Welche Pflichtattribute hat der Leitungssatz im VEC?","knowledgebase":"datenmodelle","metadata_filter_json":"{\"space\":\"VEC-2.2\"}","mode":"mix","max_chunks":25}}
```

Dokument-Readback:

```json
{"tool":"get_document_content","arguments":{"reference":"https://devstack.vwgroup.com/jira/browse/VKON2-12345","knowledgebase":"default","from_line":1,"to_line":120}}
```

Anhaenge:

```json
{"tool":"list_attachments","arguments":{"reference":"https://devstack.vwgroup.com/jira/browse/VKON2-12345","knowledgebase":"default"}}
```

```json
{"tool":"get_attachment_content","arguments":{"reference":"https://devstack.vwgroup.com/jira/secure/attachment/73805/Anhang.pptx","knowledgebase":"default","from_line":1,"to_line":80}}
```
