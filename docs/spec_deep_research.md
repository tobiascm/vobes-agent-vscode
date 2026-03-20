# Spezifikation: `skill-deep-research`

> **Hinweis**: Dieses Dokument ist das urspruengliche Input-Dokument. Die formale, fuehrende Spezifikation liegt unter `specs/001-docs-spec-deep/spec.md`. Bei Abweichungen gelten die speckit-Dokumente.

## 1. Ziel

Es soll ein neuer Skill `skill-deep-research` entstehen, der **umfangreiche, mehrstufige Recherchen** über mehrere Webseiten und interne Quellen orchestriert.

Der Skill soll **nicht** nur eine einzelne Seite öffnen und lesen, sondern:

- eine Fragestellung systematisch untersuchen
- mehrere Websites / Portale / Unterseiten nacheinander abarbeiten
- Zwischenergebnisse verdichten
- Recherchepfade priorisieren
- Fundstellen und Belege sammeln
- den Suchweg transparent dokumentieren
- am Ende eine belastbare Antwort mit Evidenz liefern

Der bestehende Skill `skill-browse-intranet` bleibt dabei die Basis für **konkrete Browser-Interaktionen** auf einzelnen Seiten.

---

# 2. Ausgangslage

Es existiert bereits ein Skill `skill-browse-intranet`, der für einzelne Interaktionen mit Webseiten geeignet ist, insbesondere:

- Webseite öffnen
- warten
- Snapshot lesen
- klicken
- Suchfelder bedienen
- Text eingeben
- JavaScript ausführen
- Screenshots erstellen
- Tabs handhaben
- Login-/Session-Situationen im Browserkontext mitnutzen

Dieser Skill ist **Single-Page-/Single-Step-orientiert**.

Darauf aufbauend soll `skill-deep-research` als **Meta-Skill / Orchestrierungs-Skill** entstehen.

---

# 3. Abgrenzung

## 3.1 Was `skill-deep-research` leisten soll

- Rechercheauftrag strukturieren
- Suchstrategie ableiten
- mehrere Recherchezyklen durchführen
- Suchpfade steuern
- Fundstellen bewerten
- Widersprüche markieren
- Evidenz sammeln
- Abschlussbericht erstellen
- Suchweg in einer Tracking-Datei protokollieren

## 3.2 Was `skill-deep-research` nicht leisten soll

- Playwright-/Browser-Details duplizieren
- bestehende Einzelseitenlogik neu implementieren
- alle Browser-Tools selbst beschreiben
- pauschal Schreibaktionen ausführen
- site-spezifische Speziallogik mehrfach pflegen

## 3.3 Rolle von `skill-browse-intranet`

`skill-browse-intranet` bleibt zuständig für:

- konkrete Webseiteninteraktion
- Navigation auf Einzelseiten
- Eingabe in Suchfelder / Formulare
- Klicks
- Snapshots
- Screenshots
- Lesen sichtbarer Inhalte
- DOM-/JS-basierte Extraktion

---

# 4. Kernanforderungen

## 4.1 Funktionale Anforderungen

### F1 — Research Brief erzeugen

Der Skill soll aus der Nutzerfrage einen strukturierten Rechercheauftrag ableiten.

Enthalten sein sollen mindestens:

- Fragestellung
- Ziel der Recherche
- bekannte Startquellen
- vermutete Systeme/Portale
- Suchbegriffe
- alternative Schreibweisen / Synonyme / Abkürzungen
- Ausschlüsse / Grenzen
- gewünschtes Ausgabeformat

---

### F2 — Rechercheplan erzeugen

Vor der eigentlichen Recherche soll ein Plan erzeugt werden mit:

- priorisierten Startpunkten
- initialen Suchbegriffen
- alternativen Suchpfaden
- Stop-Kriterien
- Priorisierungslogik für Folgepfade

---

### F3 — Iterative Recherche durchführen

Die Recherche soll in Schleifen erfolgen.

Jede Schleife umfasst mindestens:

1. nächsten Lead auswählen
2. Quelle/Website öffnen
3. relevante Seite / Suchfunktion bedienen
4. Inhalt lesen / extrahieren
5. Fundstellen bewerten
6. neue Leads ableiten
7. Status aktualisieren

---

### F4 — Evidenz erfassen

Jede relevante Fundstelle soll strukturiert erfasst werden.

Mindestens:

