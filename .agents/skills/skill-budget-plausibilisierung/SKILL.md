---
name: skill-budget-plausibilisierung
description: Plausibilisierungsanfragen und BM-Texte fuer EAs, Fahrzeugprojekte, AWS, Beauftragungen, Abrufe und Vorgaenge beantworten. Unterscheidet zwischen SYS/BIB, Projektbuero/Pruefbuero, Bordnetzentwicklung, KUeE und VOBES 2025 IT. Nutze diesen Skill wenn ein Controller, Projektleiter oder Budgetverantwortlicher nach einer Begruendung fuer Aufwaende fragt, einen BM-Text benoetigt, oder eine Aufwandsplausibilisierung angefordert wird.
---

# Skill: Plausibilisierung und BM-Texte

Dieser Skill beantwortet Plausibilisierungsanfragen zu Aufwaenden in der EKEK/1. Er liefert passende **Begruendungen** und **Muster-BM-Texte** basierend auf dem erkannten Gewerk und der Firma.

## Wann verwenden?

- Controller fragt: "Warum wird X€ fuer EA Y benoetigt?"
- User braucht einen **BM-Text** fuer einen neuen Abruf / Vorgang
- User braucht eine **Begruendung** fuer eine Aufwandsplausibilisierung
- Nachfrage zu Beauftragungen, Abrufen oder Vorgaengen
- Stichwoerter: Plausibilisierung, Begruendung, BM-Text, Aufwandsplausibilisierung, Nachfrage Controller, "warum wird X benoetigt"

## Entscheidungslogik

> **Workflow bei jeder Anfrage:**
>
> 1. **Gewerk/Firma identifizieren:** Aus der Anfrage das Gewerk oder die Firma extrahieren
> 2. **Kategorie bestimmen:** Ueber die Mapping-Tabelle (unten) die Kategorie und Textquelle ermitteln
> 3. **Textquelle laden:** Die passende Datei per `read_file` oeffnen
> 4. **Begruendung extrahieren:** Den zum Gewerk passenden Abschnitt lesen
> 5. **BM-Text extrahieren:** Den zur Firma passenden Muster-BM-Text lesen
> 6. **Parametrisieren:** Platzhalter ersetzen (Projekt, Leistungszeitraum, Stueckzahlen, EA)
> 7. **Hut/Plattform-Validierung durchfuehren** (siehe unten)
> 8. **Antwort formulieren:** Begruendung + BM-Text als fertige Vorlage ausgeben

## Kategorie-Mapping

| Kategorie | Firmen / Gewerke | Textquelle Begruendung | Textquelle BM-Text |
|---|---|---|---|
| **SYS/BIB** | Bertrandt, EDAG, SYS-Flow | `scripts/budget/begruendungen.md` → Abschnitt "Gewerk SYS und Bib" / "Gewerk SYS-Flow" | `scripts/budget/muster-bm-texte.md` → Abschnitt "Gewerk SYS-BIB" |
| **Projektbuero / Pruefbuero** | FEV, FES, B+W, Rulechecker (4soft Vestigo) | `scripts/budget/begruendungen.md` → Abschnitt "Gewerk Bordnetz Freigabepruefung" / "Gewerk Bordnetz-Konstruktionspruefung" | `scripts/budget/muster-bm-texte.md` → Abschnitt "Projektbuero" / "4soft Rulechcker" |
| **Bordnetzentwicklung** | 4soft, Thiesen, SEBN, Sumitomo | `scripts/budget/begruendungen.md` → Abschnitt "Gewerk Bordnetzentwicklung (Firma)" | `scripts/budget/muster-bm-texte.md` → Abschnitt "4soft" / "Thiesen Spezifikation" / "Thiesen Support" / "SEBN Support/Spezifikation" |
| **KUeE** | VCTC SOC, Systemschaltplaene (Plattform/Hut-Kalkulation) | `scripts/budget/kue_texte.md` | `scripts/budget/kue_texte.md` |
| **VOBES 2025 IT** | PMT, SW-Entwicklung, KSK-ZEN, PMT-Mechanik, SYS-Designer, Spezifikation | `scripts/budget/IT_begruendungen.md` | `scripts/budget/IT_begruendungen.md` |

## Detailstufen fuer Begruendungen

Die Datei `scripts/budget/begruendungen.md` enthaelt Begruendungen in drei Detailstufen:

| Stufe | Wann verwenden |
|---|---|
| **kurz** | Fuer einfache Rueckfragen, Statusberichte, kurze E-Mail-Antworten |
| **mittel** | Standard fuer Plausibilisierungsanfragen von Controllern |
| **ausfuehrlich** | Fuer formelle Begruendungen, Audits, detaillierte Nachfragen |

