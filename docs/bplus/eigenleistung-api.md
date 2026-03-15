# BPLUS-NG Eigenleistung (EL) — API-Spezifikation

> **Stand:** 2026-03-14 (aktualisiert) — Reverse-Engineering der Angular-App und Live-API-Tests.
> **Quelle:** `https://bplus-ng-mig.r02.vwgroup.com/ek/el`

---

## 1. Überblick

Die BPLUS-NG EL-Seite ("Planung der Eigenleistung") verwaltet die **monatliche Arbeitsplanung** von Mitarbeitern auf Entwicklungsaufträge (EA). Die Angular-App kommuniziert mit einer ASP.NET-REST-API unter `/ek/api/`.

### Fachliches Modell

```
OE (z.B. EKEK/1, orgUnitId=161)
 └── Mitarbeiter (idxUser)
      ├── Wochenstunden (hoursPerWeek)
      ├── Planungsstatus / Validierung
      └── Planungspositionen (pro EA)
           ├── Prozent-Verteilung pro Monat (Jan–Dez)
           ├── Planungsbetrag (EUR)
           └── Buchungsrechts-Exceptions
```

### Authentifizierung

- **Windows-SSO** via Kerberos/NTLM
- PowerShell: `-UseDefaultCredentials`
- Voraussetzung: VW-Netzwerk (VPN oder On-Prem)

### Basis-URL

```
https://bplus-ng-mig.r02.vwgroup.com
```

> **Achtung:** Die URL kann sich ändern (z.B. Wechsel von `-mig` zu Produktion). Bei Fehlern User nach aktueller URL fragen.

---

## 2. Bekannte OrgUnit-IDs

| OE | orgUnitId | Verifiziert |
|---|---|---|
| EKEK/1 | 161 | Ja (Live-Test) |

> **Wissenslücke:** Mapping aller OE-Namen → orgUnitId ist unbekannt. Kann vermutlich über `/ek/api/BasicELData` mit anderem Auth-Kontext oder einen Admin-Endpunkt ermittelt werden. Die BTL-API (`/ek/api/Btl/GetAll`) liefert `orgUnitName`, aber nicht `orgUnitId`.

---

## 3. Lese-Endpunkte (GET) — Verifiziert

### 3.1 Jahr-Konfiguration

```
GET /ek/api/Year
```

**Response:** Array aller konfigurierten Jahre.

