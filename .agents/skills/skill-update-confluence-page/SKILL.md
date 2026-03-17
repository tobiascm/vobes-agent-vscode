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

---

## EKEK/1 Dashboard: Aura-Card-Kachel hinzufuegen

Das EKEK/1 Dashboard (Page-ID `6926484665`, Space `EKEK1`) verwendet das Confluence-Plugin **Aura Cards** (`ac:structured-macro ac:name="aura-cards"`).
Jede Sektion (z.B. "KI-Tools und Chatbots") ist eine eigene Aura-Card-Instanz mit einem JSON-Array (`cardsCollection`) fuer die einzelnen Kacheln.
Der Seiteninhalt liegt im Confluence-Storage-Format (XML) vor — daher kann er **nicht** per Markdown bearbeitet werden.

Fuer das Einfuegen neuer Kacheln nutze das Script `scripts/dashboard_add_card.py`.

### Workflow
1. Seite laden: `mcp_mcp-atlassian_confluence_get_page(page_id="6926484665", convert_to_markdown=false)`
2. Ergebnis-JSON in eine temp-Datei speichern (z.B. `userdata/tmp/page_content.json`)
3. Script ausfuehren:
   ```
   python scripts/dashboard_add_card.py <content_json> <output_file> --marker "<marker>" --card '<card_json>'
   ```
4. Inhalt aus `<output_file>` lesen
5. `mcp_mcp-atlassian_confluence_update_page(page_id="6926484665", title="EKEK/1 - Dashboard", content=<inhalt>, content_format="storage")`

### Marker pro Sektion
| Sektion                     | Marker-Text                          |
|-----------------------------|--------------------------------------|
| VOBES 2025                  | VOBES 2025 Ziele und Vision          |
| VOBESplus (inkl. SYS)       | SYS-Flow Klickanleitung              |
| Kommunikation               | Regeltermine                         |
| Prozesse und Regelungen     | Führungskräfteordner                 |
| Fahrzeugprojekte            | Migrationsübersicht (ausstehend)     |
| Budget                      | Planungs-Auswertungs-Excel           |
| KI-Tools und Chatbots       | EHD Chatbot (Eddy)                   |

### Card-JSON Pflichtfelder
- `title`: Anzeigename der Kachel
- `href`: Ziel-URL
- `hrefType`: immer `"link"`

### Card-JSON optionale Felder (mit Defaults)
- `body`: Beschreibungstext (Default: leer)
- `color`: Farbe als Hex oder `{"light":"#hex"}` (Default: `#66afff`)
- `icon`: FontAwesome-Icon (Default: `faLink`)
- `hrefTarget`: `"_blank"` (Default)
- `image`: Unsplash-URL (Default: wird automatisch gewaehlt)
- `imageType`: `"link"` (Default)

### Beispiel
```
python scripts/dashboard_add_card.py userdata/tmp/page.json userdata/tmp/modified.html \
  --marker "EHD Chatbot (Eddy)" \
  --card '{"title":"Mein Tool","body":"Beschreibung","color":"#66afff","icon":"faDesktop","href":"https://example.com","hrefType":"link","hrefTarget":"_blank"}'
```

### Exit-Codes
- 0: Erfolg
- 1: Fehler (Marker nicht gefunden, ungueltiges JSON, etc.)
- 2: Kachel existiert bereits (Duplikat-Schutz)
