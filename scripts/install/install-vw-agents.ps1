Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Split-PathEntries {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }
    return @(
        $Value -split ";" |
        ForEach-Object { $_.Trim() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
}

function Join-PathEntries {
    param([string[]]$Entries)
    return (($Entries | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ";")
}

function Add-PathEntry {
    param(
        [string[]]$Entries,
        [string]$Entry
    )
    if ($Entries -contains $Entry) {
        return ,$Entries
    }
    return @($Entries + $Entry)
}

function Get-EffectiveExecutionPolicySummary {
    $policies = Get-ExecutionPolicy -List
    return $policies
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$claudeSource = Join-Path $scriptDir "claudeVW.ps1"
$codexSource = Join-Path $scriptDir "codexVW.ps1"
$claudeDir = Join-Path $scriptDir ".claude"

if (-not (Test-Path $claudeSource)) {
    throw "Quelle nicht gefunden: $claudeSource"
}
if (-not (Test-Path $codexSource)) {
    throw "Quelle nicht gefunden: $codexSource"
}
if (-not (Test-Path $claudeDir)) {
    throw "Quelle nicht gefunden: $claudeDir"
}

$installRoot = Join-Path $env:LOCALAPPDATA "VWAI"
$binDir = Join-Path $installRoot "bin"
$installDir = Join-Path $installRoot "install"
$uninstallTarget = Join-Path $installDir "uninstall-vw-agents.ps1"
$uninstallSource = Join-Path $scriptDir "uninstall-vw-agents.ps1"

New-Item -ItemType Directory -Force -Path $binDir | Out-Null
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

Copy-Item -Path $claudeSource -Destination (Join-Path $binDir "claudeVW.ps1") -Force
Copy-Item -Path $codexSource -Destination (Join-Path $binDir "codexVW.ps1") -Force

$claudeTargetDir = Join-Path $binDir ".claude"
New-Item -ItemType Directory -Force -Path $claudeTargetDir | Out-Null
Get-ChildItem -Path $claudeDir -Recurse -File | Where-Object { $_.FullName -notmatch "__pycache__" } | ForEach-Object {
    $relativePath = $_.FullName -replace [regex]::Escape($claudeDir), ""
    $targetPath = Join-Path $claudeTargetDir $relativePath
    $targetPathDir = Split-Path -Parent $targetPath
    New-Item -ItemType Directory -Force -Path $targetPathDir | Out-Null
    Copy-Item -Path $_.FullName -Destination $targetPath -Force
}

Copy-Item -Path $uninstallSource -Destination $uninstallTarget -Force

$userPathRaw = [Environment]::GetEnvironmentVariable("Path", "User")
$userPathEntries = Split-PathEntries -Value $userPathRaw
$updatedUserPathEntries = Add-PathEntry -Entries $userPathEntries -Entry $binDir
$updatedUserPath = Join-PathEntries -Entries $updatedUserPathEntries
[Environment]::SetEnvironmentVariable("Path", $updatedUserPath, "User")

$processPathEntries = Split-PathEntries -Value $env:PATH
$updatedProcessPathEntries = Add-PathEntry -Entries $processPathEntries -Entry $binDir
$env:PATH = Join-PathEntries -Entries $updatedProcessPathEntries

$executionPolicies = Get-EffectiveExecutionPolicySummary
$effectivePolicy = Get-ExecutionPolicy
$machinePolicy = ($executionPolicies | Where-Object { $_.Scope -eq "MachinePolicy" }).ExecutionPolicy
$userPolicy = ($executionPolicies | Where-Object { $_.Scope -eq "UserPolicy" }).ExecutionPolicy

Write-Host ""
Write-Host "=== VW Agents installiert ==="
Write-Host "Installationsordner:  $installRoot"
Write-Host "Bin-Ordner:           $binDir"
Write-Host "Claude-Wrapper:       $(Join-Path $binDir 'claudeVW.ps1')"
Write-Host "Codex-Wrapper:        $(Join-Path $binDir 'codexVW.ps1')"
Write-Host "Claude-Utilities:     $(Join-Path $binDir '.claude')"
Write-Host "Uninstall-Script:     $uninstallTarget"
Write-Host "Effective Policy:     $effectivePolicy"

if ($machinePolicy -ne "Undefined" -or $userPolicy -ne "Undefined") {
    Write-Warning "Execution Policy wird teilweise per Group Policy gesteuert. Falls Skripte nicht laufen, bitte IT-/Policy-Kontext pruefen."
}
elseif ($effectivePolicy -eq "Restricted") {
    Write-Warning "Execution Policy ist Restricted. Lokale .ps1-Skripte laufen dann typischerweise nicht. RemoteSigned im CurrentUser-Scope ist der uebliche lokale Mindestwert."
}

Write-Host ""
Write-Host "Hinweis: Der User-PATH wurde aktualisiert."
Write-Host "Hinweis: Fuer andere bereits offene Shells bitte ein neues PowerShell-Fenster oeffnen."
Write-Host ""
Write-Host "Test jetzt im aktuellen Fenster:"
Write-Host "  claudeVW.ps1"
Write-Host "  codexVW.ps1"
Write-Host ""
