---
name: skill-deep-research
description: "Mehrstufige, quellenuebergreifende Recherche orchestrieren. Erzeugt Research Brief, Rechercheplan, iterative Quellenanalyse, Evidenzsammlung mit Vertrauensgraden und strukturierten Abschlussbericht. Confluence-Inhalte werden per mcp-atlassian gelesen und durchsucht; alle anderen Browser-Interaktionen werden an skill-browse-intranet delegiert. Trigger: Recherchiere systematisch, Untersuche systematisch, Deep research, Multi-Source-Recherche, evidence-backed research across portals."
---

# Skill: Deep Research

Meta-Skill zur **systematischen, quellenuebergreifenden Recherche** ueber mehrere Webseiten und interne Portale. Erzeugt evidenzbasierte Antworten mit transparentem Suchweg.

Dieser Skill **orchestriert** die Recherche — **Confluence-Inhalte** werden per `mcp-atlassian` gelesen und durchsucht, alle anderen Browser-Interaktionen werden an `skill-browse-intranet` delegiert.

---

## Organisationskontext (PFLICHT)

Wir arbeiten bei **Volkswagen (VW)** in der Abteilung **EKEK/1**. Dieser Kontext ist fuer jede Recherche bindend:

### Grundregel: VW-Prozesse bevorzugen

- **VW-Dokumente** (Volkswagen AG, Konzern-TE, VW-spezifische Regelwerke, EKEK-Inhalte) sind die **primaere und verbindliche Quelle**.
- **Audi-Dokumente** (Audi AG, AUDI-spezifische Prozesse, Audi-Arbeitsanweisungen) **gelten NICHT fuer VW**. Sie duerfen nur als **ergaenzender Hinweis** herangezogen werden, niemals als verbindliche Antwort.
- Bei jeder Fundstelle MUSS geprueft werden, ob es sich um ein VW- oder Audi-Dokument handelt (siehe Phase C, Schritt 4a).
- Wenn sowohl VW- als auch Audi-Quellen vorliegen, werden **ausschliesslich die VW-Quellen** fuer die Kernantwort verwendet. Audi-Quellen werden separat als Hinweis dokumentiert.

### Erkennungsmerkmale

| Merkmal | VW-Dokument | Audi-Dokument |
|---------|-------------|---------------|
| Logo / Branding | VW-Logo, Volkswagen AG | Audi-Logo, Audi AG |
| URL-Bestandteile | `volkswagen`, `vw`, `vobes`, `ekek` | `audi`, `audi.de`, `AUDI` |
| OE-Bezeichnungen | EKEK, EK, TE (VW-Kontext) | I/xx (Audi-Kuerzel) |
| Regelwerk-Praefix | PS-VW, AA-VW | PS-AUDI, AA-AUDI |
| Confluence Spaces | VOBES, VSUP, EKEK1 | Audi-spezifische Spaces |

---

## Wann verwenden?

- Offene Recherchefragen: "Recherchiere systematisch...", "Untersuche systematisch...", "Deep research:..."
- Fragen, die Informationen aus **mehreren Quellen** erfordern
- Anfragen nach evidenzbasierten Antworten mit Quellenvergleich
- Wenn unklar ist, welche Portale/Seiten die Antwort enthalten

**Faustregel:** Wenn die Frage des Users den Besuch **mehrerer unbekannter Quellen** erfordert, um eine Antwort aufzubauen → diesen Skill verwenden.

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| Einzelne Seite oeffnen / lesen / interagieren | `$skill-browse-intranet` |
| Bekannte URL direkt aufrufen ("Oeffne...", "Geh auf...") | `$skill-browse-intranet` |
| Confluence / Jira **schreiben** (Seite erstellen, aktualisieren, loeschen) | `mcp-atlassian` direkt (nicht ueber Deep Research) |
| Formular ausfuellen, Button klicken, Screenshot | `$skill-browse-intranet` |
| Bordnetz/VOBES-Wissensfrage | `$skill-knowledge-bordnetz-vobes` |

