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
3. Fuer neue Termine standardmaessig `create --send-mode review`
4. Bei `direkt senden` oder `sofort senden` `create --send-without-confirmation`
5. Fuer spaetere Aenderungen oder Versand zuerst `search` oder bekannte `entry_id` verwenden
6. Bei Ambiguitaet bei Teilnehmern Termin nicht raten, sondern Rueckfrage ausloesen

## Hinweise

- Outlook muss lokal laufen und COM-Zugriff erlauben
- Teilnehmer werden zuerst ueber Outlook/GAL aufgeloest
- Wenn ein Name ueber Outlook allein nicht eindeutig ist, gibt das Script strukturierte Kandidaten zurueck
- Typische interne Trigger fuer `$skill-orga-ekek1` sind z. B. `Interne Fachthemen`, `PO-APO-Prio-Runde`, `VOBES FB-IT-Abstimmung` oder Teilnehmerangaben nur per Nachname/Rolle im `EKEK/1`-Umfeld
- `$skill-orga-ekek1` liefert nur den organisatorischen Kontext; die tatsaechliche Teilnehmeraufloesung bleibt bei Outlook/GAL oder bei einer Rueckfrage an den User
