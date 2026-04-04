---
name: skill-chatgpt-research
description: "Frage an ChatGPT stellen und Antwort als Markdown speichern. Bridge Mode via Playwright MCP ist Pflicht. Trigger: frage ChatGPT, ChatGPT Research, was sagt ChatGPT, schicke Frage an ChatGPT, ChatGPT antworten lassen."
---

# Skill: ChatGPT Research

Stellt eine Frage an **ChatGPT** via **Playwright MCP Bridge** und speichert die Antwort direkt als **Markdown-Datei**.

Der Standardweg ist **ein einziger Python-Aufruf**:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run --question "FRAGE" --thinking
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
- globalen Schutz gegen zu viele ChatGPT-Anfragen
- Login-/Textbox-Pruefung
- optional Aktivierung von **Laengeres Nachdenken**
- Prompt senden
- Antwort pollend auf Vollstaendigkeit pruefen
- Abschluss nur nach echtem Ruhefenster und Mindestinhalt erkennen
- bei Research-Laeufen bis zu **30 Minuten** auf die Antwort warten
- genau **einen** Prompt pro Lauf, ohne automatischen Follow-up
- minuetliche Mini-Statusmeldungen auf `stderr`
- HTML-Extraktion direkt neben der Markdown-Datei
- Markdown-Ausgabe nach `tmp/`
- minimales Ergebnis-JSON direkt auf `stdout`
- optionales explizites Schliessen des aktuellen ChatGPT-Tabs ueber eigenes `close`-Subcommand

Globaler Schutz:
- zwischen zwei neuen ChatGPT-Prompt-Submissions liegen mindestens **30 Sekunden**
- gilt prozess- und agentuebergreifend fuer diesen Workspace
- parallele Agenten warten automatisch auf ihren reservierten Slot

## Wann verwenden?

- User moechte eine **Frage an ChatGPT** stellen
- User moechte eine **ChatGPT-Antwort als Markdown** speichern
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

### 1. Schnellcheck

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py doctor
```

Erwartung:
- Bridge/MCP startet
- erforderliche Tools sind da
- ChatGPT-Seite ist erreichbar
- Textbox ist sichtbar

Wenn `doctor` mit Exit-Code `3` endet:
- User ist nicht eingeloggt oder die Chat-Seite zeigt keine Eingabebox

### 2. Recherche ausfuehren

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run \
  --question "FRAGE" \
  --thinking \
  --output tmp/DATEINAME.md
```

Wichtige Optionen:

| Option | Beschreibung |
|---|---|
| `--question/-q` | Pflichtfrage an ChatGPT |
| `--output/-o` | Ziel-MD-Datei |
| `--thinking` | versucht `Laengeres Nachdenken` zu aktivieren |
| `--quick` | Kurzantwort-Modus fuer Tests / kleine Antworten; schnellere Abschluss-Schwellen |
| `--reuse-chat` | bestehenden Chat weiterverwenden statt neuen Startzustand zu erzwingen |
| `--timeout-seconds` | Timeout pro Antwort, Standard: 1800 Sekunden = **30 Minuten** |
| `--completion-stable-seconds` | benoetigte Ruhezeit ohne Textaenderung vor Abschluss, Default: `15` |
| `--completion-min-chars` | Mindestlaenge fuer fruehen Abschluss ohne sichtbaren Generierungsindikator, Default: `200` |
| `--no-generation-grace-seconds` | Fallback-Wartezeit ohne Generierungsindikator, bevor ein stabiler Text trotzdem als fertig gilt, Default: `90` |

Wichtig:
- ChatGPT-Research kann je nach Last und Thema bis zu **30 Minuten** dauern.
- Der Agent wartet im Standardlauf entsprechend lange und bricht erst nach Ablauf dieses Timeouts mit Exit `4` ab.
- Ein kurzer Einleitungssatz gilt nicht mehr sofort als fertig; das Script wartet standardmaessig auf mindestens `15` Sekunden stabilen Inhalt und blockt sehr kurze Zwischenstaende.
- Im langen `--thinking`-Modus wird ein sichtbares `TL;DR`/`Fazit` zusaetzlich als starkes Abschluss-Indiz genutzt. Fehlt das, wartet der Wrapper deutlich laenger, bevor er einen stabilen Zwischenstand akzeptiert.
- Zusaetzlich injiziert der Wrapper standardmaessig ein Abschluss-Token `---fertig---`. Sobald dieses am Antwortende erscheint, kann der Lauf deutlich frueher und zuverlaessiger als abgeschlossen erkannt werden.
- Fuer kurze Testprompts oder 2-3 Zeilen Antwort `--quick` verwenden. Dann sind die Abschluss-Schwellen deutlich kuerzer und das Script beendet frueher, sobald der kurze Inhalt stabil ist.

Der Tab wird durch `run` **nie automatisch** geschlossen. Wenn keine Folgefrage mehr noetig ist, rufe danach explizit auf:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close
```

### 3. Outputs

Standardmaessig:
- Markdown: `tmp/YYYYMMDD_chatgpt_<slug>.md`
- Roh-HTML: gleiches Verzeichnis und gleicher Basisname wie Markdown, nur `.html`
- `stdout`: minimales JSON-Ergebnis

Das Ergebnis auf `stdout` ist absichtlich minimal:

```json
{
  "output_md": "tmp/DATEINAME.md",
  "output_chars": 6842,
  "raw_html_out": "tmp/DATEINAME.html"
}
```

## Fallback / Debug

Wenn der Ein-Kommandopfad klemmt, zuerst:

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

Falls der ChatGPT-Tab danach nicht mehr gebraucht wird:

```bash
python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close
```

## Fehlerbehandlung

| Problem | Erkennung | Loesung |
|---------|-----------|---------|
| Bridge/MCP nicht startbar | Exit `2` | VS Code MCP / Extension / Token pruefen |
| Nicht eingeloggt | Exit `3` | User in `chatgpt.com` einloggen |
| `Target page, context or browser has been closed` | Fehler-JSON / `stderr` | Script versucht einmal automatisch zu resetten |
| Antwort-Timeout | Exit `4` | hoehere `--timeout-seconds` oder Seite manuell pruefen |
| HTML unbrauchbar | Exit `6` | Roh-HTML und JSON-Fehler pruefen |
| Tab soll geschlossen werden | `close` | `python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close` |