**Entscheidungsregel:** Wenn der User eine **spezifische Seite oder Aktion** benennt → `skill-browse-intranet`. Wenn der User eine **offene Frage** stellt, die mehrere unbekannte Quellen erfordert → `skill-deep-research`.

## Voraussetzungen

1. **Playwright MCP Server** muss aktiv sein (konfiguriert in `.vscode/mcp.json`) — fuer Nicht-Confluence-Seiten
2. **mcp-atlassian** muss aktiv sein (Docker-Container `mcp-atlassian` laeuft) — fuer Confluence-Lesen und -Suche
3. **skill-browse-intranet** muss verfuegbar und funktional sein
4. **`userdata/`** Verzeichnis muss am Repo-Root existieren

### MCP-Verfuegbarkeitspruefung (PFLICHT)

Vor Beginn jeder Recherche MUESSEN **beide** MCP-Server geprueft werden:

```
tool_search_tool_regex(pattern="mcp_playwright")
tool_search_tool_regex(pattern="mcp_mcp-atlassian")
```

**Ergebnismatrix:**

| Playwright | mcp-atlassian | Verhalten |
|-----------|--------------|----------|
| ✅ | ✅ | Normalbetrieb — Confluence per mcp-atlassian, Rest per Playwright |
| ✅ | ❌ | Warnung ausgeben, Confluence-Leads per Playwright/skill-browse-intranet abarbeiten (Fallback) |
| ❌ | ✅ | Nur Confluence-Leads moeglich. Nicht-Confluence-Leads als `rejected` markieren. User warnen. |
| ❌ | ❌ | **SOFORT abbrechen**, keine Teilausfuehrung. |

Falls **beide** fehlen:

> ⚠️ Ich bin aktuell im **Plan-Modus** und habe keinen Zugriff auf die MCP-Server `playwright` und `mcp-atlassian`, die fuer diese Aufgabe benoetigt werden.
>
> **Loesung:** Bitte wechsle in den **Agent-Modus** (ueber das Modus-Dropdown oben im Chat) und stelle die Frage dort erneut.

---

## Workflow

### Phase A: Research Brief (FR-001, FR-001a)

Aus der Nutzerfrage einen strukturierten Rechercheauftrag ableiten. Der Brief wird **vor jeder Recherche** erstellt und dem User praesentiert.

**Pflichtfelder:**

| Feld | Beschreibung |
|------|-------------|
| **Thema** (topic) | Kernthema der Recherchefrage |
| **Ziel** (goal) | Was der User lernen oder entscheiden moechte |
| **Bekannte Start-URLs** (known_start_urls) | Vom User genannte oder offensichtliche Startpunkte |
| **Kandidaten-Systeme** (candidate_systems) | Portale/Systeme, die wahrscheinlich relevante Infos enthalten |
| **Suchbegriffe** (search_terms) | Primaere Keywords |
| **Synonyme** (synonyms) | Alternative Schreibweisen, Abkuerzungen, verwandte Begriffe |
| **Ausschluesse** (constraints) | Scope-Grenzen, Ausschluesse, Zeitgrenzen |
| **Ausgabeformat** (output_format) | Gewuenschtes Format (Zusammenfassung, Detailbericht, Vergleich) |
| **Recherchetiefe** (depth) | shallow / standard / deep |

### Recherchetiefe

| Stufe | Max. Schritte | Verhalten |
|-------|--------------|-----------|
| **shallow** | 10 | Nur bekannte Start-URLs abarbeiten, keine neuen Leads entdecken |
| **standard** (Default) | 25 | Neue Leads entdecken und verfolgen |
| **deep** | 50 | Breite Entdeckung inkl. Crawl4AI (falls verfuegbar) |

