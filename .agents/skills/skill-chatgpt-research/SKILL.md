---
name: skill-chatgpt-research
description: "Frage an ChatGPT stellen und Antwort als Markdown speichern. Bridge Mode via Playwright MCP ist Pflicht. Trigger: frage ChatGPT, ChatGPT Research, was sagt ChatGPT, schicke Frage an ChatGPT, ChatGPT antworten lassen."
---

# Skill: ChatGPT Research

Stellt eine Frage an **ChatGPT** via **Playwright MCP Bridge** und speichert die Antwort direkt als **Markdown-Datei**.

Der Standardweg ist **ein einziger Python-Aufruf**:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run --question "FRAGE"
```

Fuer eine Frage **mit Datei-Upload**:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run \
  --question "Analysiere diese Datei" \
  --file /pfad/zur/datei.txt
```

Fuer eine Frage **mit Source-Bundle** (Quellcode + Configs hochladen):

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run \
  --question "Analysiere die Architektur" \
  --source-bundle
```

Fuer eine Frage **mit Source-Bundle inkl. Tests**:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run \
  --question "Pruefe die Testabdeckung" \
  --source-bundle --with-tests
```

Fuer ein **selektives Bundle** (nur bestimmte Dateien, hybrid mode):

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run \
  --question "Vergleiche diese beiden Dateien" \
  --source-bundle --includes "AGENTS.md,CLAUDE.md"
```

`--source-bundle` und `--file` sind kombinierbar (Bundle + zusaetzliche Datei).

Fuer einen bestehenden Chat, der **nur gelesen** und als Markdown gespeichert werden soll:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py read-chat \
  --chat-url "https://chatgpt.com/c/CHAT-ID"
```

Nur die **letzte ChatGPT-Ausgabe** statt des kompletten Chats:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py read-chat \
  --chat-url "https://chatgpt.com/c/CHAT-ID" \
  --last-output
```

Fuer eine echte Folgefrage im zuletzt erfolgreichen Chat:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run --question "FOLGEFRAGE" --follow-up
```

Zum expliziten Aufraeumen danach:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close
```

Der Agent soll dabei **nur diesen Python-Aufruf** verwenden:
- kein direkter MCP-Tool-Aufruf
- kein manueller Snapshot-Schritt
- kein manuelles `evaluate()`

Das Script uebernimmt:
- Start des Playwright MCP Servers im **Bridge Mode**
- Navigation zu `https://chatgpt.com/`
- optional Wiederaufnahme des zuletzt erfolgreichen konkreten Chat-URLs fuer echte Folgefragen
- globalen Schutz gegen zu viele ChatGPT-Anfragen
- Login-/Textbox-Pruefung
- Aktivierung von **Laengeres Nachdenken** als festem Run-Standard
- Readiness-Loop bis die Texteingabe wirklich wieder verfuegbar ist
- Prompt senden
- Antwort pollend auf Vollstaendigkeit pruefen
- bestehende Chats read-only oeffnen und den sichtbaren Verlauf exportieren
- Abschluss nur nach echtem Ruhefenster und Mindestinhalt erkennen
- bei Research-Laeufen bis zu **30 Minuten** auf die Antwort warten
- genau **einen** Prompt pro Lauf, ohne automatischen Follow-up
- auf `stdout` klare Schrittmeldungen wie `ChatGPT wird geöffnet...`, `Prompt abgeschickt...` und waehrend der Laufzeit `ChatGPT recherchiert noch, bitte warten...`
- HTML-Extraktion direkt neben der Markdown-Datei
- Markdown-Ausgabe nach `tmp/`
- menschenlesbare Abschluss-/Fehlermeldungen mit Verweis auf die Markdown-Datei
- automatisches Schliessen des verwendeten ChatGPT-Tabs nach jedem `run`
- optionales explizites Schliessen des aktuellen ChatGPT-Tabs ueber eigenes `close`-Subcommand

Globaler Schutz:
- zwischen zwei neuen ChatGPT-Prompt-Submissions liegen mindestens **30 Sekunden**
- gilt prozess- und agentuebergreifend fuer diesen Workspace
- parallele Agenten warten automatisch auf ihren reservierten Slot

## Wann verwenden?

