---
name: skill-budget-eigenleistung-el
description: Eigenleistungsplanung (EL) aus BPLUS-NG abrufen und mit Fremdleistung (BTL/DevOrder) kombinieren. Nutze diesen Skill für Fragen wie **"Auf welche EAs bucht ein Mitarbeiter seine Stunden?"**, **"Welche geplanten EAs sind noch mit Buchungssperren?"**, **"Jahressicht Eigenleistung pro EA"**, oder **"EL vs. Fremdleistung Gesamtübersicht"**. Der Skill lädt die aktuellen EL-Planungsdaten der OE EKEK/1 aus der BPLUS-NG REST-API.
---

# Skill: BPLUS-NG Eigenleistung (EL) — Planung & Analyse

Dieser Skill beschreibt den Workflow, um **Eigenleistungsplanungsdaten** aus BPLUS-NG per REST-API abzurufen und mit Fremdleistungsdaten (BTL/DevOrder) zu kombinieren.

## Pflicht: Analyse-Script verwenden

> **WICHTIG:** Bei EL-Analysefragen (Mitarbeiterbuchung, Buchungssperren, Jahressicht, EL vs. Fremdleistung) IMMER das Analyse-Script `analyze_el_data.py` ausführen.  
> Daten, Summen und Filterungen NIEMALS manuell berechnen.  
> **NIEMALS eine bereits vorhandene Ergebnis-Datei (.md) wiederverwenden.** Das Script muss bei JEDER Anfrage neu ausgeführt werden.  
> **Workflow:**
> 1. Export per `export_el_data.ps1` ausführen (falls Cache älter als 1 Tag oder --force-refresh)
> 2. `python analyze_el_data.py <json> --mitarbeiter <name> --usecase <typ>` ausführen (IMMER neu)
> 3. Das Script gibt den **Pfad zur Ergebnis-Datei** (.md) auf stdout aus
> 4. **Optional:** Falls die Userfrage Kontext erfordert, darf die Ergebnis-Datei per `replace_string_in_file` **vor oder nach den Tabellen** ergänzt werden. Tabellen NICHT verändern.
> 5. **NUR folgenden Satz im Chat an den User ausgeben:**
>   `Den Ergebnisbericht habe ich erstellt und hier für Dich abgelegt:` gefolgt von **klickbarem Markdown-Link** auf die Ergebnis-Datei.
> 6. **Im Chat NICHTS weiter ausgeben** — keine Tabellen, keine Zusammenfassungen, keine Zahlen. Der User öffnet die Datei selbst.
> **VERBOTEN:** Zahlen, Summen oder Tabellen im Chat anzeigen oder in der Datei verändern (außer Kontext-Ergänzungen).  
> **Pfade:**
> - Export: `<WORKSPACE>/.agents/skills/skill-budget-eigenleistung-el/export_el_data.ps1`
> - Analyse: `<WORKSPACE>/.agents/skills/skill-budget-eigenleistung-el/analyze_el_data.py`
> - Cache: `<WORKSPACE>/userdata/tmp/_el_consolidated_*.json` (1 Tag gültig)
> - Ergebnis: `<WORKSPACE>/userdata/sessions/<datum>_el_<filter>.md`
> - Logs: `<WORKSPACE>/userdata/tmp/logs/export_el_data_*.log`, `analyze_el_data_*.log`

## Kontext

- **Standard-OE:** EKEK/1
- **OrgUnit-ID:** 161 (hardcoded)
- **Standard-Jahr:** Automatisch aktuelles Jahr (dynamisch, optional in `--jahr` setzen)
- **Caching:** EL-Daten werden **1 Tag gecacht** (Stabilität, Performance)
  - Cache-Überschreibung: `--force-refresh`
  - Bei Timeout: Letzter verfügbarer Export wird genutzt + **ROTER WARNHINWEIS** mit Datum/Uhrzeit

## Use Cases

### 1. MA-Planung: "Auf welche EAs bucht ein Mitarbeiter seine Stunden?"

```bash
python analyze_el_data.py --mitarbeiter "Bachmann, Armin" --usecase ma-planung
```

**Output:** Tabelle pro Mitarbeiter

- EA-Nummer | EA-Titel | Jan–Dez Prozente | Gesamtprozent | Jahresstunden | Sperrungen
- Validierungsstatus des MA
- Warnung: Über-/Unterplanung (Summen ≠ 100%?)

---

### 2. Buchungssperren: "Welche geplanten EAs sind noch gesperrt?"

```bash
python analyze_el_data.py --usecase buchungssperren
```

**Output:** 