> **Standard:** Wenn keine Stufe angegeben wird, verwende **mittel**.
> Biete dem User an, die Begruendung in einer anderen Detailstufe zu liefern.

## Hut/Plattform-Validierung (PFLICHT)

> **KRITISCHE REGEL — bei jeder Antwort pruefen:**
>
> - Auf **Hut-EAs** darf der generierte Text **NIEMALS** das Wort "Plattform" enthalten
> - Auf **Plattform-EAs** darf der generierte Text **NIEMALS** das Wort "Hut" enthalten
>
> **Pruefablauf:**
> 1. Ist die EA bekannt? → EA-Typ (Hut oder Plattform) bestimmen
> 2. Generierten Text (BM-Text + Begruendung) auf verbotene Woerter pruefen
> 3. Falls Verstoss gefunden:
>    - ⚠️ **Warnung an den User ausgeben**
>    - Verbotenes Wort im Text markieren
>    - Korrigierten Text ohne das verbotene Wort vorschlagen
>
> Falls der EA-Typ nicht bestimmt werden kann, den User aktiv fragen:
> "Handelt es sich um eine Hut-EA oder eine Plattform-EA?"

## Platzhalter-Hinweis

Die Textquellen fuer **KUeE** und **VOBES 2025 IT** sind aktuell noch leer:

- `scripts/budget/kue_texte.md` — Platzhalter, wird spaeter befuellt
- `scripts/budget/IT_begruendungen.md` — Platzhalter, wird spaeter befuellt

> Wenn eine Anfrage in diese Kategorien faellt:
> 1. Den User informieren: "Fuer diese Kategorie sind noch keine Muster-Texte hinterlegt."
> 2. Anbieten, eine individuelle Begruendung auf Basis der allgemeinen Informationen zu formulieren
> 3. Darauf hinweisen, dass der Text in die jeweilige Datei aufgenommen werden sollte

## Muster-BM-Text: Standardstruktur

Jeder BM-Text folgt diesem Schema (Details je nach Firma/Gewerk anpassen):

```
[Leistungsbeschreibung] fuer das Projekt [Fahrzeugprojekt]
Beauftragt wird gemaess Rahmenvertrag [Rahmenvertragsnummer]
Gewerk #[Nr], Preis [Stueckpreis] €, [Anzahl] Stueck
Leistungszeitraum: [MM/JJ] – [MM/JJ]
[Ergaenzende Beschreibung der Leistung]
```

> **Tipps fuer den User:**
> - Leistungszeitraum-Ende = Lieferdatum (in der Regel)
> - Monatsangabe statt Tagesangabe nutzen (z.B. 01/2x – 12/2x)
> - Lieferdatum vor dem 20.12. des Jahres festlegen
> - Firma NICHT manuell auswaehlen — wird ueber Rahmenvertrag automatisch gefuellt
> - Genau 2 Anhang-Dateien: Kontrakt (PDF) + Stueckliste (XLS/PDF)
> - Kein Vergabevorschlag, kein Lastenheft, kein One-Pager

## Optionale Ergaenzung mit BPLUS-Daten

Wenn der User die Begruendung mit echten Zahlen untermauern moechte:

> Verweise auf `skill-budget-bplus-export` und dessen `report_bplus.py`.
> Beispiel: "Moechtest du die Begruendung mit den aktuellen BPLUS-Daten (Vorgaenge, Abrufhoehen, Status) untermauern?"

## Beispiel-Anfragen und erwartetes Verhalten

**Anfrage:** "Warum brauchen wir 39.440 € fuer Bertrandt?"
1. Firma "Bertrandt" → Kategorie **SYS/BIB**
2. `read_file` von `scripts/budget/begruendungen.md` → Abschnitt "Gewerk SYS und Bib"
3. `read_file` von `scripts/budget/muster-bm-texte.md` → Abschnitt "Gewerk SYS-BIB" → Bertrandt
4. Begruendung (mittel) + BM-Text ausgeben
5. Hut/Plattform-Pruefung (EA-Typ abfragen falls noetig)

**Anfrage:** "BM-Text fuer neuen 4soft Rulechecker Abruf"
1. Firma "4soft" + "Rulechecker" → Kategorie **Projektbuero / Pruefbuero**
2. `read_file` von `scripts/budget/muster-bm-texte.md` → Abschnitt "4soft Rulechcker"
3. BM-Text mit Platzhaltern ausgeben, User nach Projekt und Leistungszeitraum fragen

**Anfrage:** "Begruendung fuer PMT-Aufwaende auf EA 0043402"
1. "PMT" → Kategorie **VOBES 2025 IT**
2. `read_file` von `scripts/budget/IT_begruendungen.md` → leer
3. User informieren: "Fuer VOBES 2025 IT sind noch keine Muster-Texte hinterlegt."