- Titel
- URL
- Quellsystem / Portal
- Kurzbeschreibung
- relevante Fakten
- Relevanz für die Frage
- Vertrauensgrad
- Stand / Datum, falls sichtbar
- Notizen
- mögliche Widersprüche

---

### F5 — Tracking-Markdown führen

Es soll eine **laufend aktualisierte Markdown-Datei** geben, die den Suchweg dokumentiert.

Diese Datei soll insbesondere sichtbar machen:

- welche Websites / Seiten analysiert wurden
- in welcher Reihenfolge
- warum die Seite besucht wurde
- was der Agent dort vermutet / gesucht hat
- was gefunden wurde
- ob daraus Folgepfade entstanden sind
- ob die Quelle verworfen oder weiterverfolgt wurde

Diese Datei dient der **Transparenz des Recherchepfads**.

---

### F6 — Abschlussbericht erzeugen

Nach der Recherche soll der Skill ein strukturiertes Ergebnis liefern mit:

- Kurzantwort
- wichtigste Erkenntnisse
- Evidenz / Fundstellen
- Unsicherheiten / Widersprüche
- offene Fragen
- ggf. nächste sinnvolle Schritte

---

## 4.2 Nichtfunktionale Anforderungen

### N1 — Read-first-Prinzip

Standardmäßig soll der Skill nur:

- lesen
- suchen
- navigieren
- extrahieren
- dokumentieren

Schreib-/Aktionsschritte nur, wenn sie explizit nötig und erlaubt sind.

---

### N2 — Saubere Delegation

`skill-deep-research` soll konkrete Webseitenaktionen an `skill-browse-intranet` delegieren, statt Browserlogik zu duplizieren.

---

### N3 — Transparenz

Die Recherche muss über Tracking-Datei und Abschlussbericht nachvollziehbar sein.

---

### N4 — Wiederholbarkeit

Die Recherchelogik soll so aufgebaut sein, dass spätere Erweiterungen für Persistenz / Resume / thematische States möglich sind.

---

### N5 — Redundanzvermeidung

Bereits besuchte URLs, ausgeführte Suchbegriffe und verworfene Pfade sollen berücksichtigt werden, um Endlosschleifen und nutzlose Wiederholungen zu vermeiden.

---

# 5. Lösungsidee

## 5.1 Architekturidee

`skill-deep-research` wird als **Recherche-Orchestrierungs-Skill** definiert.

Er nutzt:

- `skill-browse-intranet` für konkrete Browserinteraktionen
- interne Zustandsobjekte für Plan, Leads, Evidenz und Tracking
- ein festes Ausgabeformat für Zwischen- und Endergebnisse

## 5.2 Grundprinzip

Nicht:

> „Öffne Seite X und lies sie“

Sondern:

> „Bearbeite die Frage in mehreren Recherchezyklen und nutze Seite X nur als einen Schritt im Gesamtablauf“

---

# 6. Recherchemodell

## 6.1 Phase A — Research Brief

Aus der Nutzerfrage wird ein strukturierter Brief erzeugt.

### Beispielstruktur

topic:  

goal:  

known_start_urls: []  

candidate_systems: []  

search_terms: []  

synonyms: []  

constraints: []  

desired_output:  

depth:

---

## 6.2 Phase B — Rechercheplan

Erzeugt einen initialen Arbeitsplan.

### Beispiel

plan:

- priority: 1

lead_type: portal_search  

target: "Intranet-Startsuche"  

reason: "breiter Einstieg"

- priority: 2

lead_type: known_system  

target: "Fachportal A"  

reason: "wahrscheinlich Primärquelle"

- priority: 3

lead_type: documentation  

target: "Wiki / SharePoint / Doku"  

reason: "sekundäre Bestätigung"

---

## 6.3 Phase C — Iterativer Research Loop

### Jeder Loop beantwortet intern mindestens:

- Was suche ich gerade?
- Warum ist dieser Pfad relevant?
- Was habe ich gefunden?
- Ist die Quelle belastbar?
- Welche Folgepfade ergeben sich?
- Ist weiterer Aufwand auf dieser Seite sinnvoll?

---

## 6.4 Phase D — Evidenzkonsolidierung

Erkannte Fundstellen werden gesammelt und bewertet.

### Vertrauensstufen

