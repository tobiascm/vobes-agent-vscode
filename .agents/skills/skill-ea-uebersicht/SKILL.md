---
name: skill-ea-uebersicht
description: Entwicklungsauftraege, EA-Nummer, Projektfamilie, Controller, SOP aus BPLUS-NG per API abrufen und als CSV exportieren und auswerten.
---

# Skill: BPLUS-NG Entwicklungsauftraege (EA-Uebersicht)

Dieser Skill laedt die **EA-Uebersicht** (Entwicklungsauftraege / DevOrders) aus BPLUS-NG per REST-API.

## Kontext

- Entspricht der Tabelle auf der BPLUS-NG Seite `InfoDevOrders.aspx`
- Liefert EA-Nummer, Titel, Laufzeit, SOP, Projektfamilie, Controller und Hierarchie
- Filterung nach aktiv/inaktiv und Projektfamilie moeglich

## Wann verwenden?

- Der User fragt nach **Entwicklungsauftraegen** (EA)
- Der User moechte eine **EA-Uebersicht** oder **EA-Liste** aus BPLUS-NG
- Der User sucht eine bestimmte **EA-Nummer** oder EAs einer **Projektfamilie**
- Der User erwaehnt **DevOrders** oder **InfoDevOrders**

## Datenstruktur

### API-Felder (JSON)

| JSON-Feld | CSV-Spalte | Beschreibung | Beispiel |
|---|---|---|---|
| `number` | `ea_number` | EA-Nummer | `0011953` |
| `developmentOrderName` | `title` | Titel des EA | `MEB Antrieb Allrad/Heck ID Buzz` |
| `active` | `active` | Aktiv-Status | `True` / `False` |
| `dateFrom` | `date_from` | Start-Datum | `2017-10-18` |
| `dateUntil` | `date_until` | Ende-Datum (BIS) | `2025-01-31` |
| `sop` | `sop` | SOP-Datum | `2024-04-04` |
| `assignedProjectFamily` | `project_family` | Projektfamilie | `A_BEV` |
| `controller` | `controller` | Controller-Kuerzel | `VWTH3IE` |
| `hierarchy` | `hierarchy` | TE-Hierarchie | `TE - Aggregate - Baureihe G4 - Alternative Antriebe` |

### Weitere API-Felder (nicht im Standard-Export)

| JSON-Feld | Beschreibung |
|---|---|
| `idDevelopmentOrder` | Interne ID |
| `idProjectFamily` | Interne Projektfamilien-ID |
| `assignedProjectFamilyActive` | Projektfamilie aktiv? |
| `idAideeUserMainResponsible` | AIDEE-User-ID Hauptverantwortlicher |
| `strAideeUserMainResponsible` | Name Hauptverantwortlicher |

## URLs und API-Endpunkte

| Ressource | URL |
|---|---|
| EA-Uebersicht (Web) | `https://bplus-ng-mig.r02.vwgroup.com/ek-reports/InfoDevOrders.aspx?y={year}` |
| API: Alle DevOrders | `https://bplus-ng-mig.r02.vwgroup.com/ek/api/DevOrder/GetAll?year={year}` |

## Voraussetzungen

- VW-Netzwerk (SSO/Kerberos)
- PowerShell mit `Invoke-RestMethod`

---

## Export per Script

**Pfad:** `<WORKSPACE>/.agents/skills/skill-ea-uebersicht/export_ea_uebersicht.ps1`

### Standard-Export (alle aktiven EAs, aktuelles Jahr)

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-ea-uebersicht\export_ea_uebersicht.ps1"
```

### Mit Parametern

```powershell
# Inkl. inaktive EAs:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-ea-uebersicht\export_ea_uebersicht.ps1" -ActiveOnly $false

# Bestimmte Projektfamilie:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-ea-uebersicht\export_ea_uebersicht.ps1" -ProjectFamily "A_BEV"

# Anderes Jahr:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-ea-uebersicht\export_ea_uebersicht.ps1" -Year 2025
```

### Parameter

| Parameter | Default | Beschreibung |
|---|---|---|
| `-Year` | Aktuelles Jahr | Jahr |
| `-ActiveOnly` | `$true` | Nur aktive EAs |
| `-ProjectFamily` | (leer = alle) | Projektfamilie filtern |
| `-OutputPath` | `<WORKSPACE>\userdata\bplus\YYYYMMDD_EA_Uebersicht[_ProjFam][_aktiv].csv` | Zielpfad |
| `-BaseUrl` | `https://bplus-ng-mig.r02.vwgroup.com` | Basis-URL |

### Manueller Inline-Abruf (ohne Script)

```powershell
$response = Invoke-RestMethod -Uri "https://bplus-ng-mig.r02.vwgroup.com/ek/api/DevOrder/GetAll?year=2026" -UseDefaultCredentials
$active = $response | Where-Object { $_.active -eq $true }
$active | Select-Object number, developmentOrderName, assignedProjectFamily, dateUntil | Format-Table
```

## Haeufige Probleme

| Problem | Loesung |
|---|---|
| API nicht erreichbar | VW-Netzwerk/VPN pruefen |
| Leere Antwort | Jahr pruefen (API liefert nur Daten fuer gueltige Jahre) |
| EA nicht gefunden | EA-Nummer mit fuehrenden Nullen angeben (z.B. `0011953`) |
