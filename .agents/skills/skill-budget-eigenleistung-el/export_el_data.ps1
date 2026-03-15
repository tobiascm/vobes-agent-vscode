<#
.SYNOPSIS
    BPLUS-NG Eigenleistung (EL) Export per REST-API mit Caching.

.DESCRIPTION
    Laden Eigenleistungsplanungsdaten direkt aus BPLUS-NG REST-API:
    - BasicELData, EmployeeHours, PlanningExceptions pro MA
    - DevOrder (EA-Stammdaten), BTL (Fremdleistung)
    
    Intelligentes Caching: 1 Tag Gültigkeit
    Timeout-Fallback: Bei Fehler → letzter erfolgreicher Export
    
    Sequentiell zum Testen (später: # TODO: PARALLEL mit PowerShell Jobs)

.PARAMETER Year
    Planjahr (Default: aktuelles Jahr).

.PARAMETER ForceRefresh
    Cache überschreiben, neu exportieren.

.PARAMETER BaseUrl
    BPLUS-NG Basis-URL.

.EXAMPLE
    .\export_el_data.ps1
    # Nutzt Cache oder importiert neu (EKEK/1, 2026)

.EXAMPLE
    .\export_el_data.ps1 -ForceRefresh
    # Ignoriert Cache, erzeugt neuen Export

.EXAMPLE
    .\export_el_data.ps1 -Year 2025
    # Historische Daten (2025)
#>

param(
    [int]$Year = (Get-Date).Year,
    [switch]$ForceRefresh = $false,
    [string]$BaseUrl = "https://bplus-ng-mig.r02.vwgroup.com"
)

$ErrorActionPreference = "Stop"

# --- Konfiguration ---
$OrgUnitId = 161
$OrgUnitName = "EKEK/1"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ScriptDir))
$TmpDir = Join-Path $WorkspaceRoot "userdata\tmp"
$LogsDir = Join-Path $WorkspaceRoot "userdata\tmp\logs"
$CacheDir = $TmpDir
$ConsolidatedFile = Join-Path $CacheDir "_el_consolidated_$Year.json"
$CacheCheckFile = Join-Path $CacheDir "_el_consolidated_$Year.cachetime"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogsDir "export_el_data_$Timestamp.log"