Falls der User keine Tiefe angibt, wird `standard` verwendet. Der User kann die Tiefe im Checkpoint (Phase B) anpassen. Bei Fragen, die breites Portal-Scanning implizieren, DARF der Agent `deep` vorschlagen.

---

### Phase B: Rechercheplan (FR-002, FR-002a)

Vor der eigentlichen Recherche einen priorisierten Plan erstellen.

**Anforderungen:**
- **2 bis 15 Leads** im initialen Plan
- Jeder Lead hat: ID, Art (portal_search / url / document / page / export_path / **confluence_search** / **confluence_page**), Label, Quelle, Prioritaet (1 = hoechste), Begruendung, Status (pending)
- **Lead-Typ `confluence_search`**: CQL-basierte Suche in Confluence (z.B. `text ~ "Bordnetz" AND space = VOBES`)
- **Lead-Typ `confluence_page`**: Direktes Lesen einer bekannten Confluence-Seite (per Page-ID oder URL)
- **Stop-Kriterien** definieren: Wann ist die Recherche beendet?

**Beispiel:**

```
Rechercheplan:
1. [Prio 1] confluence_search — CQL: text ~ "Lieferanten-Freigabe" AND space = VOBES — Primaerquelle
2. [Prio 2] confluence_page — Confluence VOBES Prozessseite (pageId=754406190) — bekannte Seite
3. [Prio 3] portal_search — iProject Regelwerk — sekundaere Bestaetigung
4. [Prio 4] page — SharePoint TE-Ablage — moegliche Arbeitsanweisungen
```

### USER CHECKPOINT (PFLICHT)

Nach Erstellung von Brief und Plan: **Brief und Plan dem User praesentieren und auf Bestaetigung warten.**

Der User darf:
- Leads hinzufuegen oder entfernen
- Prioritaeten aendern
- Recherchetiefe anpassen
- Suchbegriffe ergaenzen
- Brief-Felder korrigieren

**Erst nach User-Bestaetigung mit der Recherche beginnen.**

---

### Phase C: Iterativer Research Loop (FR-003, FR-003a, FR-008, FR-009)

Die Recherche erfolgt in Schleifen. Jede Schleife:

1. **Naechsten Lead waehlen** — hoechste Prioritaet, Status `pending`
2. **Quelle besuchen** — je nach Lead-Typ:
    - **Confluence-Lead** (Lead-Typ `confluence_search`, `confluence_page`, oder URL enthaelt `devstack.vwgroup.com/confluence`) → **mcp-atlassian** verwenden:
      - `confluence_search` fuer CQL-Suchen (Space eingrenzen auf VOBES, VSUP, EKEK1 wenn moeglich)
      - `confluence_get_page` fuer bekannte Seiten (Page-ID aus URL extrahieren: `pageId=NNNN`)
      - Falls mcp-atlassian fehlschlaegt → **Fallback auf `skill-browse-intranet`**
    - **Alle anderen Leads** → per `skill-browse-intranet` (NICHT direkte Playwright-Aufrufe!)
3. **Inhalt extrahieren** — relevante Abschnitte lesen, Suchfunktionen bedienen
4. **Relevanz bewerten** — high / medium / low / none
4a. **Quellzugehoerigkeit pruefen: VW vs. Audi (PFLICHT)** — Bei jedem gelesenen Dokument feststellen, ob es ein VW- oder Audi-Dokument ist (siehe Erkennungsmerkmale im Abschnitt "Organisationskontext"):
    - **VW-Dokument** → normal weiterverarbeiten
    - **Audi-Dokument** → Relevanz auf maximal `low` setzen, Vertrauensgrad auf maximal `C` begrenzen, im Agenten-Hinweis als **"Audi-Quelle — nicht direkt auf VW EKEK/1 uebertragbar"** kennzeichnen
    - **Unklar** → im Agenten-Hinweis als "Quellzugehoerigkeit unklar" vermerken, konservativ als Nicht-VW behandeln