- **A** = offizielle Primärquelle / führendes System
- **B** = offizielle interne Sekundärquelle / Fachseite / Wiki
- **C** = abgeleitete oder indirekte Quelle
- **D** = schwacher Hinweis / unbestätigt

---

## 6.5 Phase E — Abschlussbericht

Strukturierte Ausgabe am Ende der Recherche.

---

# 7. Tracking-Markdown

## 7.1 Ziel

Die Tracking-Datei soll den **Suchweg des Agenten sichtbar machen**.

Sie ist nicht nur Log, sondern ein **menschlich lesbares Research Journal**.

## 7.2 Inhalt

Sie soll nacheinander für jede analysierte Seite mindestens enthalten:

- Zeitpunkt / Reihenfolge
- Website / URL
- Grund für den Besuch
- Suchfrage / Hypothese des Agenten
- was dort konkret geprüft wurde
- Ergebnis
- Einschätzung der Relevanz
- nächste abgeleitete Schritte
- Status: weiterverfolgt / abgeschlossen / verworfen

## 7.3 Wunsch gemäß deiner Anforderung

Zusätzlich soll dort auch ein kurzer **Gedanke des Agenten zur Website** stehen, damit der Suchweg und die Denkspur sichtbar bleiben.

Wichtig: Das sind **arbeitsbezogene Recherchegedanken**, keine versteckte interne Chain-of-Thought.  

Also eher:

- „Diese Seite wirkt wie eine Übersichtsseite, nicht wie die Primärquelle.“
- „Hier gibt es einen Link auf ein möglich relevantes Exportportal.“
- „Suchbegriff A liefert nur veraltete Treffer; Synonym B scheint besser.“

Nicht erwünscht wären unstrukturierte oder endlose freie Gedanken.

## 7.4 Vorschlag für Format

# Deep Research Tracking

## Research Brief

- Thema:  
- Ziel:  
- Startpunkte:  
- Suchbegriffe:  
- Ausschlüsse:

## Verlauf

### Schritt 1

- URL:  
- Quelle/Portal:  
- Grund:  
- Agenten-Hinweis:  
- Aktion:  
- Gefunden:  
- Relevanz:  
- Vertrauensgrad:  
- Folgepfade:  
- Status:

### Schritt 2

...

## 7.5 Ausgabedateien (V1)

V1 verwendet **zwei Dateien**:

- `research_tracking.md` — lesbarer Suchweg (Research Journal)
- `research_report.md` — konsolidierter Abschlussbericht mit Evidenz

---

# 8. Datenmodell

## 8.1 Research Brief

topic:  

goal:  

known_start_urls: []  

candidate_systems: []  

search_terms: []  

synonyms: []  

constraints: []  

output_format:  

depth:

## 8.2 Research State

visited_urls: []  

visited_queries: []  

pending_leads: []  

completed_leads: []  

rejected_leads: []  

evidence_items: []  

open_questions: []  

working_hypotheses: []  

tracking_entries: []

## 8.3 Lead

id:  

kind: portal_search | url | document | page | export_path  

label:  

source:  

priority:  

reason:  

status: pending | in_progress | done | rejected

## 8.4 Evidence Item

id:  

title:  

url:  

source_system:  

summary:  

key_facts: []  

confidence: A | B | C | D  

timestamp_hint:  

notes:  

contradictions: []

## 8.5 Tracking Entry

step_no:  

url:  

source_system:  

reason_for_visit:  

agent_note:  

actions_taken: []  

observations: []  

relevance:  

confidence:  

derived_leads: []  

status:

---

# 9. Entscheidungslogik

## 9.1 Lead-Priorisierung

Ein Lead soll bevorzugt werden, wenn:

- er auf eine Primärquelle hindeutet
- er hohe thematische Relevanz hat
- er neue Information verspricht
- er von mehreren Quellen indirekt bestätigt wird
- er zu konkreten Unterseiten / Dokumenten führt

## 9.2 Lead-Abwertung

Ein Lead soll zurückgestuft werden, wenn:

- er redundant ist
- nur schwache oder veraltete Hinweise liefert
- keine neuen Informationen bringt
- nur auf allgemeine Übersichtsseiten führt

## 9.3 Stop-Kriterien

Recherche kann beendet werden, wenn:

- die Frage belastbar beantwortet ist
- keine hochwertigen neuen Leads mehr entstehen
- weitere Schritte nur Redundanz erzeugen
- nur noch schwache Quellen verbleiben

---

