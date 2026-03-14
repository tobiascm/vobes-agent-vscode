---
name: skill-ua-leiter
description: Unterabteilungsleiter (UA-Leiter) aus BPLUS-NG abrufen. Nutze diesen Skill wenn der User nach Leitungen, UA-Leitern oder Ansprechpartnern einer OE fragt.
---

# Skill: BPLUS-NG Unterabteilungsleiter (UA-Leiter)

Dieser Skill findet die **Leitungen** (Leitung=1) aus den BPLUS-NG InfoDepartments-Daten.

## Kontext

- Gleiche Datenquelle wie Stundensaetze (InfoDepartments-Seite).
- Gefiltert auf Personen mit Leitungsfunktion (`Leitung=1`).
- Liefert OE, Ebene und Mail-Adresse.

## Wann verwenden?

- Der User fragt nach **Unterabteilungsleitern** (UA-Leitern)
- Der User sucht den **Leiter** / **Ansprechpartner** einer OE
- Der User moechte wissen, wer eine bestimmte OE leitet

## Datenstruktur

| CSV-Spalte | Beschreibung | Beispiel |
|---|---|---|
| `oe` | Organisationseinheit | `EKEK/1` |
| `ebene` | Hierarchie-Ebene | `Unterabteilung`, `Abteilung`, `Hauptabteilung`, `Bereich` |
| `mail` | E-Mail der Leitung | `max.mustermann@volkswagen.de` |

## URL

| Ressource | URL |
|---|---|
| InfoDepartments (HTML) | `https://bplus-ng-mig.r02.vwgroup.com/ek-reports/InfoDepartments.aspx?y={year}` |

## Voraussetzungen

- VW-Netzwerk (SSO/Kerberos)
- PowerShell mit `Invoke-WebRequest`

---

## Export per Script

**Pfad:** `<WORKSPACE>/.agents/skills/skill-ua-leiter/export_ua_leiter.ps1`

### Standard-Export (alle Leitungen, aktuelles Jahr)

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-ua-leiter\export_ua_leiter.ps1"
```

### Mit Parametern

```powershell
# Bestimmte OE:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-ua-leiter\export_ua_leiter.ps1" -OrgUnit "EKEK/1"

# Anderes Jahr:
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-ua-leiter\export_ua_leiter.ps1" -Year 2025
```

### Parameter

| Parameter | Default | Beschreibung |
|---|---|---|
| `-Year` | Aktuelles Jahr | Jahr |
| `-OrgUnit` | (leer = alle) | OE filtern |
| `-OutputPath` | `<WORKSPACE>\userdata\bplus\YYYYMMDD_UA_Leiter[_OE].csv` | Zielpfad |
| `-BaseUrl` | `https://bplus-ng-mig.r02.vwgroup.com` | Basis-URL |

## Haeufige Probleme

| Problem | Loesung |
|---|---|
| Seite nicht erreichbar | VW-Netzwerk/VPN pruefen |
| Keine Ergebnisse | OE-Schreibweise pruefen (exakt, z.B. `EKEK/1`) |