- User moechte eine **Frage an ChatGPT** stellen
- User moechte eine **ChatGPT-Antwort als Markdown** speichern
- User gibt eine **ChatGPT-Chat-URL** vor und moechte den bestehenden Chat nur lesen
- Keywords: `frage ChatGPT`, `ChatGPT Research`, `was sagt ChatGPT`, `ChatGPT antworten lassen`

## Wann NICHT verwenden?

| Aufgabe | Stattdessen |
|---------|-------------|
| M365 Copilot fragen | `$skill-m365-copilot-chat` |
| Generische Webseite oeffnen | `$skill-browse-intranet` |
| Bordnetz/VOBES-Wissensfragen | `$skill-knowledge-bordnetz-vobes` |

## Voraussetzungen

1. **Bridge Mode ist Pflicht**
2. **Playwright MCP Server** muss verfuegbar sein (`.vscode/mcp.json` -> `playwright`)
3. **Browser Extension** muss verbunden sein
4. User muss bei **chatgpt.com** im Browser eingeloggt sein
5. `python` mit Standardbibliothek reicht aus

## Standard-Workflow

> **⚠️ WARTEZEIT: Das Script kann bis zu 30 Minuten laufen.**
> Das ist normal – ChatGPT Research mit "Laengeres Nachdenken" braucht Zeit.
> Solange alle 30 Sekunden Statusmeldungen auf stdout erscheinen, arbeitet es korrekt.
> **NIEMALS vorzeitig mit `stop_powershell` abbrechen.**
> Das Script beendet sich selbst nach Ablauf des Timeouts (Exit `4`).
>
> Erwartete stdout-Sequenz:
> 1. `ChatGPT wird geöffnet...` (sofort)
> 2. `Prompt abgeschickt, warte auf Antwort (max 30 Min.)...` (nach 10-30s)
> 3. `ChatGPT recherchiert noch (0:30 / max 30 Min.), bitte warten...` (alle 30s)
> 4. `OK: Antwort gespeichert → tmp/...` (am Ende)

Der normale Ablauf ist **direkt `run`**. Ein separater `doctor`-Aufruf ist davor **nicht** vorgesehen, weil `run` den relevanten Preflight bereits selbst ausfuehrt:
- Bridge/MCP starten
- erforderliche Tools pruefen
- `chatgpt.com` oeffnen
- Login / Textbox pruefen
- Readiness der Eingabe abwarten

### 1. Recherche ausfuehren

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run \
  --question "FRAGE" \
  --output tmp/DATEINAME.md
```

### 1b. Bestehenden Chat read-only exportieren

Standard: **kompletter sichtbarer Chat** in chronologischer Reihenfolge.

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py read-chat \
  --chat-url "https://chatgpt.com/c/CHAT-ID" \
  --output tmp/DATEINAME.md
```

Nur die letzte ChatGPT-Antwort:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py read-chat \
  --chat-url "https://chatgpt.com/c/CHAT-ID" \
  --last-output \
  --output tmp/DATEINAME.md
