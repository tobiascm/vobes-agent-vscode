<#
.SYNOPSIS
    BPLUS-NG Export per REST-API (ohne Playwright/Browser).

.DESCRIPTION
    Laedt die Konzeptuebersicht (BTL) direkt ueber die BPLUS-NG REST-API als JSON
    und exportiert die Daten als LLM-optimiertes CSV. Nutzt Windows-Authentifizierung (SSO).

    LLM-Optimierungen:
    - Komma als Delimiter, Punkt als Dezimalzeichen
    - Alle Strings getrimmt (kein trailing whitespace)
    - Ein kombinierter Klartext-Status statt zwei Spalten
    - Newlines in pbmText durch " | " ersetzt
    - Ganzzahl-Werte (keine Nachkommastellen)
    - UTF-8 ohne BOM
    - snake_case Spaltennamen

.PARAMETER Year
    Das Jahr fuer den Export (Default: aktuelles Jahr).

.PARAMETER OrgUnit
    Organisationseinheit filtern, z.B. "EKEK/1" (Default: EKEK/1).

.PARAMETER ExcludeArchived
    Archivierte Vorgaenge ausschliessen (Default: $true).

.PARAMETER OutputPath
    Zielpfad fuer die CSV-Datei. Default: userdata\bplus\YYYYMMDD_BPlus_Export_<OrgUnit>.csv

.PARAMETER BaseUrl
    Basis-URL der BPLUS-NG Instanz.

.EXAMPLE
    .\export_bplus_api.ps1
    # Exportiert EKEK/1, aktuelles Jahr, ohne Archivierte

.EXAMPLE
    .\export_bplus_api.ps1 -Year 2025 -OrgUnit "EKEK/2"

.EXAMPLE
    .\export_bplus_api.ps1 -ExcludeArchived $false
    # Alle Vorgaenge inkl. Archivierte
#>

param(
    [int]$Year = (Get-Date).Year,
    [string]$OrgUnit = "EKEK/1",
    [bool]$ExcludeArchived = $true,
    [string]$OutputPath = "",
    [string]$BaseUrl = "https://bplus-ng-mig.r02.vwgroup.com"
)

$ErrorActionPreference = "Stop"

# --- 1. API-Abruf ---
$apiUrl = "$BaseUrl/ek/api/Btl/GetAll?year=$Year"
Write-Host "Abrufe: $apiUrl"

try {
    $response = Invoke-RestMethod -Uri $apiUrl -UseDefaultCredentials
} catch {
    Write-Error "API-Abruf fehlgeschlagen: $_"
    exit 1
}

Write-Host "Empfangen: $($response.Count) Datensaetze (alle OEs, Jahr $Year)"

# --- 2. Filtern ---
$filtered = $response | Where-Object { $_.orgUnitName -eq $OrgUnit }

if ($ExcludeArchived) {
    $filtered = $filtered | Where-Object { $_.workFlowStatus -ne 'WF_Archived' }
}

Write-Host "Gefiltert ($OrgUnit, ExcludeArchived=$ExcludeArchived): $($filtered.Count) Datensaetze"

if ($filtered.Count -eq 0) {
    Write-Warning "Keine Datensaetze nach Filterung. Export abgebrochen."
    exit 0
}

# --- 3. Gesamtwert berechnen ---
$summe = ($filtered | Measure-Object plannedValue -Sum).Sum
Write-Host "Gesamtwert: $($summe.ToString('N2')) EUR"

# --- 4. Status-Mapping (API-Code → Klartext) ---
$statusMap = @{
    'WF_Created'            = '01_In Erstellung'
    'WF_In_process_BM_Team' = '06_In Bearbeitung BM-Team'
    'WF_In_Planen_BM'       = '07_In Planen-BM'
    'WF_Rejected'           = '97_Abgelehnt'
    'WF_Canceled'           = '98_Storniert'
    'WF_Archived'           = '99_Archiviert'
}

# --- 5. Daten transformieren (LLM-optimiert) ---
$transformed = $filtered | ForEach-Object {
    # Kombinierten Klartext-Status erzeugen
    $baseStatus = if ($statusMap.ContainsKey($_.workFlowStatus)) { $statusMap[$_.workFlowStatus] } else { $_.workFlowStatus }
    $displayStatus = if ($_.workFlowStatus -eq 'WF_In_Planen_BM' -and $_.status) {
        "${baseStatus}: $($_.status.Trim())"
    } elseif ($_.status) {
        "${baseStatus}: $($_.status.Trim())"
    } else {
        $baseStatus
    }

    # Wert als Ganzzahl (Punkt als Dezimalzeichen → runden → int)
    $valStr = $_.plannedValue -replace ',', '.'
    $valInt = [int][math]::Round([double]$valStr)

    # Newlines in pbmText durch " | " ersetzen, trimmen
    $cleanText = if ($_.pbmText) { ($_.pbmText -replace '\r?\n', ' | ').Trim() -replace '\s*\|\s*$', '' -replace '\|\s*\|', '|' } else { '' }

    # projektfamilie: "KEINE" → leer
    $projFam = if ($_.projektfamilie -eq 'KEINE') { '' } else { $_.projektfamilie }

    # Datumsfelder: nur Datum (ohne Uhrzeit)
    $lastUpd = if ($_.lastUpdated) { ($_.lastUpdated -split 'T')[0] } else { '' }
    $targDate = if ($_.targetDate) { ($_.targetDate -split 'T')[0] } else { '' }

    [PSCustomObject]@{
        concept          = $_.concept
        ea               = "$($_.eaTitel)".Trim()
        title            = "$($_.title)".Trim()
        status           = $displayStatus
        planned_value    = $valInt
        org_unit         = $_.orgUnitName
        company          = "$($_.company)".Trim()
        creator          = "$($_.creatorName)".Trim()
        bm_number        = $_.bmNumber
        az_number        = $_.azNumber
        projektfamilie   = $projFam
        dev_order        = $_.devOrder
        bm_text          = $cleanText
        last_updated     = $lastUpd
        category         = $_.category
        cost_type        = "$($_.costType)".Trim()
        quantity         = $_.quantity
        unit             = "$($_.unity)".Trim()
        supplier_number  = $_.supplierNumber
        first_signature  = "$($_.firstSignature)".Trim()
        second_signature = "$($_.secondSignature)".Trim()
        target_date      = $targDate
    }
}

# --- 6. Ausgabepfad bestimmen ---
if (-not $OutputPath) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $workspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
    $destDir = Join-Path $workspaceRoot "userdata\bplus"
    if (!(Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    $orgSafe = $OrgUnit -replace '/', ''
    $OutputPath = Join-Path $destDir "$(Get-Date -Format 'yyyyMMdd')_BPlus_Export_$orgSafe.csv"
}

# --- 7. CSV-Export (UTF-8 ohne BOM, Komma-Delimiter) ---
$csvContent = $transformed |
    Select-Object concept, ea, title, status, planned_value, org_unit, company, creator, bm_number, az_number, projektfamilie, dev_order, bm_text, last_updated, category, cost_type, quantity, unit, supplier_number, first_signature, second_signature, target_date |
    ConvertTo-Csv -NoTypeInformation -Delimiter ","

# UTF-8 ohne BOM (kompatibel mit PS 5.x und 7.x)
[System.IO.File]::WriteAllLines($OutputPath, $csvContent, (New-Object System.Text.UTF8Encoding $false))

Write-Host "Exportiert nach: $OutputPath"
Write-Host "Fertig."