# 10. Standard-Ausgabeformat

## 10.1 Zwischenstand

Bei längeren Recherchen kann ein Zwischenstand in dieser Form ausgegeben werden:

## Zwischenstand

### Bisher belastbar

- ...

### Noch offen

- ...

### Aktuell verfolgter Pfad

- ...

### Nächster sinnvoller Schritt

- ...

## 10.2 Endausgabe

## Kurzantwort

...

## Wichtigste Erkenntnisse

- ...  
- ...

## Evidenz / Fundstellen

- [A] Titel – URL – Kernaussage  
- [B] Titel – URL – Kernaussage

## Unsicherheiten / Widersprüche

- ...  
- ...

## Offene Punkte

- ...

## Tracking-Datei

- Verweis auf den dokumentierten Suchweg

---

# 11. Sicherheits- und Betriebsregeln

## 11.1 Standardmodus

Default ist:

- read-only
- keine irreversiblen Aktionen
- keine Massenaktionen
- keine Datenänderungen

## 11.2 Ausnahmen

Explizite Interaktion wie:

- Formular abschicken
- Export anstoßen
- Download auslösen

nur dann, wenn:

- dies zum Rechercheauftrag gehört
- die Aktion klar benannt ist
- sie nicht über das notwendige Maß hinausgeht

## 11.3 Guardrails

- keine Löschaktionen
- keine Freigaben / Genehmigungen
- keine Stammdatenänderungen
- keine Massenabsendungen

---

# 12. Konkreter Umsetzungsplan

## Phase 1 — Spezifikation / Skill-Design

Erstellen von `skill-deep-research` mit:

- Zweck
- Triggern
- Nicht-Zielen
- Workflow
- Delegationsregeln
- Ausgabeformat
- Tracking-Regeln

## Phase 2 — Mindestfähiger Skill

Implementieren / Formulieren eines Skills, der:

- Research Brief erzeugt
- Rechercheplan erzeugt
- Recherche iterativ strukturiert
- Tracking-Markdown fordert/pflegt
- Abschlussbericht erzeugt

## Phase 3 — Qualitätsverbesserung

- bessere Priorisierungslogik
- Relevanz-/Vertrauensheuristik
- Redundanzvermeidung
- sauberere Tracking-Struktur

## Phase 4 — Spätere Erweiterungen

- Persistenz / Resume
- thematische Research-States
- zusätzliche Crawl-/Index-Backends
- getrennte Evidence-Datei
- breitere Multi-Source-Recherche

---

# 13. Akzeptanzkriterien

Der Skill gilt als fachlich passend, wenn:

## A

Er bei einer komplexen Recherchefrage **nicht sofort in Einzelklicks springt**, sondern zuerst einen strukturierten Rechercheauftrag formuliert.

## B

Er **mehrere Recherchezyklen** über unterschiedliche Seiten / Portale durchführen kann.

## C

Er jede relevante Fundstelle als Evidenz dokumentiert.

## D

Er eine **Tracking-Markdown-Datei** mit dem Suchweg und kurzen Agenten-Hinweisen zur jeweils analysierten Website pflegt.

## E

Er konkrete Webseiteninteraktion nicht selbst neu beschreibt, sondern an `skill-browse-intranet` delegiert.

## F

Er am Ende eine belastbare, strukturierte Zusammenfassung mit Unsicherheiten liefert.

---

# 14. Designentscheidungen (entschieden)

## O1 — Zwei Dateien fuer V1

Entschieden: V1 verwendet zwei Dateien — `research_tracking.md` (Suchweg) und `research_report.md` (Abschlussbericht mit Evidenz).

## O2 — Tracking-Granularitaet

Entschieden: Ein Eintrag pro bedeutendem Recherche-Schritt bzw. analysierter Seite.

## O3 — Persistenz

Entschieden: Out of scope fuer V1. Das Design soll Persistenz jedoch nicht ausschliessen.

## O4 — Umfang der Agenten-Hinweise

Entschieden: Kurz, arbeitsbezogen, 1–2 Saetze pro Eintrag.

---

# 15. Empfehlung

## Empfohlene Zielentscheidung

`skill-deep-research` wird als **Meta-Skill zur Recherche-Steuerung** gebaut.  

Er verwendet `skill-browse-intranet` als Ausführungs-Skill für konkrete Webseitenarbeit.