5. **Evidenz erfassen** — falls relevant, als Evidence Item dokumentieren
6. **Neue Leads ableiten** — gefundene Links, Verweise, Hinweise als neue Leads eintragen
7. **Status aktualisieren** — Lead-Status auf `done` oder `rejected` setzen
8. **Tracking-Eintrag schreiben** — Schritt in `research_tracking.md` dokumentieren

> **Hinweis:** Jede Schleife verarbeitet genau einen Lead und erzeugt einen Tracking-Eintrag. Wenn ein Lead (z.B. eine Portal-Suche) mehrere relevante Unterseiten liefert, werden diese als **neue Leads** mit hoher Prioritaet in den Plan aufgenommen — nicht als zusaetzliche Schritte desselben Leads.

### Redundanzvermeidung (FR-008)

Den **Research State** laufend pflegen:
- `visited_urls`: Alle bereits besuchten URLs
- `visited_queries`: Alle bereits ausgefuehrten Suchbegriffe

Vor jedem Besuch pruefen:
- URL bereits in `visited_urls`? → Lead als `rejected` markieren (Duplikat)
- Suchbegriff bereits in `visited_queries`? → Alternative verwenden oder ueberspringen

### Stop-Kriterien (FR-009)

Recherche beenden wenn:
- Die Frage belastbar beantwortet ist
- Keine hochwertigen neuen Leads mehr vorhanden
- Weitere Schritte nur Redundanz erzeugen wuerden
- Das **Schrittlimit der gewaehlten Tiefe** erreicht ist (shallow=10, standard=25, deep=50)

### Mid-Research User-Interaktion (FR-003a)

Waehrend der laufenden Recherche MUSS der Skill **Inline-Korrekturen des Users akzeptieren**:
- Neue URLs oder Hinweise → als **hochprioritaere Leads** in den Plan aufnehmen
- Richtungsaenderungen → Plan entsprechend anpassen
- Zusaetzlicher Kontext → in den Research Brief uebernehmen

**Kein Neustart** — die Recherche wird vom aktuellen Stand aus fortgesetzt.

---

### Phase D: Evidenzkonsolidierung (FR-004, FR-012, FR-013, FR-014)

Jede relevante Fundstelle als **Evidence Item** dokumentieren:

| Feld | Beschreibung |
|------|-------------|
| **ID** | E1, E2, E3... |
| **Titel** | Kurztitel der Fundstelle |
| **URL** | Quellseite |
| **Quellsystem** | Portal-/Systemname (z.B. "Confluence VOBES", "BPLUS-NG") |
| **Zusammenfassung** | 1-3 Saetze |
| **Kernfakten** | Extrahierte Aussagen als Liste |
| **Vertrauensgrad** | A / B / C / D (siehe unten) |
| **Zeithinweis** | Datum/Version der Quelle, falls sichtbar |
| **Notizen** | Einschaetzung zur Zuverlaessigkeit |
| **Widersprueche** | Konflikte mit anderen Evidence Items (per ID) |

### Vertrauensgrade

| Grad | Bedeutung | Beispiel |
|------|-----------|---------|
| **A** | Offizielle Primaerquelle / fuehrendes System | BPLUS-NG Live-Daten, Prozessstandard im TE Regelwerk |
| **B** | Offizielle interne Sekundaerquelle | Confluence-Fachseite, Wiki-Dokumentation |
| **C** | Abgeleitete oder indirekte Quelle | Praesentation, Meeting-Protokoll, Forumspost |
| **D** | Schwacher Hinweis / unbestaetigt | Veraltet, Quelle unklar, nur Andeutung |

> **Audi-Regel:** Audi-Dokumente erhalten **maximal Vertrauensgrad C**, auch wenn sie formal offizielle Primaerquellen waeren. Audi-Prozesse und -Regelwerke gelten nicht fuer VW EKEK/1. Sie duerfen nur als ergaenzender Hinweis (nicht als verbindliche Grundlage) in die Antwort einfliessen.