```json
{
  "idxYear": 26,
  "intYear": 2026,
  "bitForELPlanningIsActive": true,
  "bitForPzIsActive": true,
  "idxBTLYearStatus": 1,
  "idxForecastYearStatus": 1,
  "intHours": 1500,
  "bitDisabled": null
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `idxYear` | int | Interner Index |
| `intYear` | int | Kalenderjahr |
| `bitForELPlanningIsActive` | bool | EL-Planung für dieses Jahr aktiv? |
| `bitForPzIsActive` | bool | Planungsziel aktiv? |
| `intHours` | int | Jahres-Arbeitsstunden (z.B. 1500) |

---

### 3.2 OE-Basisdaten

```
GET /ek/api/BasicELData
```

**Response:** JSON-Objekt mit OE-Daten des eingeloggten Users.

```json
{
  "idxOrgUnit": 161,
  "strOrgUnit": "EKEK/1",
  "strOrgUnitDescription": "",
  "idxParentOrgUnit": 160,
  "intCostCenter": 0,
  "idxOrgUnitLevel": 5,
  "bitOrgUnitBudgetEnabled": true,
  "strMainResponsibleMail": "tobias.carsten.mueller@volkswagen.de",
  "idxMainResponsible": 1053,
  "children": []
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `idxOrgUnit` | int | OE-ID (für alle weiteren Calls benötigt) |
| `strOrgUnit` | string | OE-Kürzel |
| `idxParentOrgUnit` | int | Eltern-OE |
| `strMainResponsibleMail` | string | E-Mail Hauptverantwortlicher |

> **Wissenslücke:** Liefert nur die OE des eingeloggten Users. Unbekannt, ob man per Parameter andere OEs abrufen kann, oder ob ein Admin-Endpunkt existiert, der alle OEs listet.

---

### 3.3 Stundensatz & Jahresstunden prüfen

```
GET /ek/api/BasicELData/CheckExistingHourlyCostRate?intYear={year}&idxOrgUnit={orgUnitId}
```

**Response:** `bool` (true/false) — ob Stundensatz für die OE im Jahr hinterlegt ist.

```
GET /ek/api/BasicELData/CheckExistingYearlyWorkingHours?intYear={year}
```

**Response:** `bool` (true/false) — ob Jahresarbeitsstunden konfiguriert sind.

---

### 3.4 Mitarbeiter-Übersicht

```
GET /ek/api/EmployeeHours?orgUnitId={orgUnitId}&year={year}
```

**Parameter:**

| Parameter | Typ | Beispiel | Beschreibung |
|---|---|---|---|
| `orgUnitId` | int | 161 | OE-ID |
| `year` | int | 2026 | Planjahr |

**Response:** JSON-Objekt mit `current`, (vermutlich auch `former`, `future`).

```json
{
  "current": [
    {
      "idxUser": 1056,
      "isActive": true,
      "userFullName": "Bachmann, Armin",
      "hoursPerWeek": 40.0,
      "hoursPerWeekDefault": 4.0,
      "isValidated": false,
      "dateValidated": null,
      "idxUserWhoValidated": null,
      "lastValidation": null,
      "planingStatus": 0,
      "futureOuName": null,
      "futureOuStartDate": null,
      "transferredDate": null
    }
  ]
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `idxUser` | int | Mitarbeiter-ID (für weitere Abfragen) |
| `userFullName` | string | Name (Nachname, Vorname) |
| `hoursPerWeek` | float | Aktuelle Wochenstunden |
| `hoursPerWeekDefault` | float | Standard-Wochenstunden |
| `isValidated` | bool | Planung validiert? |
| `dateValidated` | datetime? | Validierungsdatum |
| `planingStatus` | int | 0 = unklar, Enum-Werte unbekannt |

> **Wissenslücke:** Die Felder `former` und `future` im Response-Objekt sind nicht getestet. Vermutlich analog zu den Tabs "Ehemalige Positionen" und "Künftige Positionen" in der UI.

> **Wissenslücke:** Die Enum-Werte für `planingStatus` sind unbekannt. In der UI wird ein farbiger Punkt (●) angezeigt — vermutlich 0=nicht geplant, 1=teilweise, 2=vollständig.

---

### 3.5 Mitarbeiter-Historie

```
GET /ek/api/EmployeeHours/GetUsersHistory?idxOrgUnit={orgUnitId}
```

**Response:** Array mit OE-Wechsel-Historie.

```json
{
  "idxHistory": 1553,
  "idxUser": 1056,
  "idxCurrentOU": 161,
  "idxPreviousOU": 51,
  "dteChangeDate": "2023-10-16T12:55:34.623",
  "bitIsActive": true,
  "dteStartDate": "2023-10-16T00:00:00",
  "dteEndDate": "2023-11-11T00:00:00"
}
```

---

### 3.6 Künftige Positionen

```
GET /ek/api/EmployeeHours/GetFuturePositions?orgUnitId={orgUnitId}&year={year}
```

**Response:** Array (im Test leer: `[]`).

> **Wissenslücke:** Datenstruktur unbekannt, da keine Daten vorhanden waren.

---

### 3.7 Export (Vollexport) ⭐

```
GET /ek/api/EmployeeHours/GetEmployeesExport?orgUnitId={orgUnitId}&year={year}
```

**Parameter:**

| Parameter | Typ | Beispiel | Beschreibung |
|---|---|---|---|
| `orgUnitId` | int | 161 | OE-ID |
| `year` | int | 2026 | Planjahr |

> **Achtung:** Dieser Endpunkt ist **sehr langsam** (>180 Sekunden). Timeout auf mindestens **300 Sekunden** setzen. Außerdem **muss** `-OutFile` verwendet werden — `Invoke-WebRequest` ohne `-OutFile` erzeugt ein Timeout, da der Response-Body zu groß ist, um im Speicher gepuffert zu werden.

**PowerShell-Aufruf:**
```powershell
Invoke-WebRequest -Uri "https://bplus-ng-mig.r02.vwgroup.com/ek/api/EmployeeHours/GetEmployeesExport?orgUnitId=161&year=2026" -UseDefaultCredentials -TimeoutSec 300 -OutFile "export.json"
```

**Response:** JSON-Array (Content-Type trotz `.json` nicht explizit gesetzt). Ca. 379 KB für EKEK/1.

**Beispiel-Eintrag:**
```json
{
  "orgUnitName": "EKEK/1",
  "year": 2026,
  "employeeAssignment": "Current",
  "weeklyWorkingHours": 40.00,
  "employee": "Bachmann, Armin",
  "devOrderNumber": "0038004",
  "devOrderDescription": "SB MEB 31",
  "devOrderFrom": "08.09.2017",
  "devOrderTo": "31.12.2028",
  "planningTarget": "0",
  "totalValueDepartment": "0",
  "january": "1%",
  "february": "1%",
  "march": "2%",
  "april": "2%",
  "may": "2%",
  "june": "3%",
  "july": "3%",
  "august": "3%",
  "september": "3%",
  "october": "3%",
  "november": "3%",
  "december": "3%"
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `orgUnitName` | string | OE-Kürzel |
| `year` | int | Planjahr |
| `employeeAssignment` | string | `"Current"`, vermutlich auch `"Former"`, `"Future"` |
| `weeklyWorkingHours` | float | Wochenstunden |
| `employee` | string | Nachname, Vorname |
| `devOrderNumber` | string | EA-Nummer |
| `devOrderDescription` | string | EA-Titel |
| `devOrderFrom` | string | EA-Start (DD.MM.YYYY) |
| `devOrderTo` | string | EA-Ende (DD.MM.YYYY) |
| `planningTarget` | string | Planungsziel |
| `totalValueDepartment` | string | Planbetrag Abteilung (EUR) |
| `january`…`december` | string | Monatliche Prozent-Werte (z.B. `"3%"`) |

> **Hinweis:** Der Export liefert alle Daten in einer **flachen Struktur** (1 Zeile pro MA × EA-Kombination). Für EKEK/1 in 2026: **764 Einträge**, 11 aktuelle Mitarbeiter.

> **Vorteil gegenüber `GetPlanningExceptionsForUser`:** Ein einziger API-Call statt N Calls (einer pro MA), und wesentlich einfacher zu parsen. Die Monats-Prozente liegen als String mit `%`-Suffix vor (muss beim Parsen entfernt werden).

> **Nachteil gegenüber `GetPlanningExceptionsForUser`:** Weniger Detail-Felder (kein `developementOrderId`, `projectFamily`, `planAmmount`, `internalCalc`, `externalCalc`, `bookingRightsExceptionsMonths`).

---

### 3.8 Planungsdaten pro Mitarbeiter ⭐

Dies ist der **zentrale Endpunkt** für die monatliche EA-Planung.

```
GET /ek/api/PlanningException/GetPlanningExceptionsForUser?userId={userId}&year={year}&orgUnitId={orgUnitId}
```

**Parameter:**

| Parameter | Typ | Beispiel | Beschreibung |
|---|---|---|---|
| `userId` | int | 1056 | Mitarbeiter-ID (aus EmployeeHours) |
| `year` | int | 2026 | Planjahr |
| `orgUnitId` | int | 161 | OE-ID |

> **Hinweis:** Dieser Endpunkt braucht **>30 Sekunden** Antwortzeit. Timeout großzügig wählen (mind. 120s).

**Response:**

```json
{
  "userId": 1056,
  "plannedPositionId": null,
  "orgUnitId": 161,
  "year": 2026,
  "yearWorkHours": 1500,
  "hourlyRateFltValueMix": 159.08,
  "inactiveMonths": [],
  "planningExceptions": [
    {
      "idxWorkPlanning": null,
      "userId": 1056,
      "plannedPositionId": null,
      "developementOrderId": 80,
      "organizationalUnitId": 161,
      "year": 2026,
      "projectFamilyActive": true,
      "projectFamilyId": 259,
      "projectFamily": "MEB",
      "projectFamilyLeaderEmail": null,
      "devOrderActive": true,
      "number": "0038004",
      "description": "0038004 - SB MEB 31",
      "devOrderDescription": "SB MEB 31",
      "from": "2017-09-08T00:00:00",
      "until": "2028-12-31T00:00:00",
      "pzActual": 0,
      "planAmmount": 294762.0,
      "internalCalc": 256601.51562,
      "externalCalc": 38160.0,
      "percentInJan": 1.0,
      "percentInFeb": 1.0,
      "percentInMar": 2.0,
      "percentInApr": 2.0,
      "percentInMay": 2.0,
      "percentInJun": 3.0,
      "percentInJul": 3.0,
      "percentInAug": 3.0,
      "percentInSep": 3.0,
      "percentInOct": 3.0,
      "percentInNov": 3.0,
      "percentInDec": 3.0,
      "notPermittedMonths": null,
      "bookingRightsExceptionsMonths": null
    }
  ]
}
```

#### Header-Felder

| Feld | Typ | Beschreibung |
|---|---|---|
| `userId` | int | Mitarbeiter-ID |
| `orgUnitId` | int | OE-ID |
| `year` | int | Planjahr |
| `yearWorkHours` | int | Jahres-Arbeitsstunden (z.B. 1500) |
| `hourlyRateFltValueMix` | float | Stundensatz in EUR (z.B. 159.08) |
| `inactiveMonths` | array | Monate mit Abwesenheit (leer wenn keine) |

#### PlanningException-Felder (pro EA-Zuordnung)

| Feld | Typ | Beschreibung |
|---|---|---|
| `developementOrderId` | int | EA-interne ID |
| `number` | string | EA-Nummer (z.B. `"0038004"`) |
| `description` | string | EA-Nummer + Titel |
| `devOrderDescription` | string | Nur EA-Titel |
| `projectFamily` | string | Projektfamilie (z.B. `"MEB"`) |
| `projectFamilyId` | int | Projektfamilien-ID |
| `projectFamilyActive` | bool | Projektfamilie aktiv? |
| `devOrderActive` | bool | EA aktiv? |
| `from` | datetime | EA-Startdatum |
| `until` | datetime | EA-Enddatum |
| `planAmmount` | float | Planbetrag gesamt (EUR) |
| `internalCalc` | float | Eigenleistungs-Kalkulation (EUR) |
| `externalCalc` | float | Fremdleistungs-Kalkulation (EUR) |
| `pzActual` | float | Planungsziel Ist (vermutlich 0–100) |
| `percentInJan` … `percentInDec` | float | **Prozent-Anteil pro Monat** (0.0–100.0) |
| `notPermittedMonths` | int[]? | Monate ohne Buchungsrecht |
| `bookingRightsExceptionsMonths` | int[] | Monate mit Buchungsrechts-Exception (1=Jan … 12=Dez) |
| `idxWorkPlanning` | int? | Arbeitsplanungs-ID (oft null) |
| `plannedPositionId` | int? | ID der geplanten Position |

> **Hinweis:** Die Summe aller `percentIn*`-Felder über alle EAs eines Mitarbeiters sollte pro Monat 100% ergeben.

> **Hinweis:** Felder wie `bookingRightsExceptionsMonths: [2,3,...,12]` zeigen an, dass für Monate Feb–Dez keine Buchungsrechtsbestätigung vorliegt — die Zelle wird in der UI **orange** dargestellt.

---

### 3.9 Planungsdaten pro Position

```
GET /ek/api/PlanningException/GetPlanningExceptionsForPlannedPosition?plannedPositionId={id}&year={year}&orgUnitId={orgUnitId}
```

> **Wissenslücke:** Nicht getestet. Vermutlich ähnliche Struktur wie `GetPlanningExceptionsForUser`, aber für eine einzelne Position.

---

### 3.10 Abwesenheitsgründe

```
GET /ek/api/PlanningException/GetInactiveMonthReasons
```

**Response:**

```json
[
  { "inactiveMonthReasonId": 1, "inactiveMonthReasonName": "OE-Wechsel", "inactiveMonthReasonOrder": 1 },
  { "inactiveMonthReasonId": 2, "inactiveMonthReasonName": "Elternzeit", "inactiveMonthReasonOrder": 2 },
  { "inactiveMonthReasonId": 3, "inactiveMonthReasonName": "Langzeitkrank (> 6 Wochen)", "inactiveMonthReasonOrder": 3 },
  { "inactiveMonthReasonId": 4, "inactiveMonthReasonName": "Freistellung", "inactiveMonthReasonOrder": 4 },
  { "inactiveMonthReasonId": 6, "inactiveMonthReasonName": "Nichtstreicher", "inactiveMonthReasonOrder": 6 },
  { "inactiveMonthReasonId": 7, "inactiveMonthReasonName": "ATZ/Rente", "inactiveMonthReasonOrder": 7 },
  { "inactiveMonthReasonId": 8, "inactiveMonthReasonName": "Ausland", "inactiveMonthReasonOrder": 8 },
  { "inactiveMonthReasonId": 5, "inactiveMonthReasonName": "Sonstiges", "inactiveMonthReasonOrder": 99 }
]
```

---

### 3.11 Arbeitsrollen-Planung

```
GET /ek/api/WorkRolePlan?orgUnitId={orgUnitId}
```

**Response:** Matrix von Arbeitsrollen × Mitarbeiter.

```json
{
  "orgUnitId": 161,
  "rolesPlanningForUser": [
    {
      "workRoleDto": { "idxWorkRole": 1, "strWorkRoleName": "ÄnderungsmanagerIn" },
      "userPlans": { "1056": ..., "1052": ... }
    }
  ]
}
```

> **Wissenslücke:** Die Struktur innerhalb von `userPlans` ist nicht detailliert analysiert (71KB Response). Enthält vermutlich Stunden- oder Prozent-Zuordnungen pro Rolle und Mitarbeiter.

---

### 3.12 Neue Planungsdaten abrufen

```
GET /ek/api/NewDataForPlanning?orgUnitId={orgUnitId}&year={year}&devOrderNbr={nr}&projFamily={pf}
```

**Response:** 204 No Content (im Test ohne `devOrderNbr`/`projFamily`-Parameter). Liefert vermutlich verfügbare EAs für Neuzuordnungen.

---

### 3.13 Rollen & Berechtigungen

```
GET /ek/api/Role/GetCurrentUserRoles
```

**Response:** Rollen des eingeloggten Users (Struktur nicht dokumentiert).

---

### 3.14 Sonstige Utility-Endpunkte

| Endpunkt | Beschreibung |
|---|---|
| `GET /ek/api/DBVersion` | Datenbank-Version |
| `GET /ek/api/Utility/GetSupportMail` | Support-E-Mail |
| `GET /ek/api/Utility/GetInstanceDescriptionHeader` | Instanz-Beschreibung |
| `GET /ek/api/Utility/GetCurrentDate` | Server-Datum |
| `GET /ek/api/BtlDefaultData` | BTL-Standard-Daten |

---

## 4. Schreib-Endpunkte (POST / PUT / DELETE) — Aus JS-Quellcode

Die folgenden Endpunkte wurden durch Analyse des Angular-JavaScript-Bundles (`chunk-RRWMWKJR.js`, 584KB) identifiziert. **Die exakten URL-Pfade und Request-Bodies sind noch nicht verifiziert**, da die URLs im minifizierten Code dynamisch zusammengebaut werden.

### 4.1 Wochenstunden anlegen (POST)

**Service-Methode:** `EmployeeHoursClient.post(id, hours, year, orgUnit)`

Legt Wochenstunden für einen Mitarbeiter an.

**Vermutete URL:**
```
POST /ek/api/EmployeeHours
```

**Vermuteter Request-Body:**
```json
{
  "idxUser": 1056,
  "hoursPerWeek": 40.0,
  "year": 2026,
  "orgUnitId": 161
}
```

> **Wissenslücke:** Exakte URL und Request-Body nicht verifiziert. Muss per Browser-DevTools (Network-Tab) oder Playwright-Interception bei einer Schreiboperation abgefangen werden.

---

### 4.2 Wochenstunden ändern (PUT)

**Service-Methode:** `EmployeeHoursClient.put(id, hours, year, orgUnit)`

Ändert die Wochenstunden eines Mitarbeiters.

**Vermutete URL:**
```
PUT /ek/api/EmployeeHours
```

> **Wissenslücke:** Wie 4.1 — nicht verifiziert.

---

### 4.3 Planungsposition aktualisieren (Monats-Prozente)

**Service-Methode:** `EmployeeHoursClient.updatePlannedPosition(posId, year, param3, param4, param5)`

Wird dreifach genutzt — die drei Parameter scheinen drei verschiedene Update-Szenarien abzudecken:

1. `updatePlannedPosition(posId, year, newValue, null, null)` — vermutlich Prozent-Update
2. `updatePlannedPosition(posId, year, null, newValue, null)` — vermutlich anderes Feld
3. `updatePlannedPosition(posId, year, null, null, moment(...))` — vermutlich Datums-Update

> **Wissenslücke:** Exakte Semantik der drei Parameter ist unbekannt. Muss durch Abfangen eines Cell-Edit-Events in der UI geklärt werden.

---

### 4.4 Planungsausnahmen aktualisieren

**Service-Methode:** `PlanningExceptionClient.updatePlanningExceptions(planningException)`

Aktualisiert Abwesenheiten / inaktive Monate für einen Mitarbeiter.

> **Wissenslücke:** HTTP-Methode (POST oder PUT) und Request-Body-Format unbekannt.

---

### 4.5 Neue EA-Zuordnung anlegen

**Service-Methode:** `NewDataForPlanningClient.insertData(orgUnitId, userId, plannedPositionId, year, devOrders)`

Ordnet einem Mitarbeiter neue Entwicklungsaufträge zu.

**Vermutete URL:**
```
POST /ek/api/NewDataForPlanning
```

> **Wissenslücke:** Format von `devOrders` (Array von IDs? Objekt?) ist unbekannt.

---

### 4.6 Planungsdaten löschen

**Service-Methode:** `NewDataForPlanningClient.deleteData(data)`

Entfernt eine EA-Zuordnung.

**Vermutete URL:**
```
DELETE /ek/api/NewDataForPlanning
```

> **Wissenslücke:** Was ist `data`? Einzelne ID oder Objekt?

---

### 4.7 Bulk-Planungsübertragung

**Service-Methode:** `NewDataForPlanningClient.postBulkPlanningTransfers(sourceYear, targetYear, orgUnit, transfers)`

Überträgt Planungsdaten von einem Jahr ins andere (Bulk-Operation).

> **Wissenslücke:** Struktur von `transfers` und exakte URL unbekannt.

---

### 4.8 Bulk-EA-Validierung

**Service-Methode:** `NewDataForPlanningClient.validateBulkDevOrders(bulkList, selectedOU, selectedYear, idxUser, plannedPositionId)`

Validiert eine Liste von EAs zur Zuordnung.

> **Wissenslücke:** Vollständige Parameterliste und URL unbekannt.

---

### 4.9 Validierung der MA-Planung

**UI-Button:** "Validieren" (wird aktiv wenn ein MA selektiert ist)

> **Wissenslücke:** Der Validierungs-Endpunkt (vermutlich `POST /ek/api/Validation/...`) ist nicht identifiziert. In der UI setzt er `isValidated=true` und `dateValidated`.

---

## 5. Zusammenfassung: Wissenslücken

### Kritisch (für Lese-Implementierung)

| # | Lücke | Lösungsansatz |
|---|---|---|
| L1 | **OrgUnit-ID-Mapping**: Wie bekommt man die `orgUnitId` für beliebige OEs? | Admin-Endpunkt suchen oder aus BTL/InfoDepartments ableiten |
| L2 | **planingStatus Enum**: Was bedeuten die Werte 0, 1, 2, ...? | In der UI verschiedene Status erzeugen und API-Response vergleichen |
| ~~L3~~ | ~~**Export-Endpunkt Timeout**~~ | **Gelöst:** Funktioniert mit `-OutFile` und Timeout ≥300s. Liefert JSON (379KB für EKEK/1). |

### Kritisch (für Schreib-Implementierung)

| # | Lücke | Lösungsansatz |
|---|---|---|
| S1 | **Exakte URLs und Request-Bodies** aller POST/PUT/DELETE-Endpunkte | Browser-DevTools oder Playwright-Request-Interception bei Schreibvorgängen |
| S2 | **CSRF/Antiforgery-Token**: App nutzt `/helpapi/antiforgery/token` — braucht man den auch für EL-Endpunkte? | Schreib-Request ohne Token versuchen, Fehler analysieren |
| S3 | **`updatePlannedPosition`**: Semantik der drei Parameter | Cell-Edit in der UI abfangen und Request analysieren |
| S4 | **Rollen-Check**: Welche Rolle braucht man zum Schreiben? | `/ek/api/Role/GetCurrentUserRoles` auswerten |

### Nice-to-have

| # | Lücke | Lösungsansatz |
|---|---|---|
| N1 | `WorkRolePlan`-Detailstruktur (71KB) | Response vollständig parsen |
| N2 | Struktur der Felder `former` und `future` in EmployeeHours | Tab "Ehemalige Positionen" in der UI nutzen und API-Call abfangen |
| N3 | `NewDataForPlanning` Response bei gültigen Parametern | Mit konkreter `devOrderNbr` und `projFamily` testen |
| N4 | Endpunkt für Forecast/Vorausschau (`/ek/api/Forecast/...`) | Separate VSI-Seite analysieren |

---

## 6. Empfohlener Implementierungsplan

### Phase 1: Lese-API (Read-only)

1. **OrgUnit-Mapping klären** (Lücke L1)
   - `BasicELData` Response für verschiedene User analysieren
   - Alternativ: Hardcoded Mapping für EKEK/1 (161) als Start

2. **Mitarbeiter-Übersicht abrufen**
   - `GET /ek/api/EmployeeHours?orgUnitId=161&year=2026`
   - Alle `idxUser`-Werte sammeln

3. **Planungsdaten pro MA laden**
   - `GET /ek/api/PlanningException/GetPlanningExceptionsForUser?userId={id}&year=2026&orgUnitId=161`
   - **Achtung:** Langsam (>30s/MA) — ggf. parallelisieren oder cachen
   - Enthält: EA-Zuordnungen mit monatlichen Prozent-Werten

4. **Auswertungen erstellen**
   - Summe der Prozent-Werte pro MA und Monat (sollte ≈100%)
   - Über-/Unterplanung erkennen
   - EAs ohne Buchungsrecht markieren (`bookingRightsExceptionsMonths`)
   - Planbeträge aggregieren

### Phase 2: Schreib-API

1. **Request-Interception** einrichten (Playwright oder Browser-DevTools)
2. **Einen Monats-Prozent-Wert ändern** in der UI und den Request abfangen
3. **URLs und Bodies** für alle Schreib-Operationen dokumentieren
4. **CSRF-Token-Handling** implementieren, falls nötig
5. **Automatisierte Planung** umsetzen

---

## 7. Referenz: Alle entdeckten API-Endpunkte

### EL-spezifisch (verifiziert)

| Methode | Pfad | Status |
|---|---|---|
| GET | `/ek/api/BasicELData` | ✅ 200 OK |
| GET | `/ek/api/BasicELData/CheckExistingHourlyCostRate?intYear={y}&idxOrgUnit={ou}` | ✅ 200 OK |
| GET | `/ek/api/BasicELData/CheckExistingYearlyWorkingHours?intYear={y}` | ✅ 200 OK |
| GET | `/ek/api/EmployeeHours?orgUnitId={ou}&year={y}` | ✅ 200 OK |
| GET | `/ek/api/EmployeeHours/GetUsersHistory?idxOrgUnit={ou}` | ✅ 200 OK |
| GET | `/ek/api/EmployeeHours/GetFuturePositions?orgUnitId={ou}&year={y}` | ✅ 200 OK |
| GET | `/ek/api/EmployeeHours/GetEmployeesExport?orgUnitId={ou}&year={y}` | ✅ 200 OK (langsam, ~3 Min, JSON 379KB) |
| GET | `/ek/api/PlanningException/GetInactiveMonthReasons` | ✅ 200 OK |
| GET | `/ek/api/PlanningException/GetPlanningExceptionsForUser?userId={u}&year={y}&orgUnitId={ou}` | ✅ 200 OK (langsam) |
| GET | `/ek/api/WorkRolePlan?orgUnitId={ou}` | ✅ 200 OK |
| GET | `/ek/api/NewDataForPlanning?orgUnitId={ou}&year={y}` | ✅ 204 No Content |

### EL-spezifisch (aus JS, nicht verifiziert)

| Methode | Service-Call | Vermuteter Pfad |
|---|---|---|
| POST | `EmployeeHoursClient.post(...)` | `/ek/api/EmployeeHours` |
| PUT | `EmployeeHoursClient.put(...)` | `/ek/api/EmployeeHours` |
| PUT | `EmployeeHoursClient.updatePlannedPosition(...)` | `/ek/api/EmployeeHours/UpdatePlannedPosition` |
| POST/PUT | `PlanningExceptionClient.updatePlanningExceptions(...)` | `/ek/api/PlanningException` |
| POST | `NewDataForPlanningClient.insertData(...)` | `/ek/api/NewDataForPlanning` |
| DELETE | `NewDataForPlanningClient.deleteData(...)` | `/ek/api/NewDataForPlanning` |
| POST | `NewDataForPlanningClient.postBulkPlanningTransfers(...)` | `/ek/api/NewDataForPlanning/BulkTransfer` |
| POST | `NewDataForPlanningClient.validateBulkDevOrders(...)` | `/ek/api/NewDataForPlanning/ValidateBulk` |

### Allgemein (verifiziert)

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/ek/api/Year` | Verfügbare Jahre |
| GET | `/ek/api/Role/GetCurrentUserRoles` | User-Rollen |
| GET | `/ek/api/DBVersion` | DB-Version |
| GET | `/ek/api/Utility/GetCurrentDate` | Server-Datum |
| GET | `/ek/api/BtlDefaultData` | BTL-Defaults |

---

## 8. Bekannte API-Controller (aus JS-Bundle)

Die Angular-App nutzt folgende HTTP-Client-Klassen:

| Client | Verwendung |
|---|---|
| `EmployeeHoursClient` | Mitarbeiter-Stunden, Positionen, Export |
| `BasicELDataClient` | OE-Basisdaten, Stundensatz-Checks |
| `PlanningExceptionClient` | Planungsdaten, Abwesenheiten |
| `NewDataForPlanningClient` | EA-Zuordnungen, Bulk-Transfers |
| `WorkRolePlanClient` | Arbeitsrollen-Matrix |
| `ValidationClient` | Validierung |
| `BtlQuerieStateClient` | BTL-Query-Status |
| `DBVersionClient` | DB-Version |
| `CurrentUserClient` | Eingeloggter User |
| `MenuClient` | Menü-Konfiguration |
| `ProfileClient` | User-Profil |
| `InActiveMonthClient` | Inaktive Monate |
| `LoggingClient` | Logging |
| `ForecastClient` | Vorausschau (VSI) |

---

## 9. Verwandte Skills & Endpunkte

Die folgenden BPLUS-NG APIs sind bereits in bestehenden Skills dokumentiert und können ergänzend genutzt werden:

| Skill | API-Endpunkt | Relevanz für EL |
|---|---|---|
| `skill-bplus-export` | `GET /ek/api/Btl/GetAll?year={y}` | EA-Nummern, Beträge, Status |
| `skill-ea-uebersicht` | `GET /ek/api/DevOrder/GetAll?year={y}` | EA-Stammdaten, Laufzeiten |
| `skill-stundensaetze` | HTML-Scraping von InfoDepartments | Stundensätze (alternativ zu BasicELData) |
| `skill-ua-leiter` | HTML-Scraping von InfoDepartments | OE-Leiter |
