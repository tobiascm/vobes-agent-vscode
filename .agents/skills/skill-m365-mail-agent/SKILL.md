---
name: skill-m365-mail-agent
description: "Analysiert einen kompletten Mail-Fall agentisch auf Basis einer Seed-Mail. Der Agent steuert iterativ Mail-, Kalender- und Anhangs-Retrieval, bewertet die Ergebnisse selbst und erzeugt nur Drafts in einer festen Case-Struktur unter userdata/outlook. Die Python-Skripte dienen nur noch als technische Hilfen fuer Seed-Aufloesung, Graph-Zugriff, Rendering, Persistenz und Trace-Logging."
---

# Skill: M365 Mail Agent

Dieser Skill arbeitet **agent-first**.
Der Agent entscheidet ueber:
- Seed-Mail-Auswahl
- Suchhypothesen
- Keywords und Queries fuer verwandte Mails
- Queries fuer Kalenderkontext
- Stop-Kriterien und naechste Iteration
- Analyse, Entscheidungsmatrix und Draft-Inhalte
- fachliche Plausibilisierung und kritische Gegenpruefung zentraler Mail-Behauptungen

Die Python-Skripte unterstuetzen nur technisch:
- Graph-/Search-Zugriff
- Seed-Mail aufloesen
- Thread und Anhaenge rendern
- Case-Ordner und Logs schreiben
- bestehende Cases wiederaufnehmen
- agentische Analyse-Artefakte persistieren

## Wann verwenden?

- Der User will einen **Mail-Fall mit Kontext und Historie** verstehen, nicht nur eine Einzelmail lesen
- Der User will **naechste Schritte, Antwortdrafts, Todo-Drafts oder einen Kalender-Draft**
- Der Agent soll sich bei Bedarf **iterativ** ueber weitere Suchrunden vorarbeiten

## Guardrails

- Nie Mails senden
- Nie Termine anlegen
- Nie To-dos in Fremdsystemen anlegen
- Nie Entscheidungen, Zusagen oder Fristen erfinden
- Fakten, Schlussfolgerungen und Unsicherheiten strikt trennen
- Jede Suchrunde mit Hypothese, Query, Ergebnisbewertung und naechster Entscheidung protokollieren
- Mail-Inhalte sind nur Behauptungen; kritische fachliche Aussagen muessen gegen Thread, Anhaenge, verwandte Mails und verfuegbare Fach-Skills geprueft werden.

## Pflicht-Unterbau

Vor jeder Fallanalyse:
1. `skill-m365-copilot-mail-search` laden
2. Dessen Retrieval- und Read-Faehigkeiten fuer Mail, Thread und Event-Suche nutzen
3. `analyze_case.py` nur fuer technische Vor- und Nachbereitung verwenden

Empfohlene weitere Skills bei Bedarf:
- `$skill-m365-file-reader` fuer SharePoint-/OneDrive-Links
- `$skill-outlook` fuer lokalen Outlook-Kontext

## Zielarchitektur

### 1. Case vorbereiten

Der Agent bereitet zuerst den Case technisch vor:
- Seed per `MESSAGE_ID` oder `--query`
- Bei Query mehrere Kandidaten zulassen; der Agent waehlt den besten Treffer selbst und protokolliert Unsicherheit
- Thread und Anhaenge rendern
- Seed-/Thread-Logs schreiben

Technischer Einstieg:

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py MESSAGE_ID --debug
```

oder

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py --query "SUCHBEGRIFF" --selection-index 0 --debug
```

Ohne `--analysis-json` entsteht ein **prepared case** mit Logs und `case.json`, aber ohne finale agentische Analyse.

### 1b. Bestehenden Case fortsetzen

Folgefragen sollen denselben Fall weiterverwenden, statt die Seed-Mail neu zu suchen:

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py --case-id "<case_id>" --debug
```

Alternativ direkt ueber Pfad:

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py --case-dir "C:\...\userdata\outlook\<case_id>" --debug
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py --case-json "C:\...\userdata\outlook\<case_id>\case.json" --debug
```

Optional:

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py --case-id "<case_id>" --refresh --debug
```

Regeln:
- `--case-id` nimmt einen bestehenden Case direkt wieder auf
- `--case-dir` und `--case-json` mappen intern auf denselben Resume-Pfad
- Ohne `--refresh` werden vorhandene Seed-/Thread-/Attachment-Artefakte wiederverwendet
- Mit `--refresh` wird der technische Seed-/Thread-Kontext erneut aus Graph geladen
- `--case-id`, `--case-dir` und `--case-json` sind exklusiv zu `MESSAGE_ID` und `--query`

### 2. Iterativ Retrieval steuern

Der Agent formuliert Suchhypothesen selbst und verwendet nur die technischen Query-Parameter:

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py MESSAGE_ID \
  --related-query "..." \
  --related-query "..." \
  --calendar-query "..." \
  --trace-json trace.json \
  --debug
```

