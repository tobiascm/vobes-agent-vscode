Du bekommst zwei Eingaben:

1. **Bestehende Seite** — der aktuelle Inhalt der Confluence-Protokollseite (HTML oder Markdown).
2. **Transkript** — Bitte aus dem Termin <Termin> selbst beschaffen.

## Aufgabe

Arbeite das Transkript aus dem Termin in eine bestehende Confleunce Protkoll Seite ein und gib das **vollstaendige** aktualisierte Protokoll als Markdown aus.

## Regeln

### Stil

- **Kompakt, stenoartig.** Nur Fakten, praezise formuliert.
- Keine Verallgemeinerungen, keine vagen oder unpraezisen Formulierungen.
- Keine Fuellwoerter, keine Hoeflichkeitsfloskeln.

### Struktur

- Themen als `## Themen`, dann verschachtelte Aufzaehlungen:
  - L1: `- Thema (Verantwortlicher)`
  - L2: `  - Detail / Ergebnis`
  - L3: `    - Unter-Detail`
- **Einrueckungen der bestehenden Seite exakt beibehalten.** Keine Ebene darf flacher werden.
- Ergaenzungen duerfen weitere Einrueckungsebenen nutzen.
- Neue Themen ans Ende des Themenblocks anfuegen.
- Bestehende Inhalte NICHT loeschen oder umformulieren, nur ergaenzen.

### TODOs / Massnahmen

- TODOs gehoeren als Unterpunkt **direkt zum jeweiligen Thema**, NICHT in einen separaten Abschnitt.
- Format:
  ```
  - [ ] @[userkey:xxx] Aufgabentext (bis YYYY-MM-DD) <!-- task id=N status=incomplete -->
  ```
- Falls kein konkretes Datum genannt wird, schlage den naechsten Regeltermin vor.
- `task-id` fortlaufend ab der hoechsten vorhandenen ID weiterzaehlen.
- Bestehende Tasks NICHT loeschen oder aendern.

### Markdown-Annotationen (Confluence-kompatibel)


| Element                      | Markdown                                                                       |
| ---------------------------- | ------------------------------------------------------------------------------ |
| Task (offen)                 | `- [ ] Text <!-- task id=N status=incomplete -->`                              |
| Task (erledigt)              | `- [x] Text <!-- task id=N status=complete -->`                                |
| Person                       | `@[userkey:xxx]`                                                               |
| Faelligkeitsdatum            | `(bis YYYY-MM-DD)`                                                             |
| Haekchen-Emoticon            | ✅                                                                              |
| Warnung-Emoticon             | ⚠️                                                                             |
| Kreuz-Emoticon               | ❌                                                                              |
| Seitenlink                   | `[[Seitentitel]]`                                                              |
| Unbekannte Confluence-Makros | `<!-- confluence:raw -->...<!-- /confluence:raw -->` unveraendert durchreichen |


## Ausgabe

Gib das **vollstaendige** Protokoll als Markdown aus — nicht nur die Aenderungen.  
Du musst die Asugabe des Protokolls starten mit
--- START ---
und Enden mit 
--- ENDE ---
  
Nachfoglend die **Bestehende Seite:** die Ergänzt werden soll:  
<content>