# Verzeichnisse erstellen
@($TmpDir, $LogsDir, $CacheDir) | ForEach-Object {
    if (!(Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}

# Logging-Funktion
function Write-Log {
    param([string]$Message, [bool]$IsError = $false)
    $logLine = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    if ($IsError) {
        Write-Host "[ERROR] $logLine" -ForegroundColor Red
    } else {
        Write-Host "[INFO] $logLine" -ForegroundColor Cyan
    }
    Add-Content -Path $LogFile -Value $logLine -Encoding UTF8
}

Write-Log "═══════════════════════════════════════════════════════"
Write-Log "EIGENLEISTUNG Export Start | Jahr: $Year | OE: $OrgUnitName"
Write-Log "Log-Datei: $LogFile"

# --- 1. Cache-Prüfung ---
$UsedCache = $false
if (!$ForceRefresh -and (Test-Path $ConsolidatedFile) -and (Test-Path $CacheCheckFile)) {
    $cacheTime = [datetime](Get-Content $CacheCheckFile)
    $cacheAge = (Get-Date) - $cacheTime
    $cacheValidDays = 1
    
    if ($cacheAge.TotalHours -lt 24) {
        Write-Log "CACHE FOUND (Alter: $([math]::Round($cacheAge.TotalHours, 1))h)"
        Write-Log "Cache gültig für weitere $([math]::Round(24 - $cacheAge.TotalHours, 1))h"
        $UsedCache = $true
    } else {
        Write-Log "CACHE VERALTET (älter als 24h) -> Neuer Export"
    }
} else {
    if ($ForceRefresh) {
        Write-Log "--ForceRefresh: Cache überschrieben"
    } else {
        Write-Log "KEIN CACHE VORHANDEN -> Neuer Export"
    }
}

if ($UsedCache) {
    Write-Log "CACHE-HIT! Nutze gespeicherte Daten"
    Write-Log "═══════════════════════════════════════════════════════"
    Write-Output $ConsolidatedFile
    exit 0
}

# --- 2. API-Abrufe (SEQUENTIELL zum Testen) ---
# TODO: PARALLEL - Die folgenden Calls können mit Start-Job parallelisiert werden
# z.B.: $jobs += Start-Job -ScriptBlock { Invoke-RestMethod ... }
# Dann: $jobs | Wait-Job | Receive-Job

$jsonFiles = @{}
$apiCalls = @(
    @{ Name = "BasicELData"; Url = "$BaseUrl/ek/api/BasicELData"; TimeoutSec = 10 },
    @{ Name = "EmployeeHours"; Url = "$BaseUrl/ek/api/EmployeeHours?orgUnitId=$OrgUnitId`&year=$Year"; TimeoutSec = 15 },
    @{ Name = "DevOrder"; Url = "$BaseUrl/ek/api/DevOrder/GetAll?year=$Year"; TimeoutSec = 20 },
    @{ Name = "Btl"; Url = "$BaseUrl/ek/api/Btl/GetAll?year=$Year"; TimeoutSec = 20 }
)

foreach ($call in $apiCalls) {
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        Write-Log "API-CALL: $($call.Name) (Timeout: $($call.TimeoutSec)s)"
        $response = Invoke-RestMethod -Uri $call.Url -UseDefaultCredentials -TimeoutSec $call.TimeoutSec -ErrorAction Stop
        $stopwatch.Stop()
        Write-Log "OK: $($call.Name) erfolgreich ($($stopwatch.ElapsedMilliseconds)ms)"
        $jsonFiles[$call.Name] = $response
    } catch {
        $stopwatch.Stop()
        Write-Log "FEHLER bei $($call.Name): $_" -IsError $true
        # Nicht kritisch - weitermachen mit anderen Calls
    }
}

# --- 3. PlanningExceptions pro Mitarbeiter (SEQUENTIELL) ---
# TODO: PARALLEL - Alle MA Jobs parallel starten
# foreach ($ma in $employees) { $jobs += Start-Job -ScriptBlock { ... } }
# Dann: $jobs | Wait-Job | Receive-Job

$planningExceptions = @()

if ($jsonFiles.ContainsKey("EmployeeHours") -and $jsonFiles["EmployeeHours"].current) {
    $employees = $jsonFiles["EmployeeHours"].current
    Write-Log "FOUND: $($employees.Count) Mitarbeiter"
    
    $i = 0
    foreach ($employee in $employees) {
        $i++
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $userId = $employee.idxUser
        $userName = $employee.userFullName
        
        try {
            Write-Log "  [$i/$($employees.Count)] PlanningException: $userName (userId: $userId)"
            $planUrl = "$BaseUrl/ek/api/PlanningException/GetPlanningExceptionsForUser?userId=$userId`&year=$Year`&orgUnitId=$OrgUnitId"
            $response = Invoke-RestMethod -Uri $planUrl -UseDefaultCredentials -TimeoutSec 120 -ErrorAction Stop
            $stopwatch.Stop()
            Write-Log "  OK: $userName erhalten ($($stopwatch.ElapsedMilliseconds)ms)"
            
            # Response enthält User-Info + planningExceptions Array
            $planningExceptions += @{
                userId = $userId
                userName = $userName
                data = $response
            }
        } catch {
            $stopwatch.Stop()
            Write-Log "  WARNING: $userName timeout/fehler ($($stopwatch.ElapsedMilliseconds)ms): $_" -IsError $true
            # MA-Fehler: Nicht kritisch, mit nächster MA weitermachen
        }
    }
    Write-Log "OK: $($planningExceptions.Count) von $($employees.Count) MA erfolgreich abgerufen"
} else {
    Write-Log "FEHLER: EmployeeHours nicht vorhanden -> PlanningExceptions uebersprungen" -IsError $true
}

# --- 4. Konsolidierung aller JSON-Dateien in eine Datei ---
Write-Log "CONSOLIDATE: JSON-Dateien werden zusammengefuehrt..."

$consolidated = @{
    exportTimestamp     = (Get-Date -Format "o")
    year                = $Year
    orgUnitId           = $OrgUnitId
    orgUnitName         = $OrgUnitName
    cacheValidHours     = 24
    basicELData         = $jsonFiles["BasicELData"]
    employeeHours       = $jsonFiles["EmployeeHours"]
    planningExceptions  = $planningExceptions
    devOrders           = $jsonFiles["DevOrder"]
    btlData             = $jsonFiles["Btl"]
}

# Als JSON speichern
try {
    $consolidatedJson = $consolidated | ConvertTo-Json -Depth 20 -ErrorAction Stop
    [System.IO.File]::WriteAllText($ConsolidatedFile, $consolidatedJson, (New-Object System.Text.UTF8Encoding $false))
    Write-Log "OK: Konsolidiert in: $ConsolidatedFile ($([math]::Round((Get-Item $ConsolidatedFile).Length / 1KB, 1)) KB)"
} catch {
    Write-Log "FEHLER beim Speichern der konsolidierten Datei: $_" -IsError $true
    exit 1
}

# Cache-Zeitstempel speichern
try {
    Set-Content -Path $CacheCheckFile -Value (Get-Date -Format "o") -Encoding UTF8
    Write-Log "OK: Cache-Zeit gespeichert"
} catch {
    Write-Log "WARNING: Cache-Zeit konnte nicht gespeichert werden: $_" -IsError $true
}

# --- 5. Zusammenfassung ---
Write-Log "═══════════════════════════════════════════════════════"
Write-Log "EXPORT ABGESCHLOSSEN"
Write-Log "Output-Datei: $ConsolidatedFile"
Write-Log "Log-Datei: $LogFile"
Write-Log "Nächste Schritte: python analyze_el_data.py"
Write-Log "═══════════════════════════════════════════════════════"

# Pfad zur konsolidierten Datei zurückgeben
Write-Output $ConsolidatedFile