- Nur MA mit `bookingRightsExceptionsMonths` > 0
- Tabelle: MA | EA-Nummer | EA-Titel | Gesperrte Monate (z.B. Feb–Dez)
- Visualisierung: Heatmap (Monate × EAs)

---

### 3. Jahressicht: "Auf welchem EA wird wie viel EL gebucht (EUR)?"

```bash
python analyze_el_data.py --usecase jahressicht
```

**Output:**

- Aggregation pro EA über **alle MA**
- Formel: Summe(Prozente × Jahresstunden × Stundensatz) pro EA
- Tabelle: EA-Nummer | EA-Titel | Projektfamilie | Geplante EL (EUR) | Status
- Sortiert nach EL-Volumen (absteigend)

---

### 4. Gesamt-Übersicht: "EL vs. Fremdleistung pro EA"

```bash
python analyze_el_data.py --usecase gesamt-uebersicht
```

**Output:**

- **Join:** EL-Planungsdaten + BTL-Abrufe (Fremdleistung) auf EA-Nummer
- Tabelle: EA-Nummer | EA-Titel | Projektfamilie | EL-Plan (EUR) | Fremdleistung (EUR) | Summe | Anteil EL (%)
- Visualisierung: Pie-Chart (EL % vs. Fremdleistung %)
- Warnungen: EAs ohne BTL, EAs mit nur EL oder nur Fremdleistung

---

## Wann verwenden?

- User fragt nach **Eigenleistungsplanung** oder **EL-Planung**
- User fragt **"Auf welche EA bucht ****?"** (wenn MA-Name)
- User fragt nach **Buchungssperren** oder **blockierten EAs**
- User möchte **Jahressicht Eigenleistung** (EUR pro EA)
- User möchte **EL vs. Fremdleistung Vergleich** pro EA
- Keywords: `EL`, `Eigenleistung`, `auf welche EA`, `Buchungssperren`, `gesperrt`, `Plan`, `Planung`

---

## ℹ️ Automatische Defaults (weniger Fehlerquellen)


| Parameter                   | Default                    | Verhalten                                                                               |
| --------------------------- | -------------------------- | --------------------------------------------------------------------------------------- |
| **Jahr** (Export + Analyse) | Aktuelles Jahr (z.B. 2026) | Automatisch erkannt; optional mit `--jahr 2025` setzen                                  |
| **JSON-Datei**              | Neueste Export-Datei       | Sucht automatisch nach `_el_consolidated_JAHR.json` im Cache                            |
| **Cache**                   | 1 Tag Gültigkeit           | Bei älterem Export automatisch erneuern; `--force-refresh` um sofort neu zu exportieren |


**Beispiele mit optionalen Parametern:**

```bash
# Hauptvariante: aktuelles Jahr, Cache-Check, neueste JSON
python analyze_el_data.py --mitarbeiter "Bachmann, Armin" --usecase ma-planung

# Historische Daten (z.B. 2025)
python analyze_el_data.py --mitarbeiter "Bachmann, Armin" --usecase ma-planung --jahr 2025

# Export mit aktuellem Jahr erzwingen
.\export_el_data.ps1 -ForceRefresh
```

---

## Disambiguierung

**"Auf welche EA bucht X?"** hat zwei Interpretationen:

1. **X = Mitarbeitername** (z.B. "Bachmann") → `skill-budget-eigenleistung-el` (dieser Skill)
2. **X = Firmenname** (z.B. "Mustermann GmbH") → `skill-budget-bplus-export` (BTL-Daten, Feld `company`)

Bei Unsicherheit: User fragen, ob es um Mitarbeiterbuchung (EL) oder Firmenbuchung (Fremdleistung/BTL) geht.

---

## URLs und API-Endpunkte (Read-only)


| Endpunkt          | URL                                                                                              | Beschreibung                                            | Timeout         |
| ----------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------- | --------------- |
| BasicELData       | `GET /ek/api/BasicELData`                                                                        | OE-Kontext, Stundensatz                                 | 10s             |
| EmployeeHours     | `GET /ek/api/EmployeeHours?orgUnitId=161&year=2026`                                              | Alle MA + Wochenstunden                                 | 15s             |
| PlanningException | `GET /ek/api/PlanningException/GetPlanningExceptionsForUser?userId={id}&year=2026&orgUnitId=161` | EA-Zuordnungen + Monats-Prozente + Sperrungen pro MA    | **120s pro MA** |
| DevOrder          | `GET /ek/api/DevOrder/GetAll?year=2026`                                                          | EA-Stammdaten (Nummer, Titel, Laufzeit, Projektfamilie) | 20s             |
| BTL               | `GET /ek/api/Btl/GetAll?year=2026`                                                               | Fremdleistungs-Abrufe (geplanter Wert, Status)          | 20s             |