### Lead-Priorisierung (FR-012)

Leads **bevorzugen** wenn:
- Sie auf eine Primaerquelle hindeuten
- Hohe thematische Relevanz
- Neue Information versprechen
- Von mehreren Quellen indirekt bestaetigt
- Zu konkreten Unterseiten / Dokumenten fuehren

### Lead-Abwertung (FR-013)

Leads **zurueckstufen** wenn:
- Redundant (bereits aehnliche Info vorhanden)
- Nur schwache oder veraltete Hinweise
- Keine neuen Informationen zu erwarten
- Nur auf allgemeine Uebersichtsseiten fuehren

### Widerspruchserkennung (FR-014)

Falls Evidence Items sich widersprechen:
- **Explizit kennzeichnen** in beiden Items (`contradictions`-Feld)
- Im **Abschlussbericht** unter "Unsicherheiten / Widersprueche" ausfuehren
- Die belastbarere Quelle (hoeherer Vertrauensgrad) bevorzugen, aber beide dokumentieren

---

### Phase E: Abschlussbericht (FR-006)

Nach Abschluss der Recherche einen strukturierten Bericht erzeugen und als `research_report.md` speichern.

**Report-Vorlage:**

```markdown
# Deep Research Report: {Thema}

## Kurzantwort
{1-3 Saetze mit der Kernantwort}

## Wichtigste Erkenntnisse
- {Erkenntnis 1}
- {Erkenntnis 2}
- ...

## Evidenz / Fundstellen
- [A] {Titel} — {URL} — {Zusammenfassung}
- [B] {Titel} — {URL} — {Zusammenfassung}
- [C] {Titel} — {URL} — {Zusammenfassung}
- [C] [AUDI] {Titel} — {URL} — {Zusammenfassung} *(Audi-Quelle, nicht direkt auf VW uebertragbar)*

## Unsicherheiten / Widersprueche
- {Widerspruch oder Unsicherheit mit betroffenen Evidence-IDs}

## Offene Punkte
- {Offene Frage, die nicht beantwortet werden konnte}

## Tracking-Datei
- Pfad: userdata/research_output/YYYYMMDD_[Title]/research_tracking.md
```

**Speicherort:** `userdata/research_output/YYYYMMDD_[Title]/research_report.md`

---

### Zwischenstand (FR-017)

Bei Recherchen mit **mehr als 10 Schritten**: Alle 10 Schritte einen Zwischenstand inline im Chat ausgeben.

**Format:**

```
## Zwischenstand (Schritt {N})

### Bisher belastbar
- {Erkenntnis 1}
- {Erkenntnis 2}

### Noch offen
- {Offene Frage 1}

### Aktuell verfolgter Pfad
- Lead {ID}: {Label} — {Grund}

### Naechster sinnvoller Schritt
- {Naechste geplante Aktion}
```

Zwischenstaende werden **nicht** in Dateien gespeichert — sie werden inline im Chat angezeigt.

---

## Tracking-Format

### Tracking-Datei: `research_tracking.md`

Die Tracking-Datei dokumentiert den **vollstaendigen Suchweg**. Sie ist ein **menschlich lesbares Research Journal**, nicht nur ein Log.

**Datei-Header:**

```markdown
# Deep Research Tracking

## Research Brief
- Thema: {topic}
- Ziel: {goal}
- Startpunkte: {known_start_urls}
- Suchbegriffe: {search_terms}
- Ausschluesse: {constraints}

## Verlauf
```

**Jeder Schritt:**

```markdown
### Schritt {N}
- URL: {url}
- Quelle/Portal: {source_system}
- Zugangskanal: {mcp-atlassian | skill-browse-intranet}
- Grund: {reason_for_visit}
- Agenten-Hinweis: {agent_note}
- Aktion: {actions_taken}
- Gefunden: {observations}
- Relevanz: {relevance}
- Vertrauensgrad: {confidence}
- Folgepfade: {derived_leads}
- Status: {status}
```