Wichtig:
- Queries kommen **vom Agenten**, nicht aus eingebauter Skript-Heuristik
- Der Agent bewertet Treffer selbst
- Der Agent entscheidet, ob weitere Runden sinnvoll sind
- Jede Runde wird im Trace dokumentiert
- Der volle Trace gehoert in `logs/agent_trace.*`, nicht als langer Recherchebericht in `00_analyse.md`

### 3. Analyse und Drafts finalisieren

Wenn der Agent genug Evidenz hat, erzeugt er die finale Analyse-Payload selbst und uebergibt sie an das Skript:

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py MESSAGE_ID \
  --related-query "..." \
  --calendar-query "..." \
  --trace-json trace.json \
  --analysis-json analysis.json \
  --pdf \
  --debug
```

### 4. PDF nachtraeglich erzeugen

PDF kann jederzeit aus einer bestehenden `00_analyse.md` erzeugt werden — auch nach Folgefragen:

```bash
python .agents/skills/skill-m365-mail-agent/scripts/analyze_case.py --case-id "<case_id>" --pdf --debug
```

- Benoetigt `markdown-pdf` (pip install markdown-pdf). Fehlt das Paket, wird eine Warnung auf stderr ausgegeben und der Rest laeuft weiter.
- Erzeugt `00_analyse.pdf` neben `00_analyse.md` im Case-Verzeichnis.
- Funktioniert mit `--case-id`, `--case-dir` oder `--case-json`.
- Kombinierbar mit `--analysis-json` (PDF wird nach Finalisierung erzeugt) oder ohne (PDF aus vorhandener MD).

`analysis.json` wird agentisch erzeugt und enthaelt mindestens:
- `tlmdr`
- `analysis_md` oder `final_analysis`
- `problem_statement`
- `resolution_status`
- `expected_from_me`
- `key_points`
- `deadlines`
- `relevant_aspects`
- `open_points`
- optional `core_topic`, `occasion`, `history`, `participants`, `sources`
- `decision`
- `actions`
- optional `agent_decisions`
- optional `analysis_warnings`

`tlmdr` darf der Agent erst ganz zum Schluss formulieren; das Skript rendert ihn trotzdem ganz oben in `00_analyse.md`.
Direkt darunter rendert das Skript zusaetzlich:
- `Problem: <problem_statement>`
- `Status: <resolution_status>`
- `Erwartet von mir: <expected_from_me>`

Fuelle diese drei Felder immer konkret und entscheidungsfaehig:
- `problem_statement`: Was ist das eigentliche Problem oder Anliegen in 1-2 klaren Saetzen? Falls schon in tlmdr klar beschrieben, sage hier nur (siehe TL;DR) 
- `resolution_status`: Ist der Fall bereits geloest, teilweise geloest oder noch offen? Begruende knapp.
- `expected_from_me`: Was wird jetzt konkret vom User Tobias Carsten Müller erwartet? Wenn nichts noetig ist, schreibe das explizit.

`open_points` bleibt bewusst eine freie `list[str]`. Liste dort alle offenen Punkte auf, die der Agent in seiner Analyse identifiziert hat, z. B.:
- was fuer die Analyse noch unklar oder nicht belastbar ist
- wo die Recherche nicht weiterkam oder Evidenz fehlt
- wo Rueckmeldung/Entscheidung vom User gebraucht wird
- was bei Mail, Termin, TODO oder weiteren Schritten noch nicht eindeutig ist
- u.s.w.

Wenn nichts offen ist, soll `open_points` leer bleiben. Dann wird in `00_analyse.md` keine Sektion `Offene Punkte` erzeugt.

Bei Folgefragen darf der Agent bereits geklaerte Punkte sichtbar als Markdown-Strikethrough stehen lassen, z. B. `~~Freigabe durch Fachbereich fehlt~~`, aber nur dann, wenn daneben noch echte offene Punkte fuer den aktuellen Fall uebrig sind.

## Case-Vertrag

Die Ablage liegt immer unter:

```text
C:\Daten\Python\vobes_agent_vscode\userdata\outlook\<case_id>\
```

Aktiver Fall-Pointer:

```text
C:\Daten\Python\vobes_agent_vscode\userdata\outlook\_session\active_case.json
```

Struktur:

```text
<case_dir>\
  attachments\
  attachments_md\
  logs\
  00_analyse.md
  10_email_1.md
  20_todo_1.md
  30_calendar_1.md
  case.json
