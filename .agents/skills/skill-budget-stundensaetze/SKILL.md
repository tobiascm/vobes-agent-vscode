---
name: skill-budget-stundensaetze
description: Stundensaetze (Hourly Rates) aus BPLUS-NG per API abrufen und als CSV exportieren. Nutze diesen Skill wenn der User nach Stundensaetzen, Kostenstellen oder OE-Stundensaetzen fragt.
---

# Skill: BPLUS-NG Stundensaetze

Dieser Skill beschreibt den Workflow, um **Stundensaetze** (Hourly Rates) aus BPLUS-NG/EK-Reports als CSV-Datei herunterzuladen.

## Kontext

- Die Quelle ist die Seite **InfoDepartments** im BPLUS-NG EK-Reports-Bereich.
- Die Daten enthalten Stundensaetze pro OE, Kostenstelle und Jahr.
- Die Daten sind in die HTML-Seite als JSON eingebettet (Tabulator-Tabelle) — es gibt keine separate REST-API.

## Wann verwenden?

- Der User fragt nach **Stundensaetzen** (Hourly Rates)
- Der User moechte wissen, welchen Stundensatz eine OE / Kostenstelle hat
- Der User erwaehnt InfoDepartments, Kostenstellen-Saetze oder OE-Stundensaetze
- Der User moechte Stundensaetze als CSV exportieren

## Datenstruktur

Der Stundensatz ist pro OE immer gleich. Die Daten werden daher aggregiert exportiert (1 Zeile pro OE).

| CSV-Spalte | Beschreibung | Beispiel |
|---|---|---|
| `jahr` | Jahr | `2026` |
| `kst` | Kostenstelle | `1721` |
| `oe` | Organisationseinheit | `EKEK/1` |
| `stundensatz` | Stundensatz in EUR | `153.35` |

## CSV-Format

- **Delimiter:** Komma (`,`)
- **Encoding:** UTF-8 ohne BOM
- **Dezimalzeichen:** Punkt (`.`)
- **Spaltennamen:** snake_case

## URL

| Ressource | URL |
|---|---|
| InfoDepartments (HTML) | `https://bplus-ng-mig.r02.vwgroup.com/ek-reports/InfoDepartments.aspx?y={year}` |

> Hinweis: Es gibt keine separate REST-API. Die Daten werden aus der HTML-Seite extrahiert (eingebettetes JSON im Tabulator-Widget).

## Voraussetzungen

- Der User muss im VW-Netzwerk authentifiziert sein (SSO/Kerberos)
- PowerShell mit `Invoke-WebRequest` (Standard)

---

## Export per Script

Im Skill-Verzeichnis liegt das Script `export_stundensaetze.ps1`.

**Pfad:** `<WORKSPACE>/.agents/skills/skill-budget-stundensaetze/export_stundensaetze.ps1`

### Standard-Export (alle OEs, aktuelles Jahr)

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-budget-stundensaetze\export_stundensaetze.ps1"
```

### Mit Parametern

```powershell
# Anderes Jahr:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-budget-stundensaetze\export_stundensaetze.ps1" -Year 2025

# Bestimmte OE:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-budget-stundensaetze\export_stundensaetze.ps1" -OrgUnit "EKEK/1"

# Eigener Ausgabepfad:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-budget-stundensaetze\export_stundensaetze.ps1" -OutputPath "C:\tmp\stundensaetze.csv"
```

### Parameter

| Parameter | Default | Beschreibung |
|---|---|---|
| `-Year` | Aktuelles Jahr | Jahr fuer den Export |
| `-OrgUnit` | (leer = alle) | OE filtern, z.B. `EKEK/1` |
| `-OutputPath` | `<WORKSPACE>\userdata\exports\YYYYMMDD_Stundensaetze[_OE].csv` | Zielpfad |
| `-BaseUrl` | `https://bplus-ng-mig.r02.vwgroup.com` | Basis-URL |

### Ausgabedatei

```
<WORKSPACE>/userdata/exports/YYYYMMDD_Stundensaetze.csv          # Alle OEs
<WORKSPACE>/userdata/exports/YYYYMMDD_Stundensaetze_EKEK-1.csv   # Gefiltert auf EKEK/1
```

---

## Manueller Inline-Export (ohne Script)

```powershell
$response = Invoke-WebRequest -Uri "https://bplus-ng-mig.r02.vwgroup.com/ek-reports/InfoDepartments.aspx?y=2026" -UseDefaultCredentials
$match = [regex]::Match($response.Content, '"data":\s*(\[[\s\S]*?\])\s*\}\);')
$records = $match.Groups[1].Value | ConvertFrom-Json
# Beispiel: Stundensatz fuer EKEK/1
$records | Where-Object { $_.col3 -eq 'EKEK/1' } | ForEach-Object { "$($_.col3) | $($_.col5) | $($_.col7) EUR/h" }
```

## Direkte Abfrage (ohne CSV-Export)

Wenn der User nur den Stundensatz einer bestimmten OE wissen moechte, kann das Script ausgefuehrt und die CSV-Datei direkt ausgelesen werden. Alternativ kann der Inline-Export (siehe oben) genutzt werden, um die Daten direkt in der Konsole anzuzeigen.

## Haeufige Probleme

| Problem | Loesung |
|---|---|
| Seite nicht erreichbar | VW-Netzwerk/VPN pruefen |
| JSON-Extraktion schlaegt fehl | Seitenstruktur hat sich geaendert — manuell pruefen |
| Keine Daten fuer ein Jahr | Jahr pruefen (ggf. noch keine Daten hinterlegt) |
| URL nicht erreichbar | URL kann sich aendern (z.B. `-mig` entfaellt); User fragen |