### Tracking-Felder

| Feld | Werte | Beschreibung |
|------|-------|-------------|
| **Relevanz** | high / medium / low / none | Einschaetzung der Relevanz fuer die Forschungsfrage |
| **Vertrauensgrad** | A / B / C / D | Vertrauensstufe der Quelle |
| **Zugangskanal** | mcp-atlassian / skill-browse-intranet | Welcher Kanal zum Lesen verwendet wurde |
| **Status** | weiterverfolgt / abgeschlossen / verworfen | Ergebnis des Schritts |

### Status-Mapping (Lead → Tracking)

| Lead-Status | Tracking-Status |
|-------------|----------------|
| `in_progress` | `weiterverfolgt` |
| `done` | `abgeschlossen` |
| `rejected` | `verworfen` |
| `pending` | Kein Tracking-Eintrag |

### Agenten-Hinweise

Agenten-Hinweise sind **kurze, arbeitsbezogene Beobachtungen** (1-2 Saetze). Sie machen die Denkspur des Agenten sichtbar.

**Gute Beispiele:**
- "Diese Seite wirkt wie eine Uebersichtsseite, nicht wie die Primaerquelle."
- "Hier gibt es einen Link auf ein moeglich relevantes Exportportal."
- "Suchbegriff A liefert nur veraltete Treffer; Synonym B scheint besser."
- "Seite erfordert Login — kann nicht gelesen werden."

**Nicht erwuenscht:**
- Lange, ausufernd freie Gedanken
- Interne Chain-of-Thought-Dumps
- Wiederholung dessen, was in anderen Feldern steht

---

## Ausgabedateien

### Verzeichnisstruktur

Jede Recherche erzeugt ein eigenes Verzeichnis unter `userdata/research_output/`:

```
userdata/research_output/YYYYMMDD_[Title]/
├── research_tracking.md   # Schritt-fuer-Schritt Suchweg
└── research_report.md     # Strukturierter Abschlussbericht
```

**Namenskonvention:**
- `YYYYMMDD` = Datum der Recherche
- `[Title]` = Kurzer Slug aus dem Thema, lowercase, Bindestriche statt Leerzeichen, max 50 Zeichen, ASCII-sicher
- Beispiele: `20260319_supplier-onboarding-process/`, `20260320_bordnetz-regelwerke-uebersicht/`

**Das Verzeichnis wird automatisch erstellt**, falls es noch nicht existiert.

---

## Quellenrouting: Confluence vs. Browser (FR-007)

Der Skill nutzt **zwei Kanaele** zum Lesen von Quellen:

### Kanal 1: mcp-atlassian (Confluence)

Fuer alle Confluence-Inhalte wird `mcp-atlassian` verwendet — **nicht** Playwright.

| Aktion | Tool | Beschreibung |
|--------|------|--------------|
| Confluence durchsuchen (CQL) | `confluence_search` | Suche mit CQL-Query, z.B. `text ~ "Bordnetz" AND space = VOBES` |
| Confluence-Seite lesen (Page-ID) | `confluence_get_page` | Seiten-Inhalt per Page-ID abrufen |
| Confluence-Seite lesen (URL) | `confluence_get_page` | Page-ID aus URL extrahieren (`pageId=NNNN`), dann Inhalt abrufen |

**Confluence-URL-Erkennung:** Eine URL gilt als Confluence-Seite wenn sie `devstack.vwgroup.com/confluence` enthaelt.

**Page-ID-Extraktion aus URLs:**
- `...?pageId=1234567` → Page-ID = `1234567`
- `.../pages/1234567/Seitenname` → Page-ID = `1234567`
- `.../display/SPACE/Seitenname` → Per `confluence_search` mit CQL `title = "Seitenname" AND space = "SPACE"` aufloesen

