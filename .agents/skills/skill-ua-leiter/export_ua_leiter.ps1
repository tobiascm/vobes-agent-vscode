<#
.SYNOPSIS
    BPLUS-NG Unterabteilungsleiter (UA-Leiter) Export.

.DESCRIPTION
    Laedt die Abteilungsdaten (InfoDepartments) aus BPLUS-NG, filtert auf
    Leitungsfunktion (Leitung=1) und exportiert OE, Ebene, Mail als CSV.
    Nutzt Windows-Authentifizierung (SSO).

.PARAMETER Year
    Das Jahr fuer den Export (Default: aktuelles Jahr).

.PARAMETER OrgUnit
    Optional: OE filtern, z.B. "EKEK/1". Ohne Filter werden alle OEs exportiert.

.PARAMETER OutputPath
    Zielpfad fuer die CSV-Datei.

.PARAMETER BaseUrl
    Basis-URL der BPLUS-NG Instanz.

.EXAMPLE
    .\export_ua_leiter.ps1
    # Alle Leitungen, aktuelles Jahr

.EXAMPLE
    .\export_ua_leiter.ps1 -OrgUnit "EKEK"
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
    $OutputPath = Join-Path $outDir "$(Get-Date -Format 'yyyyMMdd')_UA_Leiter$suffix.csv"
}

if (-not $Force) {
    $pattern = "*_UA_Leiter$suffix.csv"
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
    Write-Error "Abruf fehlgeschlagen: $_"
    exit 1
}

if ($response.StatusCode -ne 200) {
    Write-Error "Unerwarteter HTTP-Status: $($response.StatusCode)"
    exit 1
}

# --- 2. JSON-Daten aus HTML extrahieren ---
$html = $response.Content
$dataMatch = [regex]::Match($html, '"data":\s*(\[[\s\S]*?\])\s*\}\);')
if (-not $dataMatch.Success) {
    Write-Error "Konnte JSON-Daten nicht aus der Seite extrahieren."
    exit 1
}

$records = $dataMatch.Groups[1].Value | ConvertFrom-Json
Write-Host "$($records.Count) Datensaetze geladen."

# --- 3. Auf Leitung=1 filtern ---
$leaders = $records | Where-Object { $_.col6 -eq "1" } | ForEach-Object {
    [PSCustomObject]@{
        oe    = $_.col3.Trim()
        ebene = $_.col4.Trim()
        mail  = $_.col5.Trim()
    }
} | Sort-Object oe

# --- 4. Optional: OE filtern ---
if ($OrgUnit -ne "") {
    $leaders = $leaders | Where-Object { $_.oe -eq $OrgUnit }
    Write-Host "Gefiltert auf OE '$OrgUnit': $($leaders.Count) Eintraege."
}

# --- 5. CSV-Ausgabe ---

$sb = [System.Text.StringBuilder]::new()
[void]$sb.AppendLine("oe,ebene,mail")

foreach ($row in $leaders) {
    [void]$sb.AppendLine("$($row.oe),$($row.ebene),$($row.mail)")
}

[System.IO.File]::WriteAllText($OutputPath, $sb.ToString(), [System.Text.UTF8Encoding]::new($false))

$count = if ($leaders -is [array]) { $leaders.Count } else { if ($null -ne $leaders) { 1 } else { 0 } }
Write-Host "Exportiert: $count Leitungen -> $OutputPath"
