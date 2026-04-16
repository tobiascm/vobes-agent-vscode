---
name: skill-outlook-termin
description: "Outlook-Termine und Teams-Besprechungen per lokalem Outlook COM erstellen, als Entwurf in den Kalender legen, spaeter senden, aktualisieren, verschieben, absagen und wiederfinden. Verwenden bei Anfragen wie Termin einstellen, Outlook-Termin anlegen, Teams-Besprechung erstellen, Termin verschieben, Einladung senden, Termin absagen oder Teilnehmer fuer einen Outlook-Termin aufloesen."
---

# Skill: Outlook Termin

Script: `.agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py`

## Standardverhalten

- Neue Termine standardmaessig als **echtes Outlook-Terminfenster** oeffnen, aber **nicht sofort speichern oder senden**
- Betreff im Review-Fenster standardmaessig mit Praefix `Entwurf: ` vorbelegen
- Bei explizitem Direktversand (`direkt senden`, `sofort senden`) per `--send-without-confirmation` direkt ohne finalen Entwurfs-Praefix senden
- Standardmaessig **Teams-Besprechung**
- Standardzeit normalisieren auf `:05` oder `:35`, wenn der Start auf `:00` oder `:30` liegt
- Standarddauer ohne explizites Ende:
  - normaler Termin: `55` Minuten
  - kurze Klaerungsfrage: `25` Minuten

## CLI

### Termin erstellen

```bash
python .agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py create ^
  --subject "Austausch 3DX / Wissensmanagement" ^
  --start "2026-04-17T14:00:00" ^
  --required "Frenzel, Clemens (E2DC/2)" ^
  --required "Junge, Christian (EKEK/1)"
```

Wichtige Optionen:

- `--end`: explizites Ende
- `--duration-min`: explizite Dauer statt Standarddauer
- `--short-clarification`: Standarddauer 25 Minuten
- `--optional`: optionaler Teilnehmer (mehrfach moeglich)
- `--body`: Termintext
- `--location`: Ort
- `--send-mode review|draft|send`: Default `review`
- `--send-without-confirmation`: Direkter Versand ohne Outlook-Review-Fenster
- `--teams` / `--no-teams`: Default `teams`

### Passende Slots finden

```bash
python .agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py suggest-slots ^
  --search-start "2026-04-17T09:00:00" ^
  --search-end "2026-04-17T18:00:00" ^
  --duration-min 60 ^
  --required "haupt1@firma.de" ^
  --required "haupt2@firma.de" ^
  --optional "teilnehmer1@firma.de" ^
  --subject "Abstimmung VOBES"
```

Wichtige Optionen:

- `--required`: Hauptperson (mehrfach moeglich). Alle `--required`-Teilnehmer muessen fuer den Slot frei oder tentative sein
- `--optional`: weiterer Teilnehmer (mehrfach moeglich). `busy` ist erlaubt, aber schlechter gerankt; `OOF` blockiert
- `--slot-minutes`: Raster fuer die Slot-Suche, Default `30`
- `--top-n`: Anzahl der zurueckgegebenen Slots, Default `10`
- `--working-hour-start` / `--working-hour-end`: Suchfenster innerhalb des Tages, Default `8` bis `18`
- `--include-weekends`: Wochenenden in die Suche einbeziehen
- `--no-shorter-slots`: Keine kuerzeren Alternativ-Slots (30 Min) anzeigen. Standardmaessig werden bei wenigen Treffern automatisch kuerzere Slots mit niedrigerem Score ergaenzt
- `--open-best-slot`: Oeffnet direkt ein Outlook-Terminfenster fuer den besten Slot
- `--prepare-best-slot-review`: Erstellt direkt fuer den besten Slot einen Review-Entwurf ueber `create --send-mode review`
- `--body`: Termintext fuer `--prepare-best-slot-review`
- `--location`: Ort fuer `--prepare-best-slot-review`
- `--teams` / `--no-teams`: Default `teams`; wirkt bei `--prepare-best-slot-review`

Bewertungslogik:

- Eigener Kalender:
  - frei / tentative = beste Prioritaet
  - Termin ohne Kategorie = erlaubt
  - Betreff enthaelt `Blocker` = erlaubt
  - Betreff enthaelt `Rücksprache` = erlaubt, aber ungern; bei EKEK/1-Mitarbeitern (Vorname im Betreff) wird geprueft ob die Ruecksprache in derselben Woche verschoben oder auf 30 min gekuerzt werden kann — verschiebbare Ruecksprachen erhalten Score-Bonus (+15). Die JSON-Ausgabe enthaelt `ruecksprache_moves` mit `entry_id`, `proposed_start`, `proposed_end`. Bei User-Bestaetigung: `update_appointment(entry_id=..., start=proposed_start, end=proposed_end)` aufrufen.
  - alles andere = blockiert