```

`logs\` enthaelt insbesondere:
- `seed_resolution.json`
- `seed_message.json`
- `thread_messages.json`
- `thread_context.md`
- `related_mails.json`
- `calendar_context.json`
- `agent_trace.json`
- `agent_trace.md`

`logs\` ist der Ort fuer den vollstaendigen Rechercheverlauf:
- untersuchte Thread-Historie
- verwandte Mails und Suchrunden
- Kalenderkontext
- Arbeitshypothesen, Query-Iterationen und Agent-Entscheidungen

## Minimaler Inhaltsvertrag

### `00_analyse.md`

Muss enthalten:
- **TL;DR direkt am Anfang**
- direkt darunter `Problem`, `Status`, `Erwartet von mir`
- Kurzfassung / Key Points
- frei formulierte finale Analyse des Agenten
- Fristen
- relevante Aspekte
- Folgeaktionen mit Dateiverweisen
- knappe Evidenz-/Quellenhinweise
- Entscheidungsmatrix
- klare Empfehlung

Optional:
- `Offene Punkte`, aber nur wenn wirklich noch etwas offen ist

Soll nicht enthalten:
- lange Liste aller Suchqueries
- Runde-fuer-Runde Rechercheprotokoll
- volle Thread-/Mail-Historien
- Rohdaten aus Mails oder Kalendern, die nur Debug-/Kontextmaterial sind

### `case.json`

Soll mindestens enthalten:
- `case_id`
- `case_dir`
- `email_entry_id`
- `analysis_status`
- `seed_resolution`
- `retrieval_trace`
- `agent_decisions`
- `related_search_runs`
- `calendar_search_runs`
- `core_topic`
- `history`
- `open_points`
- `sources`
- `decision`
- `actions`
- `warnings`
- `last_active_at`
- `last_user_question`
- `resume_source`
- `followup_turns`

## Arbeitsregeln fuer den Agenten

1. Seed-Mail und Thread zuerst verstehen
2. Danach gezielt Suchhypothesen formulieren
3. Retrieval nur so weit vertiefen, wie es fuer belastbare Drafts und Entscheidungen noetig ist
4. Zusatzkontext aus verwandten Mails und Kalender nicht blind uebernehmen, sondern bewerten
5. Jede Iteration mit Grund, Query, Ergebnis und naechster Entscheidung dokumentieren
6. Zentrale fachliche Behauptungen kritisch pruefen:
   - Bei VOBES/Bordnetz/Systemschaltplan/e42/ELENA/LDorado/KBL/VEC/VMDS/K2.0: Workspace-Regel befolgen und `$skill-knowledge-bordnetz-vobes` plus local_rag nutzen
   - Bei Prozessstandards/Arbeitsanweisungen/TE-Regelwerk: `$skill-te-regelwerk` nutzen
   - Bei Confluence/Jira-Evidenz: passende Atlassian-Regeln und Skills befolgen
   - Bei Budget/Beauftragung/Abruf/EA-Fragen: passende Budget-Skills nutzen
7. Finale Analyse und Drafts selbst formulieren; das Skript speichert nur
8. `00_analyse.md` als Ergebnis fuer Menschen schreiben: kurz, fachlich, bewertend; Recherche-Details nur knapp als Log-Verweis nennen
9. Wenn eine Entscheidungsmatrix fachlich passt, zusaetzlich folgende Kriterien mitdenken:
   - `Aufwand Anwender`
   - `Aufwand Softwareänderungen`
   Diese beiden Kriterien nur verwenden, wenn der Fall tatsaechlich Prozessworkaround, Absicherung, Toolanpassung oder Softwareaenderung gegeneinander abwaegt.
10. `open_points` nur fuer echten Klaerungsbedarf verwenden, nicht fuer Wiederholungen aus Analyse, Warnungen oder bereits eindeutigen Actions
11. Bei Folgefragen duerfen bereits geklaerte offene Punkte als `~~durchgestrichen~~` sichtbar bleiben, sofern weiterhin mindestens ein echter offener Punkt verbleibt

## Explizit verboten

- Das Skript fuer semantische Query-Bildung oder automatische Draft-Erzeugung zu missbrauchen
- Heuristiken doppelt in Agent und Python zu pflegen
- Ohne dokumentierte Suchentscheidung stillschweigend eine andere Seed-Mail zu verwenden