```

Wichtig:
- Ohne `--last-output` wird der **komplette sichtbare Chat** exportiert.
- Mit `--last-output` wird **nur die letzte ChatGPT-Ausgabe** exportiert.
- Es wird **kein Prompt** abgeschickt.
- Der Markdown-Titel nutzt die bestehende Chat-Bezeichnung aus ChatGPT; falls diese nicht lesbar ist, wird auf die Chat-ID aus der URL zurueckgefallen.

Wichtige Optionen:

| Option | Beschreibung |
|---|---|
| `--question/-q` | Pflichtfrage an ChatGPT |
| `--output/-o` | Ziel-MD-Datei |
| `--follow-up` | stellt die Frage im zuletzt erfolgreichen konkreten Chat statt in einem neuen Chat |
| `--quick` | Kurzantwort-Modus fuer Tests / kleine Antworten; schnellere Abschluss-Schwellen |
| `--timeout-seconds` | Timeout pro Antwort, Standard: 1800 Sekunden = **30 Minuten** |
| `--completion-stable-seconds` | benoetigte Ruhezeit ohne Textaenderung vor Abschluss, Default: `15` |
| `--completion-min-chars` | Mindestlaenge fuer fruehen Abschluss ohne sichtbaren Generierungsindikator, Default: `200` |
| `--no-generation-grace-seconds` | Fallback-Wartezeit ohne Generierungsindikator, bevor ein stabiler Text trotzdem als fertig gilt, Default: `90` |

Wichtig:
- ChatGPT-Research kann je nach Last und Thema bis zu **30 Minuten** dauern.
- `run` arbeitet immer im Modus **Laengeres Nachdenken**.
- Vor dem Prompt wartet ein Readiness-Loop standardmaessig bis zu **30 Sekunden**, bis die Textbox wirklich wieder verfuegbar ist. Das ist besonders fuer lange bestehende Chats wichtig.
- Der Agent wartet im Standardlauf entsprechend lange und bricht erst nach Ablauf dieses Timeouts mit Exit `4` ab.
- Ein kurzer Einleitungssatz gilt nicht mehr sofort als fertig; das Script wartet standardmaessig auf mindestens `15` Sekunden stabilen Inhalt und blockt sehr kurze Zwischenstaende.
- Im Thinking-Modus wird ein sichtbares `TL;DR`/`Fazit` zusaetzlich als starkes Abschluss-Indiz genutzt. Fehlt das, wartet der Wrapper deutlich laenger, bevor er einen stabilen Zwischenstand akzeptiert.
- Zusaetzlich injiziert der Wrapper standardmaessig ein Abschluss-Token `---fertig---`. Sobald `---fertig---`, `---fertig` oder `--- fertig` am Antwortende erscheint, kann der Lauf deutlich frueher und zuverlaessiger als abgeschlossen erkannt werden.
- Fuer kurze Testprompts oder 2-3 Zeilen Antwort `--quick` verwenden. Dann sind die Abschluss-Schwellen deutlich kuerzer und das Script beendet frueher, sobald der kurze Inhalt stabil ist.

Der durch `run` verwendete ChatGPT-Tab wird nach dem Lauf automatisch geschlossen. Das explizite `close`-Subcommand brauchst du nur noch, wenn du einen separat offen gebliebenen Tab manuell schliessen willst:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close
```

### 2. Outputs

Standardmaessig:
- Markdown: `tmp/YYYYMMDD_chatgpt_<slug>.md`
- Roh-HTML: gleiches Verzeichnis und gleicher Basisname wie Markdown, nur `.html`
- waehrend `run` auf `stdout`: Schrittmeldungen wie `ChatGPT wird geöffnet...` oder bei `--follow-up` `Gespeicherter Chat wird geöffnet...`, dann `Prompt abgeschickt, warte auf Antwort (max 30 Min.)...` und danach alle 30 Sekunden `ChatGPT recherchiert noch (M:SS / max 30 Min.), bitte warten...`
- nach Erfolg auf `stdout`: menschenlesbarer `OK:`-Einzeiler mit Verweis auf die Markdown-Datei
- nach Fehler auf `stderr`: menschenlesbarer `Fehler:`-Einzeiler mit Verweis auf die vorgesehene Markdown-Datei

## Fallback / Debug

`doctor` ist nur fuer Diagnose gedacht, **nicht** fuer den normalen Ablauf vor `run`.
Nur verwenden, wenn der direkte `run`-Pfad fehlschlaegt und separat geklaert werden soll, ob Bridge, Tools oder Login funktionieren:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py doctor
```

Falls nur die Konvertierung wiederverwendet werden soll:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py convert tmp/DATEINAME.html \
  --question "FRAGE" \
  --output tmp/DATEINAME.md \
  --thinking
```

Falls ein ChatGPT-Tab separat manuell geschlossen werden soll:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close
```

Hinweis zu Folgefragen:
- `--follow-up` verwendet ausschliesslich die zuletzt erfolgreich gespeicherte konkrete Chat-URL aus `tmp/`.
- Wenn kein wiederverwendbarer letzter Chat gespeichert ist, bricht das Script mit einer klaren Fehlermeldung ab.

## Fehlerbehandlung

| Problem | Erkennung | Loesung |
|---------|-----------|---------|
| Bridge/MCP nicht startbar | Exit `2` | VS Code MCP / Extension / Token pruefen |
| Nicht eingeloggt | Exit `3` | User in `chatgpt.com` einloggen |
| `Target page, context or browser has been closed` | Fehlerzeile auf `stderr` | Script versucht einmal automatisch zu resetten |
| Antwort-Timeout | Exit `4` | hoehere `--timeout-seconds` oder Seite manuell pruefen |
| HTML unbrauchbar | Exit `6` | Roh-HTML und Fehlermeldung pruefen |
| Tab soll geschlossen werden | `close` | `python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close` |
