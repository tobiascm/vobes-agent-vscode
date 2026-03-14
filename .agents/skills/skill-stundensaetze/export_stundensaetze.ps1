<#
.SYNOPSIS
    BPLUS-NG Stundensaetze Export per Web-Scraping.

.DESCRIPTION
    Laedt die Stundensaetze (InfoDepartments) aus BPLUS-NG, extrahiert die
    eingebetteten JSON-Daten aus der HTML-Seite und exportiert sie als CSV.
    Nutzt Windows-Authentifizierung (SSO).

    CSV-Format:
    - Komma als Delimiter, Punkt als Dezimalzeichen
    - UTF-8 ohne BOM
    - snake_case Spaltennamen

.PARAMETER Year
    Das Jahr fuer den Export (Default: aktuelles Jahr).

.PARAMETER OrgUnit
    Optional: OE filtern, z.B. "EKEK/1". Ohne Filter werden alle OEs exportiert.

.PARAMETER OutputPath
    Zielpfad fuer die CSV-Datei. Default: userdata\bplus\YYYYMMDD_Stundensaetze[_OE].csv

.PARAMETER BaseUrl
    Basis-URL der BPLUS-NG Instanz.

.EXAMPLE
    .\export_stundensaetze.ps1
    # Exportiert alle OEs, aktuelles Jahr

.EXAMPLE
    .\export_stundensaetze.ps1 -Year 2025 -OrgUnit "EKEK/1"
#>

param(
    [int]$Year = (Get-Date).Year,
    [string]$OrgUnit = "",
    [string]$OutputPath = "",
    [string]$BaseUrl = "https://bplus-ng-mig.r02.vwgroup.com",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# --- 0. Cache pruefen (nur neu laden wenn aelter als 1 Monat) ---
$workspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$outDir = Join-Path $workspaceRoot "userdata\bplus"
if (!(Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
$suffix = if ($OrgUnit -ne "") { "_$($OrgUnit -replace '/', '-')" } else { "" }

if ($OutputPath -eq "") {
    $OutputPath = Join-Path $outDir "$(Get-Date -Format 'yyyyMMdd')_Stundensaetze$suffix.csv"
}

if (-not $Force) {
    $pattern = "*_Stundensaetze$suffix.csv"
    $existing = Get-ChildItem -Path $outDir -Filter $pattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($existing -and $existing.LastWriteTime -gt (Get-Date).AddMonths(-1)) {
        Write-Host "Cache aktuell: $($existing.FullName) ($('{0:dd.MM.yyyy}' -f $existing.LastWriteTime)). Ueberspringe Download. (-Force zum Erzwingen)"
        exit 0
    }
}

# --- 1. HTML-Seite abrufen ---
$pageUrl = "$BaseUrl/ek-reports/InfoDepartments.aspx?y=$Year"
Write-Host "Abrufe: $pageUrl"

try {
    $response = Invoke-WebRequest -Uri $pageUrl -UseDefaultCredentials -UseBasicParsing -TimeoutSec 30
} catch {
    Write-Error "API-Abruf fehlgeschlagen: $_"
    exit 1
}

if ($response.StatusCode -ne 200) {
    Write-Error "Unerwarteter HTTP-Status: $($response.StatusCode)"
    exit 1
}

# --- 2. JSON-Daten aus HTML extrahieren ---
$html = $response.Content

# Das Tabulator-Data-Array liegt zwischen "data": [ ... ]});
$dataMatch = [regex]::Match($html, '"data":\s*(\[[\s\S]*?\])\s*\}\);')
if (-not $dataMatch.Success) {
    Write-Error "Konnte JSON-Daten nicht aus der Seite extrahieren. Seitenstruktur hat sich moeglicherweise geaendert."
    exit 1
}

$jsonData = $dataMatch.Groups[1].Value
$records = $jsonData | ConvertFrom-Json

Write-Host "$($records.Count) Datensaetze geladen."

# --- 3. In strukturierte Objekte umwandeln und aggregieren (1 Zeile pro OE) ---
$mapped = $records | ForEach-Object {
    $rate = $_.col7 -replace '\.', '' -replace ',', '.'
    [PSCustomObject]@{
        jahr        = $_.col1.Trim()
        kst         = $_.col2.Trim()
        oe          = $_.col3.Trim()
        stundensatz = [decimal]$rate
    }
} | Sort-Object oe, kst | Select-Object jahr, kst, oe, stundensatz -Unique

# --- 4. Optional: OE filtern ---
if ($OrgUnit -ne "") {
    $mapped = $mapped | Where-Object { $_.oe -eq $OrgUnit }
    Write-Host "Gefiltert auf OE '$OrgUnit': $($mapped.Count) Datensaetze."
}

# --- 5. CSV-Ausgabe ---

# CSV mit Punkt-Dezimalzeichen schreiben
$sb = [System.Text.StringBuilder]::new()
[void]$sb.AppendLine("jahr,kst,oe,stundensatz")

foreach ($row in $mapped) {
    $line = "$($row.jahr),$($row.kst),$($row.oe),$($row.stundensatz)"
    [void]$sb.AppendLine($line)
}

[System.IO.File]::WriteAllText($OutputPath, $sb.ToString(), [System.Text.UTF8Encoding]::new($false))

$count = if ($mapped -is [array]) { $mapped.Count } else { 1 }
Write-Host "Exportiert: $count Datensaetze -> $OutputPath"