**Basis-URL:** `https://bplus-ng-mig.r02.vwgroup.com`

> **Achtung:** Die URL kann sich ändern (z.B. Wechsel von `-mig` zu Produktion). Bei Fehlern den User nach der aktuellen URL fragen.

---

## Authentifizierung

- **Windows-SSO** via Kerberos/NTLM
- PowerShell: `-UseDefaultCredentials`
- Voraussetzung: VW-Netzwerk (VPN oder On-Prem)

---

## Fehlerbehandlung

### Szenario 1: API-Timeout bei einzelnem MA-Call

- Export-Script skipped den fehlgeschlagenen MA, loggt Warnung
- Export läuft weiter mit allen anderen MA
- Result: Teildaten, nicht kritisch (Analysis kann mit N-1 MA weiterarbeiten)
- Benutzer erhält Hinweis: "1 von 11 MA konnte nicht abgerufen werden"

### Szenario 2: Globaler API-Fehler (z.B. Netzwerk down)

- Export-Script findet letzten erfolgreichen Export (Cache oder Session)
- Nutzt alte Daten + **ROTER WARNHINWEIS** am Anfang der .md-Datei
  - Format: `❌ WARNUNG: Daten vom {datum} {uhrzeit} (UTC+1) — aktueller Export fehlgeschlagen!`
- User sieht deutlich, dass Daten nicht aktuell sind

### Szenario 3: Cache-Hit (Export heute schon ausgeführt)

- `export_el_data.ps1` nutzt gecachte JSON-Datei
- Output: "Cache vom {datum} {uhrzeit} verwendet (Alter: {stunden}h)"
- User kann mit `--force-refresh` neu exportieren

---

## Darstellung der Ergebnisse

Tabellen immer als **pretty-printed Markdown-Tabellen** darstellen. Wenn Visualisierungen sinnvoll:

- **Heatmaps** für Buchungssperren (Monate × EAs)
- **Pie-Charts** für EL vs. Fremdleistung (Mermaid)
- **Bar-Charts** für Top-10 EAs nach EL-Volumen (optional)

### Beispiel-Ausgabe: MA-Planung


| EA-Nummer | EA-Titel       | Jan | Feb | Mär | Apr | Mai | Jun | Jul | Aug | Sep | Okt | Nov | Dez       | Gesamt   | Jahresstunden | Sperrungen      |
| --------- | -------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --------- | -------- | ------------- | --------------- |
| 0038004   | SB MEB 31      | 1%  | 1%  | 2%  | 2%  | 2%  | 3%  | 3%  | 3%  | 3%  | 3%  | 3%  | 3%        | 31%      | 465h          | —               |
| 0043102   | Kabelanbindung | 5%  | 5%  | 5%  | 5%  | 5%  | 5%  | 5%  | 5%  | 5%  | 5%  | 5%  | 5%        | 60%      | 900h          | Feb–Dez         |
| 0039801   | Prototyping    | 2%  | 2%  | 2%  | 2%  | 2%  | 2%  | 2%  | 2%  | 2%  | 2%  | 2%  | 2%        | 24%      | 360h          | —               |
|           |                |     |     |     |     |     |     |     |     |     |     |     | **Summe** | **115%** | **1725h**     | ⚠️ Überplanung! |


---

## Voraussetzungen

- VW-Netzwerk (SSO/Kerberos)
- PowerShell 5.1+ (Windows, `Invoke-RestMethod`)
- Python 3.11+ (Datenanalyse)
- keine externen Abhängigkeiten (nur stdlib: json, csv, datetime, sys)

---

## Caching & Performance

- **Cache-Dauer:** 1 Tag (86400 Sekunden)
- **Cache-Überschreibung:** `--force-refresh` Flag in `analyze_el_data.py`
- **Cache-Location:** `<WORKSPACE>/userdata/tmp/_el_consolidated_*.json`
- **Erwartete Laufzeit:**
  - Sequentiell (aktuell): ~~360 Sekunden (~~6 Minuten) — akzeptabel zum Testen
  - Parallel (zukünftig): ~40 Sekunden (mit `# TODO: PARALLEL` Umbauten im Code)

---

## Phase 2: Parallelisierung (zukünftig)

Die Scripts sind vorbereitet für Parallelisierung. Siehe `export_el_data.ps1` Kommentare:

- `# TODO: PARALLEL` Marker zeigen wo PowerShell `Start-Job` + `Wait-Job` nutzen sollte
- Caching-Logik bleibt gleich
- Fehlerbehandlung pro Job wird robuster

Umstellung: Umgebungsvariable `$EL_PARALLEL=1` oder Parameter `--parallel` hinzufügen.