- Teilnehmer:
  - Hauptpersonen (`--required`) muessen fuer den kompletten Slot frei oder tentative sein
  - weitere Teilnehmer (`--optional`) duerfen busy sein, der Slot wird dann schlechter bewertet und als Rueckfrage-Fall markiert
  - `OOF` ist fuer alle Teilnehmer ein Blocker
  - `Working Elsewhere` und sonstige unbekannte Free/Busy-Zustaende werden als frei behandelt

### Bestehenden Termin verschieben und neue Slots suchen

```bash
python .agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py suggest-slots ^
  --source-entry-id "ENTRY_ID" ^
  --search-start "2026-04-17T09:00:00" ^
  --search-end "2026-04-25T18:00:00" ^
  --prepare-best-slot-review
```

Wichtige Optionen:

- `--source-entry-id`: bestehender Outlook-Termin, dessen Dauer und Teilnehmer standardmaessig uebernommen werden
- `--store-id`: optional bei Bedarf fuer `GetItemFromID`
- explizite `--required` / `--optional` ueberschreiben die aus dem Quelltermin uebernommenen Teilnehmer
- der Quelltermin wird bei der Slot-Suche automatisch ignoriert, damit er sich nicht selbst blockiert
- bei `--prepare-best-slot-review` wird der erzeugte Termin weiterhin nach dem `:05`/`:35`-Standard normalisiert

### Vorbereiteten Termin direkt senden

```bash
python .agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py send --entry-id "ENTRY_ID"
```

### Termin aktualisieren

```bash
python .agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py update ^
  --entry-id "ENTRY_ID" ^
  --start "2026-04-17T15:00:00"
```

### Termin absagen

```bash
python .agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py cancel --entry-id "ENTRY_ID"
```

### Termin suchen

```bash
python .agents/skills/skill-outlook-termin/scripts/outlook_appointment_tools.py search ^
  --start-from "2026-04-17T00:00:00" ^
  --start-to "2026-04-18T00:00:00" ^
  --subject "3DX"
```

## Workflow

1. Fehlende Kerndaten nur erfragen, wenn sie nicht ableitbar sind
2. Bei internen `EKEK/1`-/`EKEK`-/`VOBES`-Terminen, Gremiennamen oder nur teilweise genannten Personen zuerst `$skill-orga-ekek1` konsultieren, um Namen, Rollen, Regeltermine und Standardseiten sauber einzuordnen
3. Wenn zuerst ein passender Zeitpunkt gesucht werden soll, standardmaessig `suggest-slots` verwenden
4. Fuer neue Termine mit sicherem Zeitpunkt direkt `create --send-mode review`
5. Fuer bestehende Termine mit neuem Zeitslot `suggest-slots --source-entry-id ...` verwenden
6. Wenn der beste gefundene Slot direkt als Entwurf vorbereitet werden soll, `suggest-slots --prepare-best-slot-review` verwenden
7. Bei `direkt senden` oder `sofort senden` `create --send-without-confirmation`
8. Fuer spaetere Aenderungen oder Versand zuerst `search` oder bekannte `entry_id` verwenden
9. Bei Ambiguitaet bei Teilnehmern Termin nicht raten, sondern Rueckfrage ausloesen

## Hinweise

- Outlook muss lokal laufen und COM-Zugriff erlauben
- Teilnehmer werden zuerst ueber den lokalen Outlook-Adress-Cache aufgeloest
- Ist der Cache leer, wird automatisch ein Vollaufbau gestartet
- Gibt es einen Cache-Miss und der letzte erfolgreiche Lauf ist aelter als 1 Tag, wird automatisch ein inkrementeller Update-Lauf versucht
- Erst danach faellt die Aufloesung auf direkte Outlook-Resolve-/GAL-Methoden zurueck
- Wenn ein Name ueber Outlook allein nicht eindeutig ist, gibt das Script strukturierte Kandidaten zurueck
- Mehrere Hauptpersonen werden ueber mehrfaches `--required` uebergeben
- `suggest-slots` nutzt dieselbe Outlook-COM-/GAL-Basis wie die Termin-Erstellung; keine separate M365-/Graph-Abhaengigkeit
- Typische interne Trigger fuer `$skill-orga-ekek1` sind z. B. `Interne Fachthemen`, `PO-APO-Prio-Runde`, `VOBES FB-IT-Abstimmung` oder Teilnehmerangaben nur per Nachname/Rolle im `EKEK/1`-Umfeld
- `$skill-orga-ekek1` liefert nur den organisatorischen Kontext; die tatsaechliche Teilnehmeraufloesung bleibt bei Outlook/GAL oder bei einer Rueckfrage an den User