**Bekannte Spaces (bevorzugt durchsuchen):**
- `VOBES` — VOBES-Hauptspace
- `VSUP` — VOBES Support
- `EKEK1` — EKEK/1 Abteilungsspace

**Fallback:** Falls `mcp-atlassian` einen Fehler liefert (Container nicht erreichbar, Auth-Fehler, Timeout) → auf `skill-browse-intranet` (Playwright) zurueckfallen. Fehler im Agenten-Hinweis dokumentieren.

### Kanal 2: skill-browse-intranet (alle anderen Seiten)

Fuer alle **Nicht-Confluence-Seiten** wird `skill-browse-intranet` verwendet:

| Aktion | Zustaendig |
|--------|-----------|
| URL oeffnen / navigieren | `skill-browse-intranet` |
| Suchfeld bedienen | `skill-browse-intranet` |
| Button / Link klicken | `skill-browse-intranet` |
| Seiteninhalt lesen / extrahieren | `skill-browse-intranet` |
| Screenshot erstellen | `skill-browse-intranet` |
| Formular ausfuellen | `skill-browse-intranet` |

### Verbotene Inhalte in dieser Skill-Datei

Diese SKILL.md darf **NICHT** enthalten:
- Playwright Tool-Aufrufe (`mcp_playwright_browser_*`)
- DOM-Selektoren oder CSS-Selektoren
- JavaScript-Ausfuehrungsanweisungen (`evaluate`, `querySelector`, etc.)
- Browser-spezifische Instruktionen (Warten auf Elemente, Tab-Wechsel, etc.)

Alle diese Aktionen gehoeren in `skill-browse-intranet`. Dieser Skill beschreibt nur **was** getan werden soll (welche Seite besuchen, was suchen, was extrahieren) — nicht **wie** der Browser bedient wird.

### Delegation laden

Vor der ersten Browser-Interaktion: `skill-browse-intranet` ueber den Standard-Skill-Dispatch laden.

---

## Sicherheits- und Betriebsregeln (FR-010, FR-015)

### Standardmodus: Read-Only

Der Skill arbeitet im **Read-Only-Modus**. Erlaubt sind ausschliesslich:
- Lesen
- Suchen
- Navigieren
- Extrahieren
- Dokumentieren

### Verbotene Aktionen

Folgende Aktionen sind **grundsaetzlich verboten**:
- Loeschaktionen
- Freigaben / Genehmigungen
- Stammdatenaenderungen
- Massenabsendungen
- Formular-Submissions (ausser explizit autorisiert)

### Ausnahmen

Explizite Interaktionen wie Formular absenden, Export anstoessen oder Download ausloesen sind **nur** erlaubt wenn:
1. Die Aktion zum Rechercheauftrag gehoert
2. Die Aktion **klar benannt** wird (welches Formular, welcher Export)
3. Sie nicht ueber das notwendige Mass hinausgeht

### Fehlerbehandlung bei unzugaenglichen Seiten (FR-015)

Falls eine Seite nicht erreichbar ist (Auth-Fehler, Timeout, 403/404):
1. **Fehler im Tracking dokumentieren** — Schritt mit Status `verworfen` und Grund
2. **Quelle als unzugaenglich notieren** im Agenten-Hinweis
3. **Mit den verbleibenden Leads fortfahren** — nicht abbrechen

---

## Crawl4AI Integration (OPTIONAL) (FR-011)

> **Hinweis:** Dieser Abschnitt ist **optional**. Der Skill ist ohne Crawl4AI voll funktionsfaehig und nutzt dann ausschliesslich `skill-browse-intranet` fuer alle Seitenbesuche.

### Wann verwenden?

- Recherchetiefe `deep` gewaehlt
- Breites Portal-Scanning benoetigt (z.B. "alle Erwaechnungen von X im Intranet")
- Viele potenzielle Seiten muessen schnell gesichtet werden

