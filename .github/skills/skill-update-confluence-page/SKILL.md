---
name: skill-update-confluence-page
description: Standardisierter Ablauf, um eine bestehende Confluence-Seite ausschließlich über MCP-Tools zu aktualisieren.
---
## Regeln

- Nutze nur MCP-Funktionen, **keine** direkten REST-/Terminal-Updates.
- Für Seitenänderungen immer `mcp_mcp-atlassian_confluence_update_page` verwenden.
- Vor dem Update den aktuellen Inhalt per `mcp_mcp-atlassian_confluence_get_page` laden.
- Bei Tabellen den kompletten Tabellenblock im Markdown konsistent zurückschreiben.

## Inputs

- `page_id` (z. B. `6952668174`)
- Gewünschte Änderung (z. B. „Zeile 3 ergänzen“)
- Optional: `version_comment`

## Ablauf (Playbook)

1. **Seite laden**
   - Tool: `mcp_mcp-atlassian_confluence_get_page`
   - Parameter: `page_id`, `include_metadata=true`, `convert_to_markdown=true`
2. **Inhalt anpassen**
   - Gewünschte Zeile/Abschnitt im Markdown ändern
   - Struktur (Tabellenkopf/Spalten) unverändert lassen
3. **Seite updaten**
   - Tool: `mcp_mcp-atlassian_confluence_update_page`
   - Parameter:
     - `page_id`
     - `title` (unverändert von der Seite)
     - `content` (vollständiger aktualisierter Markdown-Inhalt)
     - `content_format="markdown"`
     - optional `version_comment`
4. **Ergebnis validieren**
   - Erfolgsmeldung prüfen (`message: Page updated successfully`)
   - `version` und `url` notieren

## Beispiel: Workshop in Tabellenzeile ergänzen

Zielseite: `Ideen für Vorträge, Workshops, Hackathon 2026` (Space `VOBES`)

Beispiel-Zeile:

| 3 | CAN- & K2.0-Datenmodell dokumentierbar machen (XSD + Semantik) | Ziel: Modellwissen aus Code in nutzbare Doku überführen (Schema/XSD, Kernfelder, Beispiele). Use-Case: Effizienzgewinn für Entwickler und Spezifikateure durch schnellere Klärung fachlicher Fragen via RAG/MCP und weniger Rückfragen. | Tobias Müller / Rainer Ganss | Workshop | 60 Min |

## Fehlervermeidung

- Kein Mischbetrieb aus MCP und manuellen REST-Calls.
- Bei Umlauten/Zeichenproblemen direkt im Markdown gegenprüfen.
- Nur die gewünschte Stelle ändern, keine unnötigen Strukturänderungen.
