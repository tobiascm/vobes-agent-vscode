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

function Remove-PathEntry {
    param(
        [string[]]$Entries,
        [string]$Entry
    )
    return @($Entries | Where-Object { $_ -ne $Entry })
}

$installRoot = Join-Path $env:LOCALAPPDATA "VWAI"
$binDir = Join-Path $installRoot "bin"
$installDir = Join-Path $installRoot "install"

$claudeTarget = Join-Path $binDir "claudeVW.ps1"
$codexTarget = Join-Path $binDir "codexVW.ps1"
$claudeUtilsTarget = Join-Path $binDir ".claude"

if (Test-Path $claudeTarget) {
    Remove-Item $claudeTarget -Force
}
if (Test-Path $codexTarget) {
    Remove-Item $codexTarget -Force
}
if (Test-Path $claudeUtilsTarget) {
    Remove-Item $claudeUtilsTarget -Recurse -Force
}

$userPathRaw = [Environment]::GetEnvironmentVariable("Path", "User")
$userPathEntries = Split-PathEntries -Value $userPathRaw
$updatedUserPathEntries = Remove-PathEntry -Entries $userPathEntries -Entry $binDir
$updatedUserPath = Join-PathEntries -Entries $updatedUserPathEntries
[Environment]::SetEnvironmentVariable("Path", $updatedUserPath, "User")

$processPathEntries = Split-PathEntries -Value $env:PATH
$updatedProcessPathEntries = Remove-PathEntry -Entries $processPathEntries -Entry $binDir
$env:PATH = Join-PathEntries -Entries $updatedProcessPathEntries

if ((Test-Path $binDir) -and -not (Get-ChildItem -Force $binDir | Select-Object -First 1)) {
    Remove-Item $binDir -Force
}
if ((Test-Path $installDir) -and -not (Get-ChildItem -Force $installDir | Select-Object -First 1)) {
    Remove-Item $installDir -Force
}
if ((Test-Path $installRoot) -and -not (Get-ChildItem -Force $installRoot | Select-Object -First 1)) {
    Remove-Item $installRoot -Force
}

Write-Host ""
Write-Host "=== VW Agents deinstalliert ==="
Write-Host "Entfernt aus User-PATH: $binDir"
Write-Host "Nicht geloescht:"
Write-Host "  $HOME\.claudeVW"
Write-Host "  $HOME\.codexVW"
Write-Host ""
Write-Host "Bitte fuer andere geoeffnete Shells ein neues PowerShell-Fenster oeffnen."
Write-Host ""