### Workflow

1. **Seed-URLs definieren** — aus dem Rechercheplan
2. **Crawl4AI ausfuehren** — Seed-URLs ablaufen, interne Links verfolgen
3. **Kandidaten priorisieren** — aus den gecrawlten Seiten die relevantesten auswaehlen
4. **Selektive Detailanalyse** — nur die Top-Kandidaten per `skill-browse-intranet` interaktiv untersuchen

### Fehlerbehandlung

Falls Crawl4AI fehlschlaegt (Timeout, Crash, Verbindungsfehler):
1. **Pausieren** und den User informieren
2. **Fragen:** Crawl erneut versuchen oder auf interaktives Browsing per `skill-browse-intranet` zurueckfallen?
3. Die Entscheidung des Users umsetzen

**Niemals** den Crawl-Fehler still ignorieren.

---

## Edge Cases

### 1. Alle Leads erschoepft ohne befriedigende Antwort
→ Trotzdem einen Abschlussbericht erstellen. Dokumentieren: was gesucht wurde, was nicht gefunden wurde, alternative Ansaetze vorschlagen.

### 2. Seite erfordert Authentifizierung oder liefert Fehler
→ Fehler im Tracking loggen, Quelle als unzugaenglich notieren, mit verbleibenden Leads fortfahren.

### 3. Widerspruechliche Evidenz
→ Widersprueche **explizit kennzeichnen** in der Evidenzsammlung und im Abschlussbericht hervorheben. Belastbarere Quelle bevorzugen, beide dokumentieren.

### 4. Zu vage Recherchefrage
→ **Vor Beginn der Recherche** den User um Klaerung bitten. Keine unfokussierten Suchen starten.

### 5. Fruehe vollstaendige Antwort
→ Stop-Kriterien greifen: Wenn ausreichend Evidenz vorhanden, Recherche **frueh beenden** statt alle geplanten Leads abzuarbeiten.

### 6. Doppelte URL als Lead
→ Per `visited_urls`-Tracking erkennen und ueberspringen. Lead als `rejected` markieren (Duplikat).

### 7. Crawl4AI-Fehler waehrend Recherche
→ Pausieren, User informieren, Retry oder Fallback auf interaktives Browsing anbieten.

### 8. Playwright MCP nicht verfuegbar
→ MCP-Verfuegbarkeit **vor Start** pruefen (siehe Voraussetzungen). Fehlt nur Playwright aber mcp-atlassian ist da → nur Confluence-Leads abarbeiten, Nicht-Confluence-Leads als `rejected` markieren und User warnen. Fehlen **beide** MCP-Server → sofortiger Abbruch.

### 8a. mcp-atlassian nicht verfuegbar
→ Warnung ausgeben. Confluence-Leads per Playwright/`skill-browse-intranet` abarbeiten (Fallback). Recherche laeuft weiter, aber Confluence-Zugriff ist langsamer und weniger strukturiert.

### 9. User will Plan waehrend Recherche aendern
→ Inline-Korrekturen akzeptieren. Rechercheplan entsprechend anpassen. Vom aktuellen Stand **ohne Neustart** fortfahren.

### 10. User liefert zusaetzlichen Kontext/URLs nach
→ Als **hochprioritaere Leads** in den aktuellen Plan aufnehmen. Research Brief bei Bedarf ergaenzen.

### 11. Nur Audi-Quellen gefunden, keine VW-Quellen
→ Im Abschlussbericht **explizit darauf hinweisen**, dass keine VW-spezifischen Quellen gefunden wurden. Die Audi-Informationen als **nicht direkt uebertragbar** kennzeichnen. Empfehlung aussprechen, VW-spezifische Ansprechpartner (z.B. in EKEK/1 oder der zustaendigen VW-Fachabteilung) zu kontaktieren, um die Gueltigkeit fuer VW zu klaeren.