Zusätzlich wird eine **Tracking-Markdown-Datei** eingeführt, damit der Recherchepfad transparent sichtbar bleibt.

Das ist die sauberste, wartbarste und für dein bestehendes Setup passendste Lösung.

---

# TL;DR

`skill-deep-research` soll ein **Orchestrierungs-Skill** sein, nicht ein zweiter Browser-Skill.  

Er soll:

- Recherchefragen strukturieren
- mehrere Seiten/Portale systematisch abarbeiten
- Evidenz sammeln
- Widersprüche markieren
- einen Abschlussbericht erstellen
- und zusätzlich eine **Tracking-Markdown-Datei** führen, in der alle analysierten Websites samt kurzem Agenten-Hinweis zum Suchweg dokumentiert werden.

Im nächsten Schritt kann ich daraus direkt eine **fertige `SKILL.md`-Datei** für `skill-deep-research` machen.  


# Externe Repos

## 1) **Crawl4AI: ja, aktiv verwenden**

Das würde ich **wirklich einbauen**.

Warum:  

Crawl4AI ist genau für den Teil stark, der dir bei `browser-use` zu langsam ist: **großflächiges Sammeln, Deep Crawling, Adaptive Crawling, session-/identity-nahe Verarbeitung und LLM-taugliche Extraktion**. Die Doku nennt dafür explizit **Deep Crawling**, **Adaptive Crawling** und **Session Management** als Kernfunktionen.

## Wo genau kommt Crawl4AI hin?

### **Unterhalb von **`skill-deep-research`** als Crawl-/Discovery-Backend**

Also ungefähr so:

skill-deep-research  

├─ Research Brief / Plan / Tracking / Evidence  

├─ nutzt skill-browse-intranet für einzelne interaktive Seiten  

└─ nutzt Crawl4AI für breite Recherche über viele Seiten

### Konkrete Rolle von Crawl4AI

Crawl4AI übernimmt:

- Seed-URLs ablaufen
- interne Suchergebnisseiten oder Portale tiefer verfolgen
- relevante Unterseiten sammeln
- Inhalte extrahieren
- query-nahe / adaptive Linkverfolgung
- später optional: Vorfilterung für den Agenten

### Typischer Flow

Beispiel:

1. `skill-deep-research` erzeugt Suchbegriffe
2. Crawl4AI durchsucht Portal A / Bereich B
3. liefert 20–100 potenziell relevante Seiten
4. `skill-deep-research` priorisiert diese
5. nur die besten Kandidaten werden mit `skill-browse-intranet` interaktiv vertieft

**Das ist der wichtigste Performance-Hebel.**

---

## 2) **Open Deep Research: ja, aber eher indirekt / selektiv**

Das würde ich **nicht** blind als zentrales Hauptsystem einsetzen.

Warum:  
`open_deep_research` ist ein **vollständiger Deep-Research-Agent**, der laut Repo über viele Modellanbieter, Search-Tools und **MCP-Server** arbeiten kann. Die Referenzarchitektur ist klar **Scope → Research → Write**.

Das ist sehr gut — aber du hast schon:

- dein eigenes Skill-System
- `skill-browse-intranet`
- bestehende Projektlogik
- dein Intranet-/PKI-/Unternehmenskontext

Deshalb würde ich bei **V1** nicht das ganze Repo „in die Mitte“ setzen.

## Wo genau kommt Open Deep Research dann hin?

### **Primär als Architekturvorbild**

Ich würde daraus übernehmen:

- die **3-Phasen-Logik**
  - Scope
  - Research
  - Write
- die Trennung von:
  - Rechercheplanung
  - Rechercheausführung
  - Ergebnisbericht
- eventuell Ideen für:
  - Query-Verfeinerung
  - Kompression von Zwischenergebnissen
  - saubere Abschlussberichte

### **Optional später als austauschbare Orchestrator-Engine**

Wenn du später willst, könntest du `skill-deep-research` intern so bauen, dass ein Teil der Orchestrierung alternativ von Open Deep Research inspiriert oder teilweise ausgeführt wird.

Aber meine Empfehlung für **jetzt** ist:

- **Skill und Workflow selbst bauen**
- **Open Deep Research als Vorlage, nicht als Zwangsabhängigkeit**

Denn sonst bekommst du schnell doppelte Orchestrierung:

- einmal dein Skill
- einmal deren Agent-Loop

Das wird oft unnötig kompliziert.