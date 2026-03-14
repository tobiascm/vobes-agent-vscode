<#
.SYNOPSIS
    BPLUS-NG Entwicklungsauftraege (EA) Export per REST-API.

.DESCRIPTION
    Laedt die EA-Uebersicht (DevOrders) ueber die BPLUS-NG REST-API als JSON
    und exportiert die Daten als LLM-optimiertes CSV. Nutzt Windows-Authentifizierung (SSO).

    LLM-Optimierungen:
    - Komma als Delimiter, Punkt als Dezimalzeichen
    - Alle Strings getrimmt (kein trailing whitespace)
    - Datumsfelder nur als Datum (ohne Uhrzeit)
    - UTF-8 ohne BOM
    - snake_case Spaltennamen

.PARAMETER Year
    Das Jahr fuer den Export (Default: aktuelles Jahr).

.PARAMETER ActiveOnly
    Nur aktive EAs exportieren (Default: $true).

.PARAMETER ProjectFamily
    ProjektFamilie filtern, z.B. "A_BEV". Ohne Filter werden alle exportiert.

.PARAMETER OutputPath
    Zielpfad fuer die CSV-Datei. Default: userdata\bplus\YYYYMMDD_EA_Uebersicht.csv

.PARAMETER BaseUrl
    Basis-URL der BPLUS-NG Instanz.

.EXAMPLE
    .\export_ea_uebersicht.ps1
    # Alle aktiven EAs, aktuelles Jahr

.EXAMPLE
    .\export_ea_uebersicht.ps1 -ActiveOnly $false
    # Alle EAs inkl. inaktive

.EXAMPLE
    .\export_ea_uebersicht.ps1 -ProjectFamily "A_BEV" -Year 2025
#>

param(
    [int]$Year = (Get-Date).Year,
    [bool]$ActiveOnly = $true,
    [string]$ProjectFamily = "",
    [string]$OutputPath = "",
    [string]$BaseUrl = "https://bplus-ng-mig.r02.vwgroup.com",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# --- 0. Cache pruefen (nur neu laden wenn aelter als 1 Monat) ---
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$destDir = Join-Path $workspaceRoot "userdata\bplus"
if (!(Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
$pfSuffix = if ($ProjectFamily -ne "") { "_$ProjectFamily" } else { "" }
$activeTag = if ($ActiveOnly) { "_aktiv" } else { "" }

if ($OutputPath -eq "") {
    $OutputPath = Join-Path $destDir "$(Get-Date -Format 'yyyyMMdd')_EA_Uebersicht$pfSuffix$activeTag.csv"
}

if (-not $Force) {
    $pattern = "*_EA_Uebersicht$pfSuffix$activeTag.csv"
    $existing = Get-ChildItem -Path $destDir -Filter $pattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($existing -and $existing.LastWriteTime -gt (Get-Date).AddMonths(-1)) {
        Write-Host "Cache aktuell: $($existing.FullName) ($('{0:dd.MM.yyyy}' -f $existing.LastWriteTime)). Ueberspringe Download. (-Force zum Erzwingen)"
        exit 0
    }
}

# --- 1. API-Abruf ---
$apiUrl = "$BaseUrl/ek/api/DevOrder/GetAll?year=$Year"
Write-Host "Abrufe: $apiUrl"

try {
    $response = Invoke-RestMethod -Uri $apiUrl -UseDefaultCredentials
} catch {
    Write-Error "API-Abruf fehlgeschlagen: $_"
    exit 1
}

Write-Host "Empfangen: $($response.Count) Datensaetze (Jahr $Year)"

# --- 2. Filtern ---
$filtered = $response

if ($ActiveOnly) {
    $filtered = $filtered | Where-Object { $_.active -eq $true }
    Write-Host "Gefiltert (ActiveOnly=$ActiveOnly): $($filtered.Count) aktive EAs"
}

if ($ProjectFamily -ne "") {
    $filtered = $filtered | Where-Object { $_.assignedProjectFamily -eq $ProjectFamily }
    Write-Host "Gefiltert (ProjectFamily=$ProjectFamily): $($filtered.Count) EAs"
}

if ($filtered.Count -eq 0) {
    Write-Warning "Keine Datensaetze nach Filterung. Export abgebrochen."
    exit 0
}

# --- 3. Daten transformieren (LLM-optimiert) ---
$transformed = $filtered | ForEach-Object {
    # Datumsfelder: nur Datum (ohne Uhrzeit)
    $dateFrom  = if ($_.dateFrom)  { ($_.dateFrom  -split 'T')[0] } else { '' }
    $dateUntil = if ($_.dateUntil) { ($_.dateUntil -split 'T')[0] } else { '' }
    $sop       = if ($_.sop)       { ($_.sop       -split 'T')[0] } else { '' }

    [PSCustomObject]@{
        ea_number        = "$($_.number)".Trim()
        title            = "$($_.developmentOrderName)".Trim()
        active           = $_.active
        date_from        = $dateFrom
        date_until       = $dateUntil
        sop              = $sop
        project_family   = "$($_.assignedProjectFamily)".Trim()
        controller       = "$($_.controller)".Trim()
        hierarchy        = "$($_.hierarchy)".Trim()
    }
} | Sort-Object ea_number

# --- 4. Ausgabepfad (bereits in Schritt 0 bestimmt) ---

# --- 5. CSV-Export (UTF-8 ohne BOM, Komma-Delimiter) ---
$csvContent = $transformed |
    Select-Object ea_number, title, active, date_from, date_until, sop, project_family, controller, hierarchy |
    ConvertTo-Csv -NoTypeInformation -Delimiter ","

[System.IO.File]::WriteAllLines($OutputPath, $csvContent, (New-Object System.Text.UTF8Encoding $false))

$count = if ($transformed -is [array]) { $transformed.Count } else { if ($null -ne $transformed) { 1 } else { 0 } }
Write-Host "Exportiert: $count EAs -> $OutputPath"
Write-Host "Fertig